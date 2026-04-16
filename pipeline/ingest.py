"""
DataIngestionModule - Fetch SF Open Data via Socrata API with time-based intervals
"""
import os
from datetime import datetime, timedelta
import logging
from sodapy import Socrata
from sqlalchemy.exc import IntegrityError

from pipeline.database import (
    get_session, CrashInjury, CrashFatality, Case311, IngestMetadata
)

logger = logging.getLogger(__name__)


class DataIngestionModule:
    """Fetches data from SF Open Data (Socrata) API with intelligent update intervals"""

    # Socrata API credentials
    DOMAIN = "data.sfgov.org"
    SOCRATA_API_KEY = os.getenv("SOCRATA_API_KEY")

    # Dataset IDs (from CLAUDE.md)
    CRASHES_INJURY_ID = "ubvf-ztfx"
    CRASHES_FATALITY_ID = "dau3-4s8f"
    CASES_311_ID = "vw6y-z8j6"

    # Update frequencies (days between pulls)
    # From CLAUDE.md: Crashes quarterly, 311 nightly
    UPDATE_INTERVALS = {
        CRASHES_INJURY_ID: 90,      # Quarterly
        CRASHES_FATALITY_ID: 90,    # Quarterly + 1-month lag
        CASES_311_ID: 1,            # Nightly
    }

    DATASET_NAMES = {
        CRASHES_INJURY_ID: "Traffic Crashes (Injury)",
        CRASHES_FATALITY_ID: "Traffic Crashes (Fatality)",
        CASES_311_ID: "SF 311 Service Cases",
    }

    def __init__(self):
        """Initialize Socrata client"""
        self.client = Socrata(self.DOMAIN, self.SOCRATA_API_KEY)
        self.session = get_session()
        self.ingest_report = {}

    def should_update_dataset(self, dataset_id: str) -> bool:
        """Check if dataset is due for an update based on its frequency"""
        metadata = self.session.query(IngestMetadata).filter(
            IngestMetadata.dataset_id == dataset_id
        ).first()

        if not metadata:
            return True  # Never synced, do initial pull

        update_interval = self.UPDATE_INTERVALS.get(dataset_id, 90)
        days_since_sync = (datetime.utcnow() - metadata.last_synced).days
        return days_since_sync >= update_interval

    def get_last_sync_timestamp(self, dataset_id: str) -> datetime:
        """Get the last sync timestamp for a dataset"""
        metadata = self.session.query(IngestMetadata).filter(
            IngestMetadata.dataset_id == dataset_id
        ).first()

        if metadata:
            return metadata.last_synced or (datetime.utcnow() - timedelta(days=365))
        return datetime.utcnow() - timedelta(days=365)  # Default: last 1 year for initial pull

    def ingest_crashes_injury(self, force: bool = False) -> dict:
        """Fetch Traffic Crashes Resulting in Injury via SODA API (Quarterly)"""
        dataset_id = self.CRASHES_INJURY_ID
        dataset_name = self.DATASET_NAMES[dataset_id]

        # Check if update is needed
        if not force and not self.should_update_dataset(dataset_id):
            days_until_next = self.UPDATE_INTERVALS[dataset_id] - (
                datetime.utcnow() - self.session.query(IngestMetadata).filter(
                    IngestMetadata.dataset_id == dataset_id
                ).first().last_synced
            ).days
            logger.info(f"⊘ {dataset_name}: Skipped (next update in ~{days_until_next} days)")
            return {"dataset": dataset_name, "status": "skipped", "reason": "not_due"}

        last_sync = self.get_last_sync_timestamp(dataset_id)
        logger.info(f"\n📥 {dataset_name} (Quarterly, ubvf-ztfx)")
        logger.info(f"   Fetching records since: {last_sync.strftime('%Y-%m-%d')}")

        where_clause = f"collision_date >= '{last_sync.isoformat()}'"

        try:
            records = self.client.get(
                dataset_id,
                where=where_clause,
                limit=50000
            )
            logger.info(f"   API returned: {len(records)} records")

            inserted = 0
            skipped = 0
            for record in records:
                try:
                    crash = CrashInjury(
                        unique_id=record.get("unique_id"),
                        case_id_pkey=record.get("case_id_pkey"),
                        collision_datetime=self._parse_datetime(record.get("collision_datetime")),
                        collision_date=self._parse_datetime(record.get("collision_date")),
                        collision_year=self._to_int(record.get("accident_year")),
                        tb_latitude=self._to_float(record.get("tb_latitude")),
                        tb_longitude=self._to_float(record.get("tb_longitude")),
                        primary_rd=record.get("primary_rd"),
                        secondary_rd=record.get("secondary_rd"),
                        number_injured=self._to_int(record.get("number_injured")),
                        number_killed=self._to_int(record.get("number_killed")),
                        collision_severity=record.get("collision_severity"),
                        type_of_collision=record.get("type_of_collision"),
                        weather_1=record.get("weather_1"),
                        lighting=record.get("lighting"),
                        road_surface=record.get("road_surface"),
                        reporting_district=record.get("reporting_district"),
                        police_district=record.get("police_district"),
                        supervisor_district=record.get("supervisor_district"),
                    )
                    self.session.add(crash)
                    inserted += 1
                except IntegrityError:
                    self.session.rollback()
                    skipped += 1
                    continue

            self.session.commit()
            self._update_metadata(dataset_id, dataset_name, len(records))

            result = {
                "dataset": dataset_name,
                "status": "success",
                "total_records": len(records),
                "inserted": inserted,
                "duplicates_skipped": skipped,
            }
            logger.info(f"   ✓ Inserted: {inserted} | Duplicates: {skipped}")
            self.ingest_report[dataset_id] = result
            return result

        except Exception as e:
            logger.error(f"   ✗ Error: {e}")
            self.session.rollback()
            return {"dataset": dataset_name, "status": "error", "error": str(e)}

    def ingest_crashes_fatality(self, force: bool = False) -> dict:
        """Fetch Traffic Crashes Resulting in Fatality via SODA API (Quarterly, 1-month lag)"""
        dataset_id = self.CRASHES_FATALITY_ID
        dataset_name = self.DATASET_NAMES[dataset_id]

        if not force and not self.should_update_dataset(dataset_id):
            days_until_next = self.UPDATE_INTERVALS[dataset_id] - (
                datetime.utcnow() - self.session.query(IngestMetadata).filter(
                    IngestMetadata.dataset_id == dataset_id
                ).first().last_synced
            ).days
            logger.info(f"⊘ {dataset_name}: Skipped (next update in ~{days_until_next} days)")
            return {"dataset": dataset_name, "status": "skipped", "reason": "not_due"}

        last_sync = self.get_last_sync_timestamp(dataset_id)
        logger.info(f"\n📥 {dataset_name} (Quarterly + 1mo lag, dau3-4s8f)")
        logger.info(f"   Fetching records since: {last_sync.strftime('%Y-%m-%d')}")

        where_clause = f"collision_date >= '{last_sync.isoformat()}'"

        try:
            records = self.client.get(
                dataset_id,
                where=where_clause,
                limit=50000
            )
            logger.info(f"   API returned: {len(records)} records")

            inserted = 0
            skipped = 0
            for record in records:
                try:
                    crash = CrashFatality(
                        unique_id=record.get("unique_id"),
                        case_id_fkey=record.get("case_id_fkey"),
                        collision_date=self._parse_datetime(record.get("collision_date")),
                        collision_year=self._to_int(record.get("collision_year")),
                        death_date=self._parse_datetime(record.get("death_date")),
                        latitude=self._to_float(record.get("latitude")),
                        longitude=self._to_float(record.get("longitude")),
                        location=record.get("location"),
                        age=self._to_int(record.get("age")),
                        sex=record.get("sex"),
                        collision_type=record.get("collision_type"),
                        supervisor_district=record.get("supervisor_district"),
                        police_district=record.get("police_district"),
                    )
                    self.session.add(crash)
                    inserted += 1
                except IntegrityError:
                    self.session.rollback()
                    skipped += 1
                    continue

            self.session.commit()
            self._update_metadata(dataset_id, dataset_name, len(records))

            result = {
                "dataset": dataset_name,
                "status": "success",
                "total_records": len(records),
                "inserted": inserted,
                "duplicates_skipped": skipped,
            }
            logger.info(f"   ✓ Inserted: {inserted} | Duplicates: {skipped}")
            self.ingest_report[dataset_id] = result
            return result

        except Exception as e:
            logger.error(f"   ✗ Error: {e}")
            self.session.rollback()
            return {"dataset": dataset_name, "status": "error", "error": str(e)}

    def _fetch_with_pagination(self, dataset_id: str, where_clause: str, limit: int = 50000) -> list:
        """Fetch records with pagination (handles 50k limit by making multiple requests)"""
        all_records = []
        offset = 0
        batch_num = 1

        while True:
            try:
                records = self.client.get(
                    dataset_id,
                    where=where_clause,
                    limit=limit,
                    offset=offset
                )
                if not records:
                    logger.info(f"   Batch {batch_num} (offset {offset:,}): Empty response, pagination complete")
                    break

                all_records.extend(records)
                logger.info(f"   Batch {batch_num} (offset {offset:,}): {len(records)} records | Total so far: {len(all_records):,}")

                # Stop if we got fewer records than the limit (last page)
                if len(records) < limit:
                    logger.info(f"   Batch {batch_num}: Got {len(records)} records (< {limit}), pagination complete")
                    break

                offset += limit
                batch_num += 1
            except Exception as e:
                logger.error(f"   Error during pagination at offset {offset}: {e}")
                break

        return all_records

    def ingest_311_cases(self, force: bool = False) -> dict:
        """Fetch SF 311 Cases via SODA API (Nightly updates) - Safety-relevant only"""
        dataset_id = self.CASES_311_ID
        dataset_name = self.DATASET_NAMES[dataset_id]

        if not force and not self.should_update_dataset(dataset_id):
            logger.info(f"⊘ {dataset_name}: Skipped (next update in ~1 day)")
            return {"dataset": dataset_name, "status": "skipped", "reason": "not_due"}

        last_sync = self.get_last_sync_timestamp(dataset_id)
        logger.info(f"\n📥 {dataset_name} (Nightly, vw6y-z8j6)")
        logger.info(f"   Fetching records since: {last_sync.strftime('%Y-%m-%d %H:%M')}")
        logger.info(f"   Filtering for safety-relevant subtypes only")

        # Filter for safety-relevant (service_name, service_subtype) pairs confirmed in SF 311 dataset
        safety_filters = [
            ("Blocked Street and Sidewalk", "blocked_sidewalk"),
            ("Blocked Street and Sidewalk", "blocked_parking_space_or_strip"),
            ("Street Defect", "pavement_defect"),
            ("Street Defect", "sidewalk_defect"),
            ("Street Defect", "manhole_cover_off"),
            ("Street Defect", "curb_or_curb_ramp_defect"),
            ("Sidewalk and Curb", "pavement_defect"),
            ("Sidewalk and Curb", "sidewalk_defect"),
            ("Sidewalk and Curb", "curb_or_curb_ramp_defect"),
            ("Streetlights", "light"),
            ("Sewer", "flooding"),
            ("Tree Maintenance", "damaged_tree"),
            ("Damage Property", "traffic_signal"),
            ("Damage Property", "transit_shelter_platform_hazardous"),
        ]
        or_clauses = " OR ".join(
            [f"(service_name='{sn}' AND service_subtype='{st}')" for sn, st in safety_filters]
        )
        where_clause = f"requested_datetime >= '{last_sync.isoformat()}' AND ({or_clauses})"

        try:
            records = self._fetch_with_pagination(dataset_id, where_clause)
            logger.info(f"   API returned: {len(records)} records (with pagination)")

            inserted = 0
            skipped = 0
            for record in records:
                try:
                    case = Case311(
                        service_request_id=record.get("service_request_id"),
                        requested_datetime=self._parse_datetime(record.get("requested_datetime")),
                        closed_date=self._parse_datetime(record.get("closed_date")),
                        status_description=record.get("status_description"),
                        service_name=record.get("service_name"),
                        service_subtype=record.get("service_subtype"),
                        service_details=record.get("service_details"),
                        address=record.get("address"),
                        latitude=self._to_float(record.get("lat")),
                        longitude=self._to_float(record.get("long")),
                        supervisor_district=record.get("supervisor_district"),
                        police_district=record.get("police_district"),
                        neighborhoods=record.get("neighborhoods_sffind_boundaries"),
                    )
                    self.session.add(case)
                    inserted += 1
                except IntegrityError:
                    self.session.rollback()
                    skipped += 1
                    continue

            self.session.commit()
            self._update_metadata(dataset_id, dataset_name, len(records))

            result = {
                "dataset": dataset_name,
                "status": "success",
                "total_records": len(records),
                "inserted": inserted,
                "duplicates_skipped": skipped,
            }
            logger.info(f"   ✓ Inserted: {inserted} | Duplicates: {skipped}")
            self.ingest_report[dataset_id] = result
            return result

        except Exception as e:
            logger.error(f"   ✗ Error: {e}")
            self.session.rollback()
            return {"dataset": dataset_name, "status": "error", "error": str(e)}

    def ingest_all(self, force: bool = False) -> dict:
        """Run all ingestion pipelines with smart scheduling"""
        logger.info("=" * 70)
        logger.info(f"🔄 SFMTA Safety Tool - Data Ingestion Pipeline")
        logger.info(f"   Timestamp: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}")
        logger.info(f"   Mode: {'FORCE (all datasets)' if force else 'SMART (only due datasets)'}")
        logger.info("=" * 70)

        results = {
            "crashes_injury": self.ingest_crashes_injury(force=force),
            "crashes_fatality": self.ingest_crashes_fatality(force=force),
            "cases_311": self.ingest_311_cases(force=force),
        }

        # Summary report
        logger.info("\n" + "=" * 70)
        logger.info("📊 INGESTION SUMMARY")
        logger.info("=" * 70)

        total_inserted = 0
        total_skipped = 0

        for dataset_id, result in results.items():
            if result["status"] == "success":
                total_inserted += result["inserted"]
                total_skipped += result["duplicates_skipped"]
                logger.info(
                    f"  {result['dataset']:35} | "
                    f"Inserted: {result['inserted']:5d} | "
                    f"Skipped: {result['duplicates_skipped']:5d}"
                )
            elif result["status"] == "skipped":
                logger.info(f"  {result['dataset']:35} | ⊘ Not due (next update soon)")
            else:
                logger.info(f"  {result['dataset']:35} | ✗ {result.get('error', 'Unknown error')}")

        logger.info("-" * 70)
        logger.info(f"  TOTAL INSERTED: {total_inserted:6d} records")
        logger.info(f"  TOTAL DUPLICATES: {total_skipped:6d} records")
        logger.info("=" * 70 + "\n")

        return results

    def ingest_all_force(self) -> dict:
        """Force full ingestion of all datasets (ignoring update intervals)"""
        return self.ingest_all(force=True)

    def _update_metadata(self, dataset_id: str, dataset_name: str, record_count: int):
        """Update ingest metadata for a dataset"""
        metadata = self.session.query(IngestMetadata).filter(
            IngestMetadata.dataset_id == dataset_id
        ).first()

        if metadata:
            metadata.last_synced = datetime.utcnow()
            metadata.record_count = record_count
        else:
            metadata = IngestMetadata(
                dataset_id=dataset_id,
                dataset_name=dataset_name,
                last_synced=datetime.utcnow(),
                record_count=record_count,
            )
            self.session.add(metadata)

        self.session.commit()

    @staticmethod
    def _parse_datetime(value) -> datetime:
        """Parse datetime string"""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        except:
            return None

    @staticmethod
    def _to_float(value) -> float:
        """Convert to float safely"""
        try:
            return float(value) if value else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_int(value) -> int:
        """Convert to int safely"""
        try:
            return int(value) if value else None
        except (ValueError, TypeError):
            return None

    def show_sync_status(self):
        """Display last sync timestamps for all datasets"""
        logger.info("\n" + "=" * 70)
        logger.info("📋 DATASET SYNC STATUS")
        logger.info("=" * 70)

        all_metadata = self.session.query(IngestMetadata).all()

        for metadata in all_metadata:
            update_interval = self.UPDATE_INTERVALS.get(metadata.dataset_id, "Unknown")
            days_since = (datetime.utcnow() - metadata.last_synced).days if metadata.last_synced else "Never"

            status = "✓" if self.should_update_dataset(metadata.dataset_id) or days_since == "Never" else "•"
            logger.info(
                f"  {status} {metadata.dataset_name:35} | "
                f"Records: {metadata.record_count:6d} | "
                f"Last synced: {metadata.last_synced.strftime('%Y-%m-%d %H:%M') if metadata.last_synced else 'Never':16} | "
                f"Interval: {update_interval}d"
            )

        logger.info("=" * 70 + "\n")

    def verify_data_accuracy(self) -> dict:
        """Verify that data was ingested correctly by checking record counts"""
        logger.info("\n" + "=" * 70)
        logger.info("🔍 DATA ACCURACY VERIFICATION")
        logger.info("=" * 70)

        from sqlalchemy import func

        results = {}

        # Check crashes (injury)
        injury_count = self.session.query(func.count(CrashInjury.id)).scalar()
        injury_with_location = self.session.query(func.count(CrashInjury.id)).filter(
            (CrashInjury.tb_latitude != None) & (CrashInjury.tb_longitude != None)
        ).scalar()

        results["crashes_injury"] = {
            "total": injury_count,
            "with_location": injury_with_location,
            "completeness": f"{(injury_with_location / injury_count * 100):.1f}%" if injury_count > 0 else "N/A",
        }

        # Check crashes (fatality)
        fatality_count = self.session.query(func.count(CrashFatality.id)).scalar()
        fatality_with_location = self.session.query(func.count(CrashFatality.id)).filter(
            (CrashFatality.latitude != None) & (CrashFatality.longitude != None)
        ).scalar()

        results["crashes_fatality"] = {
            "total": fatality_count,
            "with_location": fatality_with_location,
            "completeness": f"{(fatality_with_location / fatality_count * 100):.1f}%" if fatality_count > 0 else "N/A",
        }

        # Check 311 cases
        cases_count = self.session.query(func.count(Case311.id)).scalar()
        cases_with_location = self.session.query(func.count(Case311.id)).filter(
            (Case311.latitude != None) & (Case311.longitude != None)
        ).scalar()

        results["cases_311"] = {
            "total": cases_count,
            "with_location": cases_with_location,
            "completeness": f"{(cases_with_location / cases_count * 100):.1f}%" if cases_count > 0 else "N/A",
        }

        # Log results
        logger.info(f"  {'Dataset':35} | {'Total':8} | {'With Location':15} | {'Completeness'}")
        logger.info("-" * 70)

        for dataset_name, data in results.items():
            logger.info(
                f"  {dataset_name:35} | {data['total']:8} | {data['with_location']:15} | {data['completeness']}"
            )

        logger.info("=" * 70 + "\n")

        return results

    def close(self):
        """Close database session"""
        self.session.close()
