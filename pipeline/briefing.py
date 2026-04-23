"""
Daily Granite briefing — generates a plain-English safety summary from top 10 scored streets.
"""
import logging
import os
from datetime import datetime, timezone

import pandas as pd
from ibm_watsonx_ai import Credentials
from ibm_watsonx_ai.foundation_models import ModelInference
from sqlalchemy import text

from pipeline.database import get_db_engine

logger = logging.getLogger(__name__)

MODEL_ID = "ibm/granite-4-h-small"
BRIEFING_KEY = "DAILY_BRIEFING"


def _build_prompt(top10: pd.DataFrame) -> str:
    lines = []
    for _, row in top10.iterrows():
        lines.append(
            f"- {row['location_name']}: {int(row['crash_count'])} crashes, "
            f"{int(row['fatality_count'])} fatalities, {int(row['complaint_count'])} complaints, "
            f"{row['recency_score']:.0%} of incidents in last 90 days, score {row['final_score']:.1f}/100"
        )
    data_block = "\n".join(lines)
    return (
        "You are a road safety analyst for the San Francisco Municipal Transportation Agency (SFMTA). "
        "Based on cumulative road safety data from the past year of incidents, write a 3-sentence briefing "
        "for a non-technical director identifying the highest priority streets and what is driving their scores. "
        "Be specific about which streets have fatalities vs high complaint volume vs recent activity. "
        "Do not use jargon.\n\n"
        f"Top 10 streets by risk score:\n{data_block}"
    )


def generate_daily_briefing():
    engine = get_db_engine()

    top10 = pd.read_sql(
        "SELECT location_name, crash_count, fatality_count, complaint_count, "
        "recency_score, final_score FROM scored_zones ORDER BY final_score DESC LIMIT 10",
        engine,
    )

    if top10.empty:
        logger.warning("scored_zones is empty — skipping daily briefing")
        return

    prompt = _build_prompt(top10)

    credentials = Credentials(
        url=os.getenv("WATSONX_URL"),
        api_key=os.getenv("WATSONX_API_KEY"),
    )
    model = ModelInference(
        model_id=MODEL_ID,
        credentials=credentials,
        project_id=os.getenv("WATSONX_PROJECT_ID"),
        params={"max_new_tokens": 300, "temperature": 0.3},
    )
    explanation = model.generate_text(prompt=prompt)

    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM ai_explanations WHERE location_name = :key"),
            {"key": BRIEFING_KEY},
        )
        conn.execute(
            text(
                "INSERT INTO ai_explanations "
                "(location_name, question_asked, explanation, generated_at) "
                "VALUES (:location_name, :question_asked, :explanation, :generated_at)"
            ),
            {
                "location_name": BRIEFING_KEY,
                "question_asked": prompt,
                "explanation": explanation,
                "generated_at": datetime.now(timezone.utc),
            },
        )

    logger.info("Daily briefing generated and stored.")
    print(f"Briefing stored:\n{explanation}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    generate_daily_briefing()
