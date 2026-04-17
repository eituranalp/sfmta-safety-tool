import streamlit as st
import pandas as pd
import numpy as np
import folium
from streamlit_folium import st_folium

st.title("🚦 San Francisco Traffic Prioritization Dashboard")

data = pd.DataFrame({
    "Zone": ["Mission", "Sunset", "SoMa"],
    "Priority Score": [0.82, 0.45, 0.63]
})

st.write("Top priority zones:")
st.dataframe(data)

m = folium.Map(location=[37.77, -122.44], zoom_start=12)

folium.Marker([37.76, -122.43], popup="Mission").add_to(m)
folium.Marker([37.75, -122.49], popup="Sunset").add_to(m)

st_folium(m)