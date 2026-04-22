import streamlit as st
import pandas as pd
import sqlite3
import folium
from streamlit_folium import st_folium

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
        height: 0rem !important;
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
</style>
""", unsafe_allow_html=True)

st.title("🚦 San Francisco Traffic Prioritization Dashboard")
st.write("Weighted scoring dashboard using your SF safety database.")

# -------------------------------------------------
# Database path
# -------------------------------------------------
DB_PATH = "/Users/yokolu/Desktop/sfmta_safety.db"

# -------------------------------------------------
# Approximate district coordinates and names
# -------------------------------------------------
district_coords = {
    "1": (37.7800, -122.4820),
    "2": (37.7970, -122.4380),
    "3": (37.7940, -122.4100),
    "4": (37.7520, -122.4940),
    "5": (37.7730, -122.4460),
    "6": (37.7780, -122.4140),
    "7": (37.7340, -122.4660),
    "8": (37.7520, -122.4340),
    "9": (37.7430, -122.4160),
    "10": (37.7300, -122.3920),
    "11": (37.7170, -122.4470)
}

district_names = {
    "1": "Richmond District",
    "2": "Marina",
    "3": "Chinatown",
    "4": "Sunset District",
    "5": "Haight-Ashbury",
    "6": "SoMa",
    "7": "West Portal",
    "8": "Castro",
    "9": "Mission District",
    "10": "Bayview",
    "11": "Excelsior"
}

# -------------------------------------------------
# Load data from SQLite
# -------------------------------------------------
@st.cache_data
def load_data():
    conn = sqlite3.connect(DB_PATH)

    complaints_df = pd.read_sql_query("""
        SELECT
            CAST(supervisor_district AS TEXT) AS location,
            COUNT(*) AS complaint_count
        FROM cases_311
        WHERE supervisor_district IS NOT NULL
        GROUP BY CAST(supervisor_district AS TEXT)
    """, conn)

    crashes_df = pd.read_sql_query("""
        SELECT
            CAST(supervisor_district AS TEXT) AS location,
            COUNT(*) AS crash_count
        FROM crashes_injury
        WHERE supervisor_district IS NOT NULL
        GROUP BY CAST(supervisor_district AS TEXT)
    """, conn)

    fatalities_df = pd.read_sql_query("""
        SELECT
            CAST(supervisor_district AS TEXT) AS location,
            COUNT(*) AS fatality_count
        FROM crashes_fatality
        WHERE supervisor_district IS NOT NULL
        GROUP BY CAST(supervisor_district AS TEXT)
    """, conn)

    conn.close()

    def normalize_location(value):
        try:
            number = float(value)
            if number.is_integer():
                return str(int(number))
        except Exception:
            pass
        return str(value)

    complaints_df["location"] = complaints_df["location"].apply(normalize_location)
    crashes_df["location"] = crashes_df["location"].apply(normalize_location)
    fatalities_df["location"] = fatalities_df["location"].apply(normalize_location)

    merged_df = complaints_df.merge(crashes_df, on="location", how="outer")
    merged_df = merged_df.merge(fatalities_df, on="location", how="outer")
    merged_df = merged_df.fillna(0)

    merged_df["complaint_count"] = merged_df["complaint_count"].astype(int)
    merged_df["crash_count"] = merged_df["crash_count"].astype(int)
    merged_df["fatality_count"] = merged_df["fatality_count"].astype(int)

    merged_df["location_name"] = merged_df["location"].map(
        lambda x: district_names.get(x, f"Supervisor District {x}")
    )
    merged_df["lat"] = merged_df["location"].map(
        lambda x: district_coords.get(x, (37.7600, -122.4400))[0]
    )
    merged_df["lng"] = merged_df["location"].map(
        lambda x: district_coords.get(x, (37.7600, -122.4400))[1]
    )

    return merged_df

# -------------------------------------------------
# Helpers
# -------------------------------------------------
def min_max_normalize(series):
    min_val = series.min()
    max_val = series.max()
    if max_val == min_val:
        return pd.Series([1.0] * len(series), index=series.index)
    return (series - min_val) / (max_val - min_val)

def classify_priority(score):
    if score >= 0.75:
        return "HIGH"
    elif score >= 0.45:
        return "MEDIUM"
    return "LOW"

def get_priority_color(priority_level):
    if priority_level == "HIGH":
        return "red"
    elif priority_level == "MEDIUM":
        return "orange"
    return "blue"

# -------------------------------------------------
# Load data
# -------------------------------------------------
try:
    data = load_data()
except Exception as e:
    st.error(f"Could not read database file at: {DB_PATH}")
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

st.sidebar.subheader("Normalized Weights")
st.sidebar.write(f"Crash: {crash_weight_norm:.2f}")
st.sidebar.write(f"Fatality: {fatality_weight_norm:.2f}")
st.sidebar.write(f"Complaint: {complaint_weight_norm:.2f}")

# -------------------------------------------------
# Score computation
# -------------------------------------------------
data["crash_norm"] = min_max_normalize(data["crash_count"])
data["fatality_norm"] = min_max_normalize(data["fatality_count"])
data["complaint_norm"] = min_max_normalize(data["complaint_count"])

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
left_col, right_col = st.columns([2.2, 1.05])

# -------------------------------------------------
# Left side
# -------------------------------------------------
with left_col:
    st.subheader("Prioritized Output")
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.subheader("Map View")

    sf_map = folium.Map(
        location=[37.76, -122.44],
        zoom_start=12,
        control_scale=True
    )

    for _, row in output_df.iterrows():
        popup_text = (
            f"Location: {row['location_name']}<br>"
            f"Crash Count: {row['crash_count']}<br>"
            f"Fatality Count: {row['fatality_count']}<br>"
            f"Complaint Count: {row['complaint_count']}<br>"
            f"Recency Score: {row['recency_score']:.2f}<br>"
            f"Priority: {row['priority_level']}"
        )

        folium.Marker(
            location=[row["lat"], row["lng"]],
            popup=folium.Popup(popup_text, max_width=300),
            icon=folium.Icon(color=get_priority_color(row["priority_level"]))
        ).add_to(sf_map)

    st.markdown('<div class="map-wrapper">', unsafe_allow_html=True)
    st_folium(
        sf_map,
        use_container_width=True,
        height=470,
        returned_objects=[]
    )
    st.markdown('</div>', unsafe_allow_html=True)

# -------------------------------------------------
# Right side
# -------------------------------------------------
with right_col:
    st.subheader("Decision Support Panel")

    st.markdown(
        f"""
        <div class="metric-card">
            <div class="metric-title">Top Priority Location</div>
            <div class="metric-value">{top_row['location_name']}</div>
        </div>
        """,
        unsafe_allow_html=True
    )

    st.markdown("### Output Row")

    st.markdown(
        f"""
        <div class="row-card">
            <div class="row-grid">
                <div class="row-item">
                    <div class="row-label">location_name</div>
                    <div class="row-value">{top_row['location_name']}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">recency_score</div>
                    <div class="row-value">{float(top_row['recency_score']):.2f}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">lat</div>
                    <div class="row-value">{float(top_row['lat']):.4f}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">lng</div>
                    <div class="row-value">{float(top_row['lng']):.4f}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">crash_count</div>
                    <div class="row-value">{int(top_row['crash_count'])}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">fatality_count</div>
                    <div class="row-value">{int(top_row['fatality_count'])}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">complaint_count</div>
                    <div class="row-value">{int(top_row['complaint_count'])}</div>
                </div>
                <div class="row-item">
                    <div class="row-label">priority_level</div>
                    <div class="row-value">{top_row['priority_level']}</div>
                </div>
            </div>
        </div>
        """,
        unsafe_allow_html=True
    )

    if top_row["priority_level"] == "HIGH":
        st.markdown(
            '<div class="alert-high">Immediate intervention recommended.</div>',
            unsafe_allow_html=True
        )
    elif top_row["priority_level"] == "MEDIUM":
        st.markdown(
            '<div class="alert-medium">Monitor conditions closely.</div>',
            unsafe_allow_html=True
        )
    else:
        st.markdown(
            '<div class="alert-low">Normal conditions.</div>',
            unsafe_allow_html=True
        )

    st.markdown("### Weight Summary")
    st.write(f"Crash Weight: {crash_weight_norm:.2f}")
    st.write(f"Fatality Weight: {fatality_weight_norm:.2f}")
    st.write(f"Complaint Weight: {complaint_weight_norm:.2f}")

# -------------------------------------------------
# Raw data
# -------------------------------------------------
with st.expander("Show raw output data"):
    st.dataframe(output_df, use_container_width=True, hide_index=True)
