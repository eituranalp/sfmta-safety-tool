# AI-Powered Road Safety Prioritization for SFMTA

Built by **Team Golden Gate** for the IBM SkillsBuild AI Experiential Learning Lab 2026.

[![Live Dashboard](https://img.shields.io/badge/Live_Dashboard-Visit-blue)](https://sfmta-safety-tool-yvduhajzsv7dnrpoecwvvv.streamlit.app/)

  [![Demo Video](https://img.shields.io/badge/Demo_Video-YouTube-red)](https://www.youtube.com/watch?v=ZoMH6Bb5gyE)

A proof-of-concept decision-support tool that helps a non-technical SFMTA director identify which San Francisco streets should be prioritized for safety improvements. It ingests public crash and complaint data daily, scores streets by risk, generates an AI briefing using IBM Granite, and surfaces results through a conversational interface and a live dashboard.

---

## Architecture

```
SF Open Data (Socrata API)
        ↓
DataIngestionModule — fetches crash + 311 data daily into PostgreSQL
        ↓
RiskScoringModule — scores every street → scored_zones table
        ↓
Granite Briefing — IBM Granite summarizes top 10 streets → ai_explanations table
        ↓
  ┌─────────────────────────────────┐
  │                                 │
  ▼                                 ▼
IBM watsonx Orchestrate         Streamlit Dashboard
Karl asks plain-English          Map + table view of
questions → Orchestrate calls    scored streets, on-demand
FastAPI → SQL query → JSON       Granite briefing
→ Orchestrate explains results
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Backend API | FastAPI + Uvicorn |
| Scheduler | APScheduler (daily at 6am UTC) |
| Database | PostgreSQL on Render |
| AI Model | IBM Granite (`ibm/granite-4-h-small`) via watsonx.ai |
| Conversational UI | IBM watsonx Orchestrate |
| Visual Dashboard | Streamlit |
| Hosting | Render free tier |
| Keep-alive | UptimeRobot (5-min pings to /health) |

---

## Data Sources

All data is public — no API key required.

| Dataset | Socrata ID | Notes |
|---|---|---|
| Traffic Crashes — Injury | `ubvf-ztfx` | Quarterly updates |
| Traffic Crashes — Fatality | `dau3-4s8f` | Quarterly, 1-month lag |
| SF 311 Cases | `vw6y-z8j6` | Nightly updates |

Only safety-relevant 311 categories are ingested (blocked streets, pavement defects, streetlights, flooding, damaged traffic signals, etc.).

---

## Project Structure

```
sfmta-safety-tool/
├── .python-version       # Pins Python 3.11 for Render
├── requirements.txt
├── run_normal.py         # Local manual ingestion trigger (dev only)
│
├── api/
│   └── main.py           # FastAPIServer — /query, /ingest, /score, /briefing, /health
│
├── dashboard/
│   └── app.py            # Streamlit dashboard
│
└── pipeline/
    ├── database.py       # SQLAlchemy models + DB connection
    ├── ingest.py         # DataIngestionModule — Socrata fetch + normalize + store
    ├── score.py          # RiskScoringModule — street-level risk scoring
    └── briefing.py       # Daily Granite briefing — reads top 10, writes to ai_explanations
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/query` | GET | Query scored streets — all params optional |
| `/ingest` | POST | Manually trigger data ingestion |
| `/score` | POST | Manually trigger risk scoring |
| `/briefing` | GET | Return the latest stored Granite briefing |
| `/health` | GET | Health check for UptimeRobot keep-alive |

### /query Parameters

| Parameter | Type | Description |
|---|---|---|
| `street_name` | string | Partial street name filter (ILIKE) |
| `metric` | string | Sort by: `final_score`, `crash_count`, `fatality_count`, `complaint_count`, `recency_score` |
| `limit` | int | Results to return (default 10, max 50) |
| `days_recent` | int | Filter to streets with activity in last N days |
| `lat_min/lat_max/lng_min/lng_max` | float | Bounding box filter |

---

## Risk Scoring Formula

Each street gets a `final_score` from 0–100:

```
recency_score  = recent_crashes / total_crashes   (recent = last 90 days)
raw_score      = (crash_count × 0.4) + (fatality_count × 3.5) + (complaint_count × 0.1) + (recency_score × 20)
final_score    = (raw_score / max_raw_across_all_streets) × 100
```

Streets with fewer than 3 total records are excluded.

---

## Setup (Local)

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Configure environment variables
Create a `.env` file:
```
DATABASE_URL=postgresql://user:password@host/dbname
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_PROJECT_ID=your_project_id
WATSONX_API_KEY=your_api_key
```

Omit `DATABASE_URL` to use a local SQLite file for development.

### 3. Initialize the database
```bash
python -m pipeline.database
```

### 4. Start the API server
```bash
uvicorn api.main:app --reload
```

### 5. Start the dashboard
```bash
streamlit run dashboard/app.py
```

---

## Current Data (as of April 2026)

| Table | Records | Date Range |
|---|---|---|
| `crashes_injury` | 2,365 | Apr 2025 – Apr 2026 |
| `crashes_fatality` | 18 | Apr 2025 – Apr 2026 |
| `cases_311` | 46,986 | Apr 2025 – Apr 2026 |
| `scored_zones` | 1,957 streets | Apr 2025 – Apr 2026 |

---

## Notes

- **Do not commit `.env`** — IBM Cloud credentials are deactivated immediately if exposed
- **Render free tier sleeps** after 15 minutes — UptimeRobot keeps it alive during demos
- **Orchestrate tool import** — export `/openapi.json` from the running server and import into Orchestrate via Build → Agents → Toolset → Add tool → OpenAPI

---

## Built With IBM

- IBM watsonx.ai — Granite foundation model (`ibm/granite-4-h-small`)
- IBM watsonx Orchestrate — Conversational interface
- IBM SkillsBuild AI Experiential Learning Lab 2026
