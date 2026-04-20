### AI-Powered Road Safety Prioritization for SFMTA

Built by **Team Golden Rate** for the IBM SkillsBuild AI Experiential Learning Lab 2026.

This is a proof-of-concept decision-support tool that helps a non-technical SFMTA director identify which San Francisco streets should be prioritized for safety improvements. It ingests public crash and complaint data daily, scores locations by risk, and uses IBM Granite to answer plain-English questions about where to focus resources.

---

## How It Works

```
SF Open Data APIs (crashes + 311 complaints)
        ↓
Daily ingestion into PostgreSQL
        ↓
Risk scoring by street → scored_zones table
        ↓
Karl asks a question in IBM watsonx Orchestrate
        ↓
Two-stage Granite AI call (classify intent → fetch data → explain)
        ↓
Plain-English answer back to Karl
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11 |
| Backend | FastAPI + Uvicorn |
| Scheduler | APScheduler (daily ingestion) |
| Database | PostgreSQL on Render free tier |
| AI Model | IBM Granite (`ibm/granite-4-h-small`) via watsonx.ai |
| User Interface | IBM watsonx Orchestrate |
| Hosting | Render free tier |
| Keep-alive | UptimeRobot (5-min pings) |

---

## Data Sources

All data is public and fetched via the SF Open Data Socrata REST API.

| Dataset | ID | Notes |
|---|---|---|
| Traffic Crashes — Injury | `ubvf-ztfx` | Quarterly updates |
| Traffic Crashes — Fatality | `dau3-4s8f` | Quarterly, 1-month lag |
| SF 311 Cases | `vw6y-z8j6` | Nightly updates |

Only safety-relevant 311 categories are ingested (blocked streets, pavement defects, streetlights, flooding, damaged traffic signals, etc).

---

## Project Structure

```
sfmta-safety-tool/
├── .env                    # Never commit — credentials here
├── requirements.txt
├── run_normal.py           # Manual ingestion runner
│
├── api/
│   ├── main.py             # FastAPI server — /ingest, /score, /query
│   └── openapi.yaml        # OpenAPI spec imported into Orchestrate
│
└── pipeline/
    ├── database.py         # SQLAlchemy models + DB connection
    ├── ingest.py           # Fetches and stores raw data from Socrata
    ├── score.py            # Scores streets by risk → scored_zones
    └── query.py            # Two-stage Granite RAG call
```

---

## Setup

### 1. Clone and install dependencies
```bash
git clone <repo-url>
cd sfmta-safety-tool
pip install -r requirements.txt
```

### 2. Configure environment variables
Create a `.env` file in the project root:
```
DATABASE_URL=postgresql://user:password@host/dbname
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_PROJECT_ID=your_project_id
WATSONX_API_KEY=your_api_key
```

For local development, omit `DATABASE_URL` to use a local SQLite file instead.

### 3. Create database tables
```bash
python -m pipeline.database
```

### 4. Run ingestion
```bash
python run_normal.py
```

### 5. Start the API server
```bash
uvicorn api.main:app --reload
```

---

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/ingest` | POST | Fetch latest data from SF Open Data |
| `/score` | POST | Re-score all streets and update scored_zones |
| `/query` | POST | Answer a natural language question using Granite |
| `/health` | GET | Health check for UptimeRobot keep-alive |
| `/openapi.json` | GET | OpenAPI spec for Orchestrate tool import |

---

## AI Query Flow

When Karl asks a question, the `/query` endpoint runs two Granite calls:

**Stage 1 — Intent Classification**
Granite classifies Karl's question into a structured JSON object identifying what type of data to fetch (top priority streets, specific street, specific metric, or general question).

**Stage 2 — Explanation**
Granite receives the relevant scored street data and Karl's question, and returns a plain-English explanation Karl can use to justify budget decisions.

---

## Current Data (as of April 2026)

| Table | Records | Date Range |
|---|---|---|
| `crashes_injury` | 2,365 | Apr 2025 – Apr 2026 |
| `crashes_fatality` | 18 | Apr 2025 – Apr 2026 |
| `cases_311` | 46,986 | Apr 2025 – Apr 2026 |

---

## Important Notes

- **No API key required** for SF Open Data — datasets are public
- **Do not commit `.env`** — IBM Cloud credentials are deactivated immediately if exposed in a public repo
- **Render free tier sleeps** after 15 minutes of inactivity — UptimeRobot keeps it alive during demos
- **IAM tokens expire** after 60 minutes — token caching is implemented in `query.py`

---

## Built With IBM

- IBM watsonx.ai — Granite foundation model
- IBM watsonx Orchestrate — Conversational interface for Karl
- IBM SkillsBuild AI Experiential Learning Lab 2026
