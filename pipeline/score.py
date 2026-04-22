"""
RiskScoringModule - Score SF streets by safety risk and write to scored_zones
"""
import re
import logging
from datetime import datetime, timedelta

import pandas as pd

from pipeline.database import get_db_engine

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Street name normalization
# ---------------------------------------------------------------------------

def clean_street_name(raw):
    """Shared cleaner applied to every extracted name from every source.

    Order of operations per the normalization plan:
    1. Uppercase + strip whitespace
    2. Strip leading house number (digits+space) — safe for ordinals like 9TH/19TH
       because ordinals have no space between digit and suffix
    3. Strip leading zeros from ordinal numbers (09TH -> 9TH)
    4. Strip trailing punctuation
    5. Catch-all second pass for any residual digits+space
    6. Drop if fewer than 3 characters
    """
    if not raw:
        return None
    name = raw.strip().upper()
    # Step 1 safety net: strip city suffix in case per-source logic missed it
    name = re.split(r',\s*(?:SAN FRANCISCO|SF)\b', name, flags=re.IGNORECASE)[0].strip()
    # Step 2: strip leading house number — digits followed by a space
    name = re.sub(r'^\d+\s+', '', name).strip()
    # Step 3: strip leading zeros from ordinal street numbers
    name = re.sub(r'\b0+(\d+(?:ST|ND|RD|TH)\b)', r'\1', name, flags=re.IGNORECASE)
    # Step 4: strip trailing punctuation
    name = re.sub(r'[,;.]+$', '', name).strip()
    # Step 5: catch-all — if still starts with digits+space, strip again
    name = re.sub(r'^\d+\s+', '', name).strip()
    return name if len(name) >= 3 else None


def _streets_from_primary_rd(primary_rd):
    """crashes_injury.primary_rd — mostly clean single street names.

    Per-source step: strip 'IFO NNNN' prefix (In Front Of address refs).
    Then shared clean_street_name() handles house numbers and ordinals.
    """
    if not primary_rd:
        return []
    name = re.sub(r'^IFO\s+\d+\s+', '', primary_rd.strip(), flags=re.IGNORECASE)
    name = clean_street_name(name)
    return [name] if name else []


def _streets_from_location(location):
    """crashes_fatality.location — free text intersection/proximity descriptions.

    Per-source step: parse structure (between/near/and/&).
    'X between A and B'  -> [X]     X is the primary road; A/B are cross-street landmarks
    'X near ...'         -> [X]     incident is on X
    'X and Y' / 'X & Y' -> [X, Y]  true intersection, count both streets
    Then shared clean_street_name() applied to each result.
    """
    if not location:
        return []

    # 'X between A and B' — take X only
    between_match = re.match(r'^(.+?)\s+between\b', location, re.IGNORECASE)
    if between_match:
        name = clean_street_name(between_match.group(1))
        return [name] if name else []

    # 'X near ...' — take X only
    if re.search(r'\bnear\b', location, re.IGNORECASE):
        primary = re.split(r'\bnear\b', location, flags=re.IGNORECASE)[0]
        name = clean_street_name(primary)
        return [name] if name else []

    # 'X and Y' or 'X & Y' — true intersection, count both
    if re.search(r'\band\b|&', location, re.IGNORECASE):
        parts = re.split(r'\band\b|&', location, flags=re.IGNORECASE)
        names = []
        for p in parts:
            name = clean_street_name(p)
            if name:
                names.append(name)
        return names

    # Default
    name = clean_street_name(location.split(',')[0])
    return [name] if name else []


def _streets_from_address(address):
    """cases_311.address — house addresses and INTERSECTION prefix format.

    Per-source step: strip city/ZIP suffix, detect INTERSECTION prefix.
    '899 27TH AVE, SAN FRANCISCO, CA 94121'         -> ['27TH AVE']
    'INTERSECTION FILLMORE ST, BUSH ST, SF, CA ...' -> ['FILLMORE ST', 'BUSH ST']
    Then shared clean_street_name() applied to each result.
    """
    if not address:
        return []

    # Strip city/state/ZIP suffix
    address = re.split(r',\s*SAN FRANCISCO\b', address, flags=re.IGNORECASE)[0].strip()

    # INTERSECTION prefix: 'INTERSECTION STREET1, STREET2'
    intersection_match = re.match(r'^INTERSECTION\s+(.+)', address, re.IGNORECASE)
    if intersection_match:
        parts = intersection_match.group(1).split(',')
        names = [clean_street_name(p) for p in parts]
        return [n for n in names if n]

    # Regular address: clean_street_name handles house number stripping
    name = clean_street_name(address)
    return [name] if name else []


def _explode_streets(df, street_col, lat_col, lng_col, date_col, source_label):
    """Apply street extraction, explode multi-street records, return clean DataFrame."""
    extractors = {
        'primary_rd': _streets_from_primary_rd,
        'location': _streets_from_location,
        'address': _streets_from_address,
    }
    df = df.copy()
    df['streets'] = df[street_col].apply(extractors[street_col])
    df = df.explode('streets').rename(columns={'streets': 'street', lat_col: 'lat', lng_col: 'lng', date_col: 'date'})
    df = df.dropna(subset=['street'])
    df = df[df['street'] != '']
    df['source'] = source_label
    return df[['street', 'lat', 'lng', 'date', 'source']]


# ---------------------------------------------------------------------------
# RiskScoringModule
# ---------------------------------------------------------------------------

class RiskScoringModule:
    """Scores SF streets by crash/complaint risk and writes results to scored_zones"""

    def score(self):
        engine = get_db_engine()
        cutoff = pd.Timestamp.utcnow() - timedelta(days=90)

        # --- Read raw tables ---
        df_injury = pd.read_sql(
            "SELECT primary_rd, tb_latitude, tb_longitude, collision_date FROM crashes_injury",
            engine
        )
        df_fatality = pd.read_sql(
            "SELECT location, latitude, longitude, collision_date FROM crashes_fatality",
            engine
        )
        df_311 = pd.read_sql(
            "SELECT address, latitude, longitude, requested_datetime FROM cases_311",
            engine
        )

        # --- Normalize and explode street names ---
        injury = _explode_streets(df_injury, 'primary_rd', 'tb_latitude', 'tb_longitude', 'collision_date', 'injury')
        fatality = _explode_streets(df_fatality, 'location', 'latitude', 'longitude', 'collision_date', 'fatality')
        cases = _explode_streets(df_311, 'address', 'latitude', 'longitude', 'requested_datetime', '311')

        # --- Combine all records ---
        all_records = pd.concat([injury, fatality, cases], ignore_index=True)
        all_records['date'] = pd.to_datetime(all_records['date'], utc=True, errors='coerce')
        all_records['is_recent'] = all_records['date'] >= cutoff

        # --- Per-source counts per street ---
        crash_counts = injury.groupby('street').size().rename('crash_count')
        fatality_counts = fatality.groupby('street').size().rename('fatality_count')
        complaint_counts = cases.groupby('street').size().rename('complaint_count')

        # --- Recency score and mean coordinates per street ---
        street_stats = all_records.groupby('street').agg(
            lat=('lat', 'mean'),
            lng=('lng', 'mean'),
            total=('date', 'count'),
            recent=('is_recent', 'sum'),
        )
        street_stats['recency_score'] = (street_stats['recent'] / street_stats['total']).round(4)

        # --- Merge ---
        scored = street_stats[['lat', 'lng', 'recency_score']].copy()
        scored = scored.join(crash_counts, how='left')
        scored = scored.join(fatality_counts, how='left')
        scored = scored.join(complaint_counts, how='left')
        scored = scored.fillna(0)

        scored['crash_count'] = scored['crash_count'].astype(int)
        scored['fatality_count'] = scored['fatality_count'].astype(int)
        scored['complaint_count'] = scored['complaint_count'].astype(int)

        # --- Scoring formula ---
        scored['raw'] = (
            scored['crash_count'] * 0.4
            + scored['fatality_count'] * 3.5
            + scored['complaint_count'] * 0.1
            + scored['recency_score'] * 20
        )
        max_raw = scored['raw'].max()
        scored['final_score'] = ((scored['raw'] / max_raw * 100) if max_raw > 0 else 0.0).round(2)

        # --- Build output ---
        output = scored.reset_index().rename(columns={
            'street': 'location_name',
            'lat': 'latitude',
            'lng': 'longitude',
        })
        output['last_updated'] = datetime.utcnow()
        output = output[[
            'location_name', 'latitude', 'longitude',
            'crash_count', 'fatality_count', 'complaint_count',
            'recency_score', 'final_score', 'last_updated'
        ]]

        # --- Write to scored_zones ---
        output.to_sql('scored_zones', engine, if_exists='replace', index=False)
        logger.info(f'scored_zones updated: {len(output)} streets')

        # --- Print summary ---
        top10 = output.sort_values('final_score', ascending=False).head(10)
        print(f'\nscored_zones updated — {len(output)} streets scored')
        print(top10[['location_name', 'crash_count', 'fatality_count', 'complaint_count', 'recency_score', 'final_score']].to_string(index=False))

        return output


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    RiskScoringModule().score()
