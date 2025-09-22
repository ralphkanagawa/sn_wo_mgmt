import folium
from streamlit_folium import st_folium
import pandas as pd
import streamlit as st

def render_map():
    if "latest_edited" not in st.session_state or st.session_state.latest_edited.empty:
        return

    df = st.session_state.latest_edited.copy()
    df = df.dropna(subset=["Latitude - Functional Location", "Longitude - Functional Location"]).reset_index(drop=True)
    df["row_id"] = df.index  # Para poder identificar la fila

    # Intentar usar columna de ID point si existe
    if "ID point" in df.columns:
        df["row_id"] = df["ID point"] - 1  # Para alinear con el índice real

    lat_center = df["Latitude - Functional Location"].mean()
    lon_center = df["Longitude - Functional Location"].mean()

    m = folium.Map(location=[lat_center, lon_center], zoom_start=16)

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
        point_id = row.get("ID point", row_id)

        # Etiqueta con número a la derecha del círculo
        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(
                html=f"""
                <div style="font-size: 12px; color: black; margin-left: 8px; white-space: nowrap;">
                    {point_id}
                </div>
                """
            )
        ).add_to(m)

        # Círculo de color
        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            color="black",
            fill=True,
            fill_color=color_from_dbm(dbm),
            fill_opacity=0.9,
            popup=f"ID point: {point_id} | dBm: {dbm}",
        ).add_to(m)

    col1, col2, col3 = st.columns([1, 3, 1])
    with col2:
        map_data = st_folium(m, width=900, height=600)

    if map_data and map_data.get("last_clicked"):
        clicked = map_data["last_clicked"]
        lat, lon = clicked["lat"], clicked["lng"]
        match = df[
            (df["Latitude - Functional Location"].sub(lat).abs() < 0.0001) &
            (df["Longitude - Functional Location"].sub(lon).abs() < 0.0001)
        ]
        if not match.empty:
            selected_idx = match.iloc[0]["row_id"]
            st.session_state["selected_row_id"] = selected_idx

