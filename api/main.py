import logging
import os

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from pipeline.database import ScoredZone, get_session
from pipeline.ingest import DataIngestionModule

logger = logging.getLogger(__name__)

VALID_METRICS = {
    "final_score", "crash_count", "fatality_count",
    "complaint_count", "recency_score",
}

scheduler = BackgroundScheduler()


def daily_pipeline():
    try:
        ingestor = DataIngestionModule()
        ingestor.ingest_all()
        ingestor.close()
        logger.info("Daily ingest complete.")
    except Exception as e:
        logger.error(f"Daily ingest failed: {e}")
    # score() call goes here once score.py is implemented


app = FastAPI(title="SFMTA Safety Tool API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def start_scheduler():
    scheduler.add_job(daily_pipeline, "cron", hour=6, minute=0)
    scheduler.start()


@app.on_event("shutdown")
def stop_scheduler():
    scheduler.shutdown()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/query")
def query(
    question: str = None,
    street_name: str = None,
    metric: str = None,
    limit: int = 10,
    lat_min: float = None,
    lat_max: float = None,
    lng_min: float = None,
    lng_max: float = None,
):
    no_sql_params = not any([street_name, metric, lat_min, lat_max, lng_min, lng_max])
    if no_sql_params:
        return {"count": 0, "data": [], "message": "No query parameters provided."}

    if metric and metric not in VALID_METRICS:
        metric = "final_score"

    limit = min(max(1, limit), 50)

    session = get_session()
    try:
        q = session.query(ScoredZone)

        if street_name:
            q = q.filter(ScoredZone.location_name.ilike(f"%{street_name}%"))

        if all(v is not None for v in [lat_min, lat_max, lng_min, lng_max]):
            q = q.filter(
                ScoredZone.latitude.between(lat_min, lat_max),
                ScoredZone.longitude.between(lng_min, lng_max),
            )

        sort_col = getattr(ScoredZone, metric or "final_score")
        q = q.order_by(sort_col.desc()).limit(limit)

        rows = q.all()

        if not rows:
            return {"count": 0, "data": [], "message": "No scored data available yet. Run /score first."}

        data = [
            {
                "location_name": r.location_name,
                "crash_count": r.crash_count,
                "fatality_count": r.fatality_count,
                "complaint_count": r.complaint_count,
                "recency_score": r.recency_score,
                "final_score": r.final_score,
                "latitude": r.latitude,
                "longitude": r.longitude,
            }
            for r in rows
        ]

        return {"count": len(data), "data": data, "message": ""}
    finally:
        session.close()


@app.post("/ingest")
def ingest():
    try:
        ingestor = DataIngestionModule()
        ingestor.ingest_all()
        ingestor.close()
        return {"status": "success", "message": "Ingestion complete."}
    except Exception as e:
        return {"status": "error", "message": str(e)}


@app.post("/score")
def score():
    return {"status": "not_implemented", "message": "score.py not yet built."}
