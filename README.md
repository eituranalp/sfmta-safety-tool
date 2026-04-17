# SFMTA Road Safety Prioritization Tool
## Project Context for Claude Code

This file is the source of truth for all confirmed project decisions.
It is updated as decisions are made — do not treat anything not listed here as decided.

---

## What This Project Is

A proof-of-concept AI decision-support tool for the San Francisco Municipal Transportation Agency (SFMTA). It helps a non-technical SFMTA director (Karl) identify which SF road locations should be prioritized for safety improvements, based on crash and complaint data. Built by a 4-person student team for the IBM SkillsBuild AI Experiential Learning Lab.

---

## The 5 Components

These names are canonical. Never rename them anywhere in the codebase.

| Component | Type | File |
|---|---|---|
| `DataIngestionModule` | Deterministic module | `pipeline/ingest.py` |
| `RiskScoringModule` | Deterministic module | `pipeline/score.py` |
| `QueryModule` | AI + DB query module | `pipeline/query.py` |
| `FastAPIServer` | REST API server | `api/main.py` |
| `OrchestrateAgent` | IBM watsonx Orchestrate agent | Configured in IBM watsonx Orchestrate UI |

---

## File Structure

```
sfmta-safety-tool/
├── CLAUDE.md
├── .env                 # Never commit — credentials
├── .gitignore
├── requirements.txt
├── run_normal.py        # Local runner: triggers ingest_all() manually against Render DB
│
├── api/                 # Not yet built
│   ├── __init__.py
│   ├── main.py          # FastAPI server — /ingest, /score, /query endpoints
│   └── openapi.yaml     # OpenAPI spec exported for Orchestrate tool import
│
└── pipeline/
    ├── __init__.py
    ├── database.py      # SQLAlchemy models and DB connection — DONE
    ├── ingest.py        # DataIngestionModule — DONE
    ├── score.py         # RiskScoringModule — shell only, needs implementation
    └── query.py         # QueryModule — RAG + Granite call — not yet built
```

---

## Data Sources (confirmed)

Three SF Open Data datasets fetched via Socrata REST API:

| Dataset | Socrata ID | Update Frequency |
|---|---|---|
| Traffic Crashes Resulting in Injury | `ubvf-ztfx` | Quarterly |
| Traffic Crashes Resulting in Fatality | `dau3-4s8f` | Quarterly, 1-month lag |
| SF 311 Cases | `vw6y-z8j6` | Nightly |

Caltrans AADT static CSV — optional, state routes only, one-time download.

---

## Tech Stack (confirmed)

- Python 3.11
- fastapi, uvicorn
- apscheduler
- requests
- pandas
- sqlalchemy, psycopg2-binary
- python-dotenv
- PostgreSQL (Render free tier) — SQLite for local development

---

## IBM Credentials (confirmed working)

```
WATSONX_URL=https://us-south.ml.cloud.ibm.com
WATSONX_PROJECT_ID=<watsonx Challenge Sandbox project ID>
WATSONX_API_KEY=<IBM Cloud API key>
```

- IAM token endpoint: `https://iam.cloud.ibm.com/identity/token`
- Granite API endpoint: `https://us-south.ml.cloud.ibm.com/ml/v1/text/chat?version=2023-05-29`
- Model: `ibm/granite-4-h-small`
- Auth: POST to IAM endpoint with API key to get bearer token; include as `Authorization: Bearer <token>` header

---

## Database Schema (confirmed)

| Table | Key Columns | Purpose |
|---|---|---|
| `crashes_injury` | id, unique_id, collision_date, primary_rd, secondary_rd, tb_latitude, tb_longitude, number_injured, number_killed, collision_severity, type_of_collision, supervisor_district, police_district, analysis_neighborhood, ingested_at | Injury crash records from ubvf-ztfx |
| `crashes_fatality` | id, unique_id, collision_date, latitude, longitude, location, collision_type, supervisor_district, police_district, analysis_neighborhood, ingested_at | Fatality crash records from dau3-4s8f |
| `cases_311` | id, service_request_id, requested_datetime, service_name, service_subtype, address, latitude, longitude, supervisor_district, police_district, neighborhoods, ingested_at | Safety-relevant 311 cases from vw6y-z8j6 |
| `ingest_metadata` | dataset_id, dataset_name, last_synced, record_count | Tracks last sync time per dataset for incremental pulls |
| `scored_zones` | location_name, latitude, longitude, crash_count, fatality_count, complaint_count, recency_score, final_score, last_updated | Ranked priority output from RiskScoringModule |
| `ai_explanations` | location_name, question_asked, explanation, generated_at | Cached Granite explanations |

**Important — `analysis_neighborhood` is null in both crash tables.**
The source datasets (ubvf-ztfx, dau3-4s8f) do not include a neighborhood field.
`score.py` must group locations using `supervisor_district`, `primary_rd` + `secondary_rd` (injury), or `location` (fatality) instead.

---

## Confirmed Technical Rules

**Granite: call directly via requests library.**
Do not use CrewAI, LiteLLM, or langchain-ibm. Call the watsonx.ai REST API directly using an IBM IAM bearer token obtained from the token endpoint.

**IAM token expires after 60 minutes.**
Implement token caching — store the token and its expiry time, refresh only when expired. Do not fetch a new token on every Granite call.

**RAG pattern for all AI calls.**
Never call Granite without data context. Pattern: query `scored_zones` for relevant locations → build prompt with that data → call Granite → return explanation. Granite is never called on a schedule — only on user request.

**Token budget is the top constraint.**
IBM SkillsBuild watsonx.ai credits are limited. Cache Granite outputs in `ai_explanations` table. Never call Granite for output that already exists and is still fresh.

**Socrata API key is not required.**
SF Open Data datasets are public. Do not set `SOCRATA_API_KEY` — the key in the original `.env` was invalid and caused 403 errors. Pass `None` as the app token to `sodapy.Socrata()`. Requests without a key are subject to rate limiting but sufficient for this project.

**Secrets via environment variables only.**
Never hardcode any key, URL, or credential. Always use `os.getenv()`. Never commit `.env` to version control — credentials get deactivated immediately.

**FastAPI generates the OpenAPI spec automatically.**
Run the FastAPI server and export the spec from `/openapi.json`. Import this YAML into IBM watsonx Orchestrate as a tool definition.

**Render free tier sleeps after 15 minutes of inactivity.**
Set up UptimeRobot (free) to ping the Render URL every 5 minutes during demo week.

---

## IBM watsonx Orchestrate (confirmed)

Orchestrate is the user-facing interface. Karl interacts with the system through Orchestrate's chat UI.

- Orchestrate connects to the FastAPI backend via an imported OpenAPI spec
- The spec describes the `/query` endpoint (and optionally `/ingest`, `/score`) as callable tools
- When Karl submits a query, Orchestrate determines which tool to call and passes the parameters
- FastAPI handles the DB query + Granite call and returns a JSON response
- Orchestrate presents the response conversationally to Karl

**To configure:** Import `api/openapi.yaml` into Orchestrate via Build → Tools → Import from file.

---

## 311 Safety Filters (confirmed)

The following `(service_name, service_subtype)` pairs are the only ones ingested from vw6y-z8j6.
These were verified against the live dataset — all other subtypes in the original filter list did not exist.

| service_name | service_subtype |
|---|---|
| Blocked Street and Sidewalk | blocked_sidewalk |
| Blocked Street and Sidewalk | blocked_parking_space_or_strip |
| Street Defect | pavement_defect |
| Street Defect | sidewalk_defect |
| Street Defect | manhole_cover_off |
| Street Defect | curb_or_curb_ramp_defect |
| Sidewalk and Curb | pavement_defect |
| Sidewalk and Curb | sidewalk_defect |
| Sidewalk and Curb | curb_or_curb_ramp_defect |
| Streetlights | light |
| Sewer | flooding |
| Tree Maintenance | damaged_tree |
| Damage Property | traffic_signal |
| Damage Property | transit_shelter_platform_hazardous |

---

## Out of Scope

- Real-time or streaming data (511.org excluded)
- User authentication or accounts
- H3 hexagonal spatial clustering — geographic grouping uses location name/neighborhood from source data
- Streamlit — replaced by IBM watsonx Orchestrate as the user-facing interface
- CrewAI, LiteLLM, langchain-ibm — all excluded
- Mobile UI
- Dollar-amount budget optimization
- Production error handling or SLAs
- Multi-city support
- SFMTA internal system integration

---

## Build Order

1. `pipeline/database.py` — SQLAlchemy models, DB connection, table creation
2. `pipeline/ingest.py` — DataIngestionModule, Socrata fetch + normalize + write to DB
3. `pipeline/score.py` — RiskScoringModule, weighted scoring formula + write scored_zones
4. `pipeline/query.py` — QueryModule, DB query + RAG prompt + Granite call
5. `api/main.py` — FastAPIServer, expose all modules as endpoints + APScheduler
6. `api/openapi.yaml` — Export from FastAPI and import into Orchestrate

---

## Decisions Log

*Append confirmed decisions here as the project progresses. Do not add anything that hasn't been explicitly decided.*

- **2025-04** — Data sources confirmed: ubvf-ztfx, dau3-4s8f, vw6y-z8j6, optional Caltrans AADT
- **2025-04** — 511.org excluded from MVP
- **2025-04** — Hosting: Render free tier (web service + PostgreSQL)
- **2026-04** — Architecture revised: CrewAI/LiteLLM/Streamlit/H3 removed
- **2026-04** — FastAPI + IBM watsonx Orchestrate adopted as backend + UI layer
- **2026-04** — Granite called directly via REST API (no framework wrappers)
- **2026-04** — Confirmed working credentials: us-south.ml.cloud.ibm.com, granite-4-h-small, watsonx Challenge Sandbox project
- **2026-04** — RAG pattern confirmed: DB query → prompt → Granite → explanation
- **2026-04** — SpatialClusteringModule removed; geographic grouping by location name from source data
- **2026-04** — Component count reduced from 6 to 5; OrchestratorAgent and ExplainabilityAgent replaced by OrchestrateAgent (IBM platform) and QueryModule (Python)
- **2026-04** — Real table names confirmed: crashes_injury, crashes_fatality, cases_311, ingest_metadata, scored_zones, ai_explanations
- **2026-04** — scored_zones primary key: location_name (String); all columns confirmed: location_name, latitude, longitude, crash_count, fatality_count, complaint_count, recency_score, final_score, last_updated
- **2026-04** — Local dev: SQLite via sfmta_safety.db (fallback when DATABASE_URL not set); production: PostgreSQL via DATABASE_URL on Render
- **2026-04** — Socrata API key not required; SF Open Data is public; pass None to sodapy.Socrata()
- **2026-04** — 311 safety filters confirmed: 14 (service_name, service_subtype) pairs; original subtype list was invalid
- **2026-04** — analysis_neighborhood is null in all crash records; source datasets don't include neighborhood field; score.py must group by supervisor_district or road name
- **2026-04** — Initial data ingested to Render: 18 fatality crashes, 2365 injury crashes, 46986 311 cases (Apr 2025 – Apr 2026)
