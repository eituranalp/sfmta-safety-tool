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
