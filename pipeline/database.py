"""
Database connections and table definitions for SFMTA Safety Tool
"""
import os
import sys
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, Float, String, DateTime, Boolean, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

Base = declarative_base()


class CrashInjury(Base):
    """Traffic Crashes Resulting in Injury (ubvf-ztfx)"""
    __tablename__ = "crashes_injury"

    id = Column(Integer, primary_key=True)
    unique_id = Column(String, unique=True, index=True)
    case_id_pkey = Column(String)
    collision_datetime = Column(DateTime)
    collision_date = Column(DateTime)
    collision_year = Column(Integer)
    tb_latitude = Column(Float)
    tb_longitude = Column(Float)
    primary_rd = Column(String)
    secondary_rd = Column(String)
    number_injured = Column(Integer)
    number_killed = Column(Integer)
    collision_severity = Column(String)
    type_of_collision = Column(String)
    weather_1 = Column(String)
    lighting = Column(String)
    road_surface = Column(String)
    reporting_district = Column(String)
    police_district = Column(String)
    supervisor_district = Column(String)
    # analysis_neighborhood: clean groupable field used by RiskScoringModule
    analysis_neighborhood = Column(String, index=True)
    ingested_at = Column(DateTime, default=datetime.utcnow)


class CrashFatality(Base):
    """Traffic Crashes Resulting in Fatality (dau3-4s8f)"""
    __tablename__ = "crashes_fatality"

    id = Column(Integer, primary_key=True)
    unique_id = Column(String, unique=True, index=True)
    case_id_fkey = Column(String)
    collision_date = Column(DateTime)
    collision_year = Column(Integer)
    death_date = Column(DateTime)
    latitude = Column(Float)
    longitude = Column(Float)
    location = Column(String)
    age = Column(Integer)
    sex = Column(String)
    collision_type = Column(String)
    supervisor_district = Column(String)
    police_district = Column(String)
    # analysis_neighborhood: clean groupable field used by RiskScoringModule
    analysis_neighborhood = Column(String, index=True)
    ingested_at = Column(DateTime, default=datetime.utcnow)


class Case311(Base):
    """SF 311 Service Cases (vw6y-z8j6)"""
    __tablename__ = "cases_311"

    id = Column(Integer, primary_key=True)
    service_request_id = Column(String, unique=True, index=True)
    requested_datetime = Column(DateTime)
    closed_date = Column(DateTime)
    status_description = Column(String)
    service_name = Column(String)
    service_subtype = Column(String)
    service_details = Column(Text)
    address = Column(String)
    latitude = Column(Float)
    longitude = Column(Float)
    supervisor_district = Column(String)
    police_district = Column(String)
    neighborhoods = Column(String)
    ingested_at = Column(DateTime, default=datetime.utcnow)


class IngestMetadata(Base):
    """Track last sync timestamps for incremental pulls"""
    __tablename__ = "ingest_metadata"

    id = Column(Integer, primary_key=True)
    dataset_id = Column(String, unique=True, index=True)  # ubvf-ztfx, dau3-4s8f, vw6y-z8j6
    dataset_name = Column(String)
    last_synced = Column(DateTime)
    record_count = Column(Integer)
    sync_timestamp = Column(DateTime, default=datetime.utcnow)


class ScoredZone(Base):
    """Output of RiskScoringModule — ranked locations by risk (scored_zones)"""
    __tablename__ = "scored_zones"

    location_name = Column(String, primary_key=True)
    latitude = Column(Float)
    longitude = Column(Float)
    crash_count = Column(Integer)
    fatality_count = Column(Integer)
    complaint_count = Column(Integer)
    recency_score = Column(Float)   # 0.0 to 1.0, higher = more recent incidents
    final_score = Column(Float)     # 0.0 to 100.0, higher = more urgent
    last_updated = Column(DateTime)


class AIExplanation(Base):
    """Cache of Granite-generated explanations — prevents repeat API calls (ai_explanations)"""
    __tablename__ = "ai_explanations"

    location_name = Column(String, primary_key=True)
    question_asked = Column(Text)
    explanation = Column(Text)
    generated_at = Column(DateTime, default=datetime.utcnow)


def get_db_engine():
    """Create database engine for local SQLite or Postgres"""
    db_url = os.getenv("DATABASE_URL", "sqlite:///./sfmta_safety.db")
    return create_engine(db_url, echo=False)


def init_db():
    """Initialize database tables"""
    engine = get_db_engine()
    Base.metadata.create_all(engine)
    return engine


def create_tables():
    """Create all tables if they do not exist. Safe to run multiple times."""
    engine = get_db_engine()
    tables = [
        "crashes_injury",
        "crashes_fatality",
        "cases_311",
        "ingest_metadata",
        "scored_zones",
        "ai_explanations",
    ]
    print("Creating tables...")
    Base.metadata.create_all(engine, checkfirst=True)
    for table in tables:
        print(f"  {table}: ok")
    print("All tables created successfully.")
    return engine


def get_session():
    """Get database session"""
    engine = get_db_engine()
    Session = sessionmaker(bind=engine)
    return Session()


if __name__ == "__main__":
    print("Connecting to database...")
    try:
        engine = get_db_engine()
        with engine.connect() as conn:
            print("Connected successfully.")
        create_tables()
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

