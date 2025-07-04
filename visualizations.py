import folium
from folium.plugins import MarkerCluster
from streamlit_folium import st_folium
import pandas as pd
import streamlit as st

def render_map():
    if "latest_edited" not in st.session_state or st.session_state.latest_edited.empty:
        return

    df = st.session_state.latest_edited.copy()
    df = df.dropna(subset=["Latitude - Functional Location", "Longitude - Functional Location"]).reset_index(drop=True)
    df["row_id"] = df.index  # Para poder identificar la fila

    # Crear mapa centrado en el centro de los puntos
    lat_center = df["Latitude - Functional Location"].mean()
    lon_center = df["Longitude - Functional Location"].mean()

    m = folium.Map(location=[lat_center, lon_center], zoom_start=14)
    marker_cluster = MarkerCluster().add_to(m)

    def color_from_dbm(dBm):
        if pd.isna(dBm):
            return "lightgray"
        if dBm >= -69:
            return "green"
        elif -80 <= dBm < -69:
            return "orange"
        else:
            return "red"

    for _, row in df.iterrows():
        lat = row["Latitude - Functional Location"]
        lon = row["Longitude - Functional Location"]
        dbm = row.get("dBm", None)
        row_id = row["row_id"]

        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            color="black",
            fill=True,
            fill_color=color_from_dbm(dbm),
            fill_opacity=0.9,
            popup=f"ID: {row_id} | dBm: {dbm}",
            tooltip="Haz clic para seleccionar",
        ).add_to(marker_cluster)

    # Mostrar el mapa y capturar interacción
    map_data = st_folium(m, width=1000, height=600)

    if map_data and map_data.get("last_object_clicked_tooltip"):
        clicked = map_data.get("last_clicked")
        if clicked:
            lat, lon = clicked["lat"], clicked["lng"]
            match = df[
                (df["Latitude - Functional Location"].sub(lat).abs() < 0.0001) &
                (df["Longitude - Functional Location"].sub(lon).abs() < 0.0001)
            ]
            if not match.empty:
                selected_idx = match.iloc[0]["row_id"]
                st.session_state["selected_row_id"] = selected_idx
