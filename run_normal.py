# run_normal.py — Local manual ingestion trigger (development use only)
#
# On Render (production), APScheduler runs ingestion automatically at 6am UTC daily.
# Use this script locally to manually pull the latest data from SF Open Data into
# the database without triggering scoring or briefing.
#
# Usage: python run_normal.py

import os
from dotenv import load_dotenv
from pipeline.database import init_db
from pipeline.ingest import DataIngestionModule
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s'
)

load_dotenv()
init_db()

ingest = DataIngestionModule()
print("\n>>> Running in NORMAL mode (respecting update intervals)...\n")
results = ingest.ingest_all(force=False)

ingest.show_sync_status()
ingest.verify_data_accuracy()

ingest.close()
