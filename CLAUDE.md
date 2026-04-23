# SFMTA Road Safety Prioritization Tool
## Project Context for Claude Code

This file is the source of truth for all confirmed project decisions.
It is updated as decisions are made — do not treat anything not listed here as decided.

---

## What This Project Is

A proof-of-concept AI decision-support tool for the San Francisco Municipal Transportation Agency (SFMTA). It helps a non-technical SFMTA director (Karl) identify which SF road locations should be prioritized for safety improvements, based on crash and complaint data. Built by a 4-person student team for the IBM SkillsBuild AI Experiential Learning Lab. Not production-ready — needs to work for a live demo at Week 10.

---

## The 4 Components

These names are canonical. Never rename them anywhere in the codebase.

| Component | Type | File |
|---|---|---|
| `DataIngestionModule` | Deterministic module | `pipeline/ingest.py` |
| `RiskScoringModule` | Deterministic module | `pipeline/score.py` |
| `FastAPIServer` | REST API server | `api/main.py` |
| `OrchestrateAgent` | IBM watsonx Orchestrate agent | Configured in IBM watsonx Orchestrate UI |

**Note: `QueryModule` and `query.py` have been removed.** Replaced entirely by Orchestrate (AI reasoning + explanation) + FastAPI (data fetching).

**Granite calls now exist in the Python codebase** — `pipeline/briefing.py` calls `ibm/granite-4-h-small` once daily after scoring, and `dashboard/app.py` calls it on-demand when the user clicks Generate Briefing. These are separate from Orchestrate's built-in model.

---

## File Structure

```
sfmta-safety-tool/
├── CLAUDE.md
├── .env                 # Never commit — credentials
├── .gitignore
├── requirements.txt
├── run_normal.py        # Local runner: triggers ingest_all() manually against Render DB
├── run_dashboard.bat    # Local launcher for Streamlit dashboard
│
├── api/
│   ├── __init__.py
│   └── main.py          # FastAPIServer — /query, /ingest, /score, /health, /briefing endpoints
│                        # APScheduler runs daily ingest → score → briefing at 6am Pacific
│
├── dashboard/
│   └── app.py           # Streamlit dashboard — reads scored_zones, on-demand Granite briefing
│                        # Run locally: streamlit run dashboard/app.py
│
└── pipeline/
    ├── __init__.py
    ├── database.py      # SQLAlchemy models and DB connection — DONE
    ├── ingest.py        # DataIngestionModule — DONE
    ├── score.py         # RiskScoringModule — DONE
    └── briefing.py      # Daily Granite briefing — reads top 10 scored_zones, calls ibm/granite-4-h-small,
                         # writes DAILY_BRIEFING row to ai_explanations — DONE
```

---

## System Architecture (confirmed)

```
Karl types question in Orchestrate chat
        ↓
Orchestrate reads tool descriptions in OpenAPI spec
Decides which parameters to pass based on Karl's question
        ↓
Calls GET /query on FastAPI with parameters:
  ?metric=fatality_count&limit=10
  ?street_name=MISSION+ST
  ?lat_min=37.748&lat_max=37.767&lng_min=-122.430&lng_max=-122.400
  (any combination of optional parameters)
        ↓
FastAPI builds SQL query dynamically from parameters
Queries scored_zones table in PostgreSQL on Render
Returns JSON of scored street data
        ↓
Orchestrate receives JSON
Explains results to Karl in plain English
Karl gets actionable answer
```

**Granite calls exist in the Python codebase** via `ibm-watsonx-ai` SDK:
- `pipeline/briefing.py` — called once daily after scoring, result stored in `ai_explanations`
- `dashboard/app.py` — called on-demand when user clicks Generate Briefing, result is ephemeral (session state only)

Orchestrate's built-in model (GPT-OSS 120B) still handles Karl's chat reasoning separately.
FastAPI's `/query` endpoint is SQL-only. `/briefing` endpoint reads from `ai_explanations`.

---

## The /query Endpoint Parameters

All parameters are optional. FastAPI builds SQL dynamically from whatever Orchestrate passes.

| Parameter | Type | Description |
|---|---|---|
| `question` | string | Karl's raw question — informational only, not used for SQL |
| `street_name` | string | Partial street name filter — uses ILIKE match |
| `metric` | string | Column to sort by: final_score, crash_count, fatality_count, complaint_count, recency_score |
| `limit` | int | Number of results (default 10, max 50) |
| `days_recent` | int | Filter to streets with activity in last N days — maps to recency_score >= (days_recent / 365.0) |
| `lat_min` | float | Bounding box minimum latitude |
| `lat_max` | float | Bounding box maximum latitude |
| `lng_min` | float | Bounding box minimum longitude |
| `lng_max` | float | Bounding box maximum longitude |

When no parameters are passed: return `{"count": 0, "data": [], "message": "No query parameters provided."}`

Response always includes: `location_name, crash_count, fatality_count, complaint_count, recency_score, final_score, latitude, longitude`

---

## Spatial Query Approach (confirmed)

For spatial/geographic questions, Orchestrate generates a lat/lng bounding box and passes it to /query. Python applies a 0.02 degree buffer to all Granite-generated boxes before querying. This is post-MVP — the /query endpoint already accepts bounding box params, buffer logic to be added later.

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

## Database Schema (confirmed)

| Table | Key Columns | Purpose |
|---|---|---|
| `crashes_injury` | id, unique_id, collision_date, primary_rd, secondary_rd, tb_latitude, tb_longitude, number_injured, number_killed, collision_severity, type_of_collision, supervisor_district, police_district, analysis_neighborhood, ingested_at | Injury crash records from ubvf-ztfx |
| `crashes_fatality` | id, unique_id, collision_date, latitude, longitude, location, collision_type, supervisor_district, police_district, analysis_neighborhood, ingested_at | Fatality crash records from dau3-4s8f |
| `cases_311` | id, service_request_id, requested_datetime, service_name, service_subtype, address, latitude, longitude, supervisor_district, police_district, neighborhoods, ingested_at | Safety-relevant 311 cases from vw6y-z8j6 |
| `ingest_metadata` | dataset_id, dataset_name, last_synced, record_count | Tracks last sync time per dataset for incremental pulls |
| `scored_zones` | location_name, latitude, longitude, crash_count, fatality_count, complaint_count, recency_score, final_score, last_updated | Ranked priority output from RiskScoringModule — primary data source for /query |
| `ai_explanations` | location_name, question_asked, explanation, generated_at | Stores daily Granite briefing — one row with location_name = 'DAILY_BRIEFING', replaced each run |

**Important — `analysis_neighborhood` is null in both crash tables.**
The source datasets (ubvf-ztfx, dau3-4s8f) do not include a neighborhood field.
`score.py` must group locations by street name extracted from:
- crashes_injury → primary_rd (already clean, uppercase)
- crashes_fatality → location (extract first street before "near", "at", "/", ",")
- cases_311 → address (strip leading house number)

---

## score.py Grouping (confirmed)

Group all records by normalized street name. One row in scored_zones per street.
location_name = clean uppercase street name e.g. "MISSION ST"

Scoring formula:
- recency_score = recent_count / total_count (recent = last 90 days)
- raw = (crash_count * 0.4) + (fatality_count * 3.5) + (complaint_count * 0.1) + (recency_score * 20)
- final_score = (raw / max_raw_across_all_streets) * 100

Filter out streets with fewer than 3 total records before scoring.
Use if_exists='replace' when writing to scored_zones — wipe and rewrite every run.

---

## Confirmed Technical Rules

**Granite calls in Python are scoped to briefing only.**
`pipeline/briefing.py` and `dashboard/app.py` call `ibm/granite-4-h-small` via `ibm-watsonx-ai`.
FastAPI `/query` endpoint remains SQL-only. No Granite calls in ingest or scoring logic.

**Socrata API key is not required.**
SF Open Data datasets are public. Pass None as the app token to sodapy.Socrata().
Requests without a key are subject to rate limiting but sufficient for this project.

**Secrets via environment variables only.**
Never hardcode any key, URL, or credential. Always use os.getenv().
Never commit .env to version control — credentials get deactivated immediately.

**FastAPI generates the OpenAPI spec automatically.**
Run the FastAPI server and export the spec from /openapi.json.
Import this JSON into IBM watsonx Orchestrate as a tool definition.
No need to maintain a separate openapi.yaml file.

**Render free tier sleeps after 15 minutes of inactivity.**
UptimeRobot (free) pings /health every 5 minutes to keep the service awake.
APScheduler runs inside the FastAPI process — it fires reliably as long as the service stays awake.

**SQL injection prevention.**
Validate metric parameter against explicit allowlist before using in ORDER BY:
VALID_METRICS = {final_score, crash_count, fatality_count, complaint_count, recency_score}

**CORS must be enabled.**
Orchestrate calls FastAPI from IBM's servers — allow_origins=["*"] required.

---

## IBM watsonx Orchestrate (confirmed)

Orchestrate is the user-facing interface and AI reasoning layer.
Karl interacts with the system through Orchestrate's chat UI.

**Confirmed behavior (tested):**
- Orchestrate calls external HTTP endpoints via imported OpenAPI tools
- It reads tool descriptions and picks the right tool + parameters based on Karl's question
- It receives JSON from FastAPI and explains results to Karl in plain English
- Tool description quality directly determines routing accuracy — descriptions must be Karl-like
- Orchestrate cannot connect to PostgreSQL directly — FastAPI is the required bridge

**Model in use:** GPT-OSS 120B (Orchestrate's built-in model)
**Note:** Change model to a Granite model before final submission for IBM evaluation.

**To configure:** Export OpenAPI spec from http://localhost:8000/openapi.json, import into Orchestrate via Build → Agents → Toolset → Add tool → OpenAPI.

**Agent instructions (confirmed):**
You are Karl the Fog, a road safety analyst assistant for the San Francisco Municipal Transportation Agency (SFMTA). You help Karl, the SFMTA director, understand which streets in San Francisco need safety improvements based on crash and complaint data. Your job is to answer Karl's questions clearly and in plain English. Karl is not technical — avoid jargon, be direct, and always explain why a location is a priority using the data available. When Karl asks about road safety priorities, locations, or data, use the query tool to fetch and explain the relevant information. Always base your answers on the data returned by the tool — never invent or assume facts. If the tool returns no data, tell Karl clearly that no data is available yet. Keep responses concise — 2 to 4 sentences per location.

## OpenAPI Spec — When to Re-import into Orchestrate

Re-import required when: new endpoint added, endpoint deleted, /query parameters added/renamed/removed, response schema changed.

Not required when: bug fixes, SQL changes, score formula changes, ingestion logic changes.

To re-import: download openapi.json from https://sfmta-safety-tool.onrender.com/openapi.json, go to Orchestrate agent Toolset, delete existing Query tool, re-import file, select Query only, redeploy agent.

---

## 311 Safety Filters (confirmed)

The following (service_name, service_subtype) pairs are the only ones ingested from vw6y-z8j6.
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
- H3 hexagonal spatial clustering — geographic grouping uses street name from source data
- CrewAI, LiteLLM, langchain-ibm — all excluded
- Granite calls in ingest/scoring/query logic — briefing only
- query.py / QueryModule — replaced by Orchestrate + FastAPI
- Mobile UI
- Dollar-amount budget optimization
- Production error handling or SLAs
- Multi-city support
- SFMTA internal system integration
- Spatial query buffer logic (post-MVP)

---

## Build Order

1. `pipeline/database.py` — SQLAlchemy models, DB connection, table creation — DONE
2. `pipeline/ingest.py` — DataIngestionModule, Socrata fetch + normalize + write to DB — DONE
3. `pipeline/score.py` — RiskScoringModule, street-level scoring + write scored_zones — DONE
4. `api/main.py` — FastAPIServer, SQL query endpoints + APScheduler — DONE
5. Deploy to Render + UptimeRobot — DONE
6. Orchestrate agent configuration — DONE
7. `pipeline/briefing.py` — daily Granite briefing after scoring, stored in ai_explanations — DONE
8. `dashboard/app.py` — Streamlit dashboard with on-demand Granite briefing — DONE
9. End to end test with real scored data — DONE (1957 streets scored, briefing generated)
10. Demo preparation — Week 9-10
11. Pitch deck and documentation — Week 9-10

---

## Current Data on Render (confirmed April 2026)

| Table | Records | Date Range |
|---|---|---|
| crashes_fatality | 18 | Apr 2025 – Apr 2026 |
| crashes_injury | 2,365 | Apr 2025 – Apr 2026 |
| cases_311 | 46,986 | Apr 2025 – Apr 2026 |
| scored_zones | 1,957 streets | Apr 2025 – Apr 2026 |

Database: Render PostgreSQL at oregon-postgres.render.com/karls_db

---

## Decisions Log

*Append confirmed decisions here as the project progresses. Do not add anything that hasn't been explicitly decided.*

- **2025-04** — Data sources confirmed: ubvf-ztfx, dau3-4s8f, vw6y-z8j6, optional Caltrans AADT
- **2025-04** — 511.org excluded from MVP
- **2025-04** — Hosting: Render free tier (web service + PostgreSQL)
- **2026-04** — Architecture revised: CrewAI/LiteLLM/Streamlit/H3 removed
- **2026-04** — FastAPI + IBM watsonx Orchestrate adopted as backend + UI layer
- **2026-04** — Confirmed working IBM credentials: us-south.ml.cloud.ibm.com, granite-4-h-small, watsonx Challenge Sandbox project
- **2026-04** — SpatialClusteringModule removed; geographic grouping by street name from source data
- **2026-04** — Component count reduced from 5 to 4; QueryModule/query.py removed entirely
- **2026-04** — Granite/LLM calls removed from Python codebase; Orchestrate handles all AI reasoning
- **2026-04** — FastAPI is SQL-only bridge between Orchestrate and PostgreSQL
- **2026-04** — Orchestrate confirmed capable of calling external HTTP endpoints and explaining JSON results
- **2026-04** — Orchestrate tool description quality determines routing accuracy — must use Karl-like language
- **2026-04** — /query endpoint accepts optional params: street_name, metric, limit, lat_min, lat_max, lng_min, lng_max
- **2026-04** — Real table names confirmed: crashes_injury, crashes_fatality, cases_311, ingest_metadata, scored_zones, ai_explanations
- **2026-04** — scored_zones primary key: location_name (String); columns: location_name, latitude, longitude, crash_count, fatality_count, complaint_count, recency_score, final_score, last_updated
- **2026-04** — score.py groups by street name (not supervisor_district); extracted from primary_rd, location, address fields
- **2026-04** — score.py scoring formula confirmed: recency = recent/total; final = weighted composite normalized to 0-100
- **2026-04** — Minimum 3 records threshold for scoring to prevent single-incident streets inflating scores
- **2026-04** — Local dev: SQLite via sfmta_safety.db fallback; production: PostgreSQL via DATABASE_URL on Render
- **2026-04** — Socrata API key not required; pass None to sodapy.Socrata()
- **2026-04** — 311 safety filters confirmed: 14 (service_name, service_subtype) pairs
- **2026-04** — analysis_neighborhood is null in all crash records
- **2026-04** — Initial data ingested to Render: 18 fatality crashes, 2365 injury crashes, 46986 311 cases (Apr 2025 – Apr 2026)
- **2026-04** — Spatial queries: Orchestrate generates lat/lng bounding box, passes to /query, 0.02 degree buffer applied in Python (post-MVP)
- **2026-04** — UptimeRobot pings /health every 5 minutes to keep Render awake; APScheduler fires daily at 6am Pacific inside FastAPI process
- **2026-04** — ai_explanations table currently unused; was for Granite caching, may be repurposed or removed
- **2026-04** — Orchestrate agent model must be changed to Granite before final submission for IBM evaluation
- **2026-04** — query.py removed from project entirely; replaced by Orchestrate + FastAPI
- **2026-04** — No Granite calls in Python; Orchestrate built-in model handles all AI reasoning
- **2026-04** — Orchestrate agent configured: SFMTA_Safety_Tool; Query tool imported from real OpenAPI spec
- **2026-04** — /query endpoint parameters confirmed: street_name, metric, limit, days_recent, lat_min, lat_max, lng_min, lng_max
- **2026-04** — days_recent filter uses recency_score >= (days_recent / 365.0)
- **2026-04** — APScheduler daily_pipeline wired: ingest runs first, score runs after, early return if ingest fails
- **2026-04** — /score endpoint auto-activates when score.py adds score() method, no main.py changes needed
- **2026-04** — Orchestrate Behavior instructions updated: explains WHY not just WHAT, compares streets with tradeoffs, mentions High Injury Network
- **2026-04** — on_vz_hin_2022 not in current schema or ingestion; deferred post-MVP
- **2026-04** — FastAPI servers field added to OpenAPI spec for Orchestrate import compatibility
- **2026-04** — UptimeRobot confirmed working; HEAD method accepted by /health endpoint
- **2026-04** — Render auto-deploy on GitHub push confirmed working
- **2026-04** — score.py completed and run successfully; scored_zones populated with 1,957 streets
- **2026-04** — score.py fatality weight confirmed as 3.5 (not 3.0 as originally planned)
- **2026-04** — pipeline/briefing.py added: reads top 10 from scored_zones, calls ibm/granite-4-h-small, writes DAILY_BRIEFING row to ai_explanations; runs after scoring in daily_pipeline
- **2026-04** — ibm-watsonx-ai package added to requirements.txt
- **2026-04** — Granite model ID requires ibm/ prefix: correct ID is ibm/granite-4-h-small
- **2026-04** — ai_explanations now actively used; DAILY_BRIEFING row replaced on each daily run
- **2026-04** — /briefing GET endpoint added to FastAPIServer; returns stored explanation and generated_at
- **2026-04** — daily_pipeline order confirmed: ingest → score → briefing; each step returns early on failure
- **2026-04** — Streamlit dashboard added at dashboard/app.py; reads scored_zones via SQLAlchemy; run locally with run_dashboard.bat
- **2026-04** — Dashboard map uses folium CircleMarkers on CartoDB dark_matter tiles; radius scaled by score; top-N cap slider in sidebar
- **2026-04** — Dashboard has on-demand Granite briefing: calls ibm/granite-4-h-small directly from Streamlit using current slider weights; result stored in st.session_state only, never written to DB
- **2026-04** — Dashboard briefing is independent from pipeline DAILY_BRIEFING: different formula (slider-normalized weights vs fixed pipeline weights), different trigger (on-demand vs daily), different storage (session state vs DB)
- **2026-04** — Dashboard briefing prompt includes current normalized weight percentages so Granite explains results in terms of the user's weighting decision
- **2026-04** — Stale warning shown in dashboard when sliders change after briefing was generated
- **2026-04** — Orchestrate /briefing endpoint serves pipeline DAILY_BRIEFING only; dashboard briefing is never exposed via API
