import os
import streamlit as st
import pandas as pd
import folium
from streamlit_folium import st_folium
from sqlalchemy import create_engine
from dotenv import load_dotenv

load_dotenv()

# -------------------------------------------------
# Page setup
# -------------------------------------------------
st.set_page_config(
    page_title="SF Traffic Prioritization Dashboard",
    layout="wide",
    initial_sidebar_state="expanded"
)

# -------------------------------------------------
# Dark dashboard styling
# -------------------------------------------------
st.markdown("""
<style>
    .stApp {
        background-color: #050816;
        color: white;
    }

    html, body, [class*="css"] {
        background-color: #050816;
    }

    /* Remove top white header area */
    header[data-testid="stHeader"] {
        background: #050816 !important;
    }

    div[data-testid="stToolbar"] {
        visibility: hidden;
        height: 0%;
        position: fixed;
    }

    /* Main container */
    .block-container {
        padding-top: 1.2rem !important;
        padding-bottom: 1.5rem !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
        max-width: 100% !important;
    }

    /* Sidebar */
    section[data-testid="stSidebar"] {
        background-color: #050816 !important;
        border-right: 1px solid #18213a;
    }

    section[data-testid="stSidebar"] * {
        color: white !important;
    }

    /* Text */
    h1, h2, h3, h4, h5, h6, p, div, span, label {
        color: white !important;
    }

    /* Dataframe */
    div[data-testid="stDataFrame"] {
        border: 1px solid #333333;
        border-radius: 10px;
        overflow: hidden;
        background-color: #1c1c1c;
    }

    /* Cards */
    .metric-card {
        background: #0d1325;
        border: 1px solid #2a3555;
        border-radius: 14px;
        padding: 18px 20px;
        margin-bottom: 14px;
    }

    .metric-title {
        font-size: 15px;
        color: #b8c3e0 !important;
        margin-bottom: 6px;
    }

    .metric-value {
        font-size: 28px;
        font-weight: 700;
        color: white !important;
        margin-bottom: 2px;
    }

    .row-card {
        background: #0d1325;
        border: 1px solid #2a3555;
        border-radius: 16px;
        padding: 20px;
        margin-top: 10px;
    }

    .row-grid {
        display: grid;
        grid-template-columns: 1fr 1fr;
        gap: 14px;
        margin-top: 14px;
    }

    .row-item {
        background: #121a31;
        border-radius: 12px;
        padding: 12px 14px;
        border: 1px solid #253150;
    }

    .row-label {
        font-size: 13px;
        color: #9fb0d9 !important;
        margin-bottom: 6px;
    }

    .row-value {
        font-size: 22px;
        font-weight: 700;
        color: white !important;
        line-height: 1.2;
        word-break: break-word;
    }

    .alert-high {
        background: rgba(180, 40, 40, 0.22);
        border: 1px solid rgba(255, 90, 90, 0.35);
        color: #ffd9d9 !important;
        border-radius: 12px;
        padding: 14px 16px;
        margin-top: 16px;
        font-weight: 600;
    }

    .alert-medium {
        background: rgba(184, 120, 20, 0.20);
        border: 1px solid rgba(255, 190, 80, 0.35);
        color: #ffe9bf !important;
        border-radius: 12px;
        padding: 14px 16px;
        margin-top: 16px;
        font-weight: 600;
    }

    .alert-low {
        background: rgba(35, 90, 170, 0.18);
        border: 1px solid rgba(100, 160, 255, 0.35);
        color: #dcecff !important;
        border-radius: 12px;
        padding: 14px 16px;
        margin-top: 16px;
        font-weight: 600;
    }

    /* Map container */
    .map-wrapper {
        width: 100%;
        border-radius: 12px;
        overflow: hidden;
        border: 1px solid #24304f;
        background: #0d1325;
        padding: 0;
        margin-top: 8px;
    }

    iframe {
        border-radius: 12px !important;
    }

    /* Hide only the collapse button inside the sidebar — keep expand button visible */
    button[data-testid="stSidebarCollapseButton"] {
        display: none !important;
    }

    /* Generate Briefing button — always active-looking */
    div[data-testid="stButton"] > button {
        background: linear-gradient(135deg, #0f2550, #1a3f8f) !important;
        border: 1px solid #3a6ad4 !important;
        color: white !important;
        font-weight: 600 !important;
        width: 100% !important;
        transition: box-shadow 0.2s, border-color 0.2s !important;
    }
    div[data-testid="stButton"] > button:hover {
        border-color: #6a9ae9 !important;
        box-shadow: 0 0 12px rgba(74, 122, 217, 0.5) !important;
    }

    .stale-warning {
        background: rgba(184, 120, 20, 0.18);
        border: 1px solid rgba(255, 190, 80, 0.4);
        color: #ffe9bf !important;
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 13px;
        font-weight: 500;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

st.title("SF Road Safety Prioritization")
st.caption("Crash and complaint data · San Francisco · Updated daily")

# -------------------------------------------------
# Database connection
# -------------------------------------------------
_db_url = os.getenv("DATABASE_URL", "sqlite:///./sfmta_safety.db")
_engine = create_engine(_db_url, echo=False)

# -------------------------------------------------
# Load data from scored_zones
# -------------------------------------------------
@st.cache_data
def load_data():
    df = pd.read_sql("SELECT location_name, latitude AS lat, longitude AS lng, crash_count, fatality_count, complaint_count FROM scored_zones", _engine)
    df["crash_count"] = df["crash_count"].astype(int)
    df["fatality_count"] = df["fatality_count"].astype(int)
    df["complaint_count"] = df["complaint_count"].astype(int)
    return df

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def max_normalize(series):
    max_val = series.max()
    if max_val == 0:
        return pd.Series([0.0] * len(series), index=series.index)
    return series / max_val

def classify_priority(score):
    if score >= 0.75:
        return "HIGH"
    elif score >= 0.45:
        return "MEDIUM"
    return "LOW"

def get_priority_color(priority_level):
    if priority_level == "HIGH":
        return "#ff4040"
    elif priority_level == "MEDIUM":
        return "#f5a623"
    return "#4a90d9"

# -------------------------------------------------
# Load data
# -------------------------------------------------
try:
    data = load_data()
except Exception as e:
    st.error(f"Could not load data from scored_zones: {e}")
    st.exception(e)
    st.stop()

# -------------------------------------------------
# Sidebar controls
# -------------------------------------------------
st.sidebar.header("Scoring Weights")

crash_weight = st.sidebar.slider("Crash Weight", 0.0, 1.0, 0.4, 0.05)
fatality_weight = st.sidebar.slider("Fatality Weight", 0.0, 1.0, 0.4, 0.05)
complaint_weight = st.sidebar.slider("Complaint Weight", 0.0, 1.0, 0.2, 0.05)

weight_total = crash_weight + fatality_weight + complaint_weight

if weight_total == 0:
    st.sidebar.error("At least one weight must be greater than 0.")
    st.stop()

crash_weight_norm = crash_weight / weight_total
fatality_weight_norm = fatality_weight / weight_total
complaint_weight_norm = complaint_weight / weight_total

st.sidebar.subheader("Map Display")
map_limit = st.sidebar.slider("Markers on map (top N by score)", 10, 200, 100, 10)

st.sidebar.subheader("Weight Breakdown")
st.sidebar.markdown(
    f"""
    <div style="border-radius:6px; overflow:hidden; height:10px; display:flex; margin-bottom:6px;">
        <div style="width:{crash_weight_norm:.0%}; background:#fbbf24;" title="Crashes"></div>
        <div style="width:{fatality_weight_norm:.0%}; background:#2dd4bf;" title="Fatalities"></div>
        <div style="width:{complaint_weight_norm:.0%}; background:#e879f9;" title="Complaints"></div>
    </div>
    <div style="display:flex; justify-content:space-between; font-size:12px; color:#9fb0d9;">
        <span style="color:#fbbf24;">&#9632;</span> Crashes {crash_weight_norm:.0%}&nbsp;&nbsp;
        <span style="color:#2dd4bf;">&#9632;</span> Fatalities {fatality_weight_norm:.0%}&nbsp;&nbsp;
        <span style="color:#e879f9;">&#9632;</span> Complaints {complaint_weight_norm:.0%}
    </div>
    """,
    unsafe_allow_html=True,
)

# -------------------------------------------------
# Score computation
# -------------------------------------------------
data["crash_norm"] = max_normalize(data["crash_count"])
data["fatality_norm"] = max_normalize(data["fatality_count"])
data["complaint_norm"] = max_normalize(data["complaint_count"])

data["recency_score"] = (
    data["crash_norm"] * crash_weight_norm +
    data["fatality_norm"] * fatality_weight_norm +
    data["complaint_norm"] * complaint_weight_norm
).round(2)

data["priority_level"] = data["recency_score"].apply(classify_priority)

# -------------------------------------------------
# Final table
# -------------------------------------------------
output_df = data[[
    "location_name",
    "lat",
    "lng",
    "crash_count",
    "fatality_count",
    "complaint_count",
    "recency_score",
    "priority_level"
]].copy()

output_df = output_df.sort_values(by="recency_score", ascending=False).reset_index(drop=True)

display_df = output_df[[
    "location_name",
    "lat",
    "lng",
    "crash_count",
    "fatality_count",
    "complaint_count",
    "recency_score"
]].copy()

display_df["lat"] = display_df["lat"].round(4)
display_df["lng"] = display_df["lng"].round(4)
display_df["recency_score"] = display_df["recency_score"].round(2)

top_row = output_df.iloc[0]

# -------------------------------------------------
# Layout
# -------------------------------------------------
left_col, right_col = st.columns([1.7, 1.3])

# -------------------------------------------------
# Left side
# -------------------------------------------------
with left_col:
    st.dataframe(display_df, use_container_width=True, hide_index=True)


    sf_map = folium.Map(
        location=[37.76, -122.44],
        zoom_start=12,
        tiles="CartoDB dark_matter",
        control_scale=True
    )

    map_df = output_df.head(map_limit)

    for _, row in map_df.iterrows():
        color = get_priority_color(row["priority_level"])
        popup_text = (
            f"<b>{row['location_name']}</b><br>"
            f"Priority: <b>{row['priority_level']}</b><br>"
            f"Score: {row['recency_score']:.2f}<br>"
            f"Crashes: {row['crash_count']}<br>"
            f"Fatalities: {row['fatality_count']}<br>"
            f"Complaints: {row['complaint_count']}"
        )
        radius = 5 + row["recency_score"] * 10

        folium.CircleMarker(
            location=[row["lat"], row["lng"]],
            radius=radius,
            color=color,
            fill=True,
            fill_color=color,
            fill_opacity=0.75,
            weight=1.5,
            popup=folium.Popup(popup_text, max_width=220),
            tooltip=row["location_name"],
        ).add_to(sf_map)

    st.markdown('<div class="map-wrapper">', unsafe_allow_html=True)
    st_folium(
        sf_map,
        use_container_width=True,
        height=540,
        returned_objects=[]
    )
    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------------------------------
# Right side
# -------------------------------------------------
with right_col:
    st.subheader("Decision Support Panel")

    st.markdown("### AI Briefing")

    current_weights = (crash_weight_norm, fatality_weight_norm, complaint_weight_norm)
    briefing_weights = st.session_state.get("briefing_weights")
    is_stale = briefing_weights is not None and briefing_weights != current_weights

    if is_stale:
        st.markdown(
            '<div class="stale-warning">↻ Weights changed — regenerate for latest</div>',
            unsafe_allow_html=True,
        )

    if st.button("Generate Briefing"):
        top10 = output_df.head(10)
        lines = []
        for _, row in top10.iterrows():
            lines.append(
                f"- {row['location_name']}: {int(row['crash_count'])} crashes, "
                f"{int(row['fatality_count'])} fatalities, {int(row['complaint_count'])} complaints, "
                f"weighted score {row['recency_score']:.2f}"
            )
        data_block = "\n".join(lines)
        prompt = (
            "You are a road safety analyst for the San Francisco Municipal Transportation Agency (SFMTA). "
            "Based on cumulative road safety data from the past year, write a 3-sentence briefing "
            "for a non-technical director identifying the highest priority streets and what is driving their scores. "
            f"The analyst has applied custom weights: crashes {crash_weight_norm:.0%}, "
            f"fatalities {fatality_weight_norm:.0%}, complaints {complaint_weight_norm:.0%}. "
            "Be specific about which streets have fatalities vs high complaint volume. "
            "Do not use jargon.\n\n"
            f"Top 10 streets by weighted risk score:\n{data_block}"
        )
        try:
            from ibm_watsonx_ai import Credentials
            from ibm_watsonx_ai.foundation_models import ModelInference

            with st.spinner("Generating briefing..."):
                credentials = Credentials(
                    url=os.getenv("WATSONX_URL"),
                    api_key=os.getenv("WATSONX_API_KEY"),
                )
                model = ModelInference(
                    model_id="ibm/granite-4-h-small",
                    credentials=credentials,
                    project_id=os.getenv("WATSONX_PROJECT_ID"),
                    params={"max_new_tokens": 300, "temperature": 0.3},
                )
                st.session_state["dashboard_briefing"] = model.generate_text(prompt=prompt)
                st.session_state["briefing_weights"] = (crash_weight_norm, fatality_weight_norm, complaint_weight_norm)
        except Exception as e:
            st.error(f"Granite call failed: {e}")

    if "dashboard_briefing" in st.session_state:
        c, f, co = st.session_state["briefing_weights"]
        st.markdown(
            f"""
            <div class="row-card" style="margin-top: 10px;">
                <div class="row-label">Granite — crashes {c:.0%} / fatalities {f:.0%} / complaints {co:.0%}</div>
                <p style="color: white; font-size: 14px; line-height: 1.7; margin-top: 8px;">{st.session_state["dashboard_briefing"]}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.divider()
    st.markdown("### Top Priority Street")

    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">Highest Risk Location</div>
            <div class="metric-value">{top_row['location_name']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="row-card">
            <div class="row-grid">
                <div class="row-item">
                    <div class="row-label">Street</div>
                    <div class="row-value">{top_row['location_name']}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">Priority</div>
                    <div class="row-value">{top_row['priority_level']}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">Crashes</div>
                    <div class="row-value">{int(top_row['crash_count'])}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">Fatalities</div>
                    <div class="row-value">{int(top_row['fatality_count'])}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">Complaints</div>
                    <div class="row-value">{int(top_row['complaint_count'])}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">Recent Activity</div>
                    <div class="row-value">{float(top_row['recency_score']):.2f}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">Latitude</div>
                    <div class="row-value">{float(top_row['lat']):.4f}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">Longitude</div>
                    <div class="row-value">{float(top_row['lng']):.4f}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

# -------------------------------------------------
# Raw data
# -------------------------------------------------
with st.expander("Show raw output data"):
    st.dataframe(output_df, use_container_width=True, hide_index=True)

