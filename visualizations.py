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
    df["row_id"] = df.index

    if "ID point" in df.columns:
        df["row_id"] = df["ID point"] - 1

    lat_center = df["Latitude - Functional Location"].mean()
    lon_center = df["Longitude - Functional Location"].mean()

    # --- Nuevo: selector de tiles ---
    tile_option = st.selectbox(
        "🌍 Select basemap",
        [
            "OpenStreetMap",
            "CartoDB Positron",
            "CartoDB Dark_Matter",
            "Esri Satellite"
        ]
    )

    tile_providers = {
        "OpenStreetMap": "OpenStreetMap",
        "CartoDB Positron": "CartoDB positron",
        "CartoDB Dark_Matter": "CartoDB dark_matter",
        "Esri Satellite": "Esri.WorldImagery",
    }

    m = folium.Map(location=[lat_center, lon_center], zoom_start=16, tiles=None)
    folium.TileLayer(tile_providers[tile_option]).add_to(m)

    def color_from_dbm(dBm):
        if pd.isna(dBm):
            return "lightgray"
        if dBm >= -69:
            return "green"
        elif -80 <= dBm < -69:
            return "orange"
        else:
            return "red"

    cluster = MarkerCluster().add_to(m)

    offsets = [
        "transform: translate(12px, 0);",
        "transform: translate(-22px, 0);",
        "transform: translate(0, -18px);",
        "transform: translate(0, 12px);"
    ]

    for _, row in df.iterrows():
        lat = row["Latitude - Functional Location"]
        lon = row["Longitude - Functional Location"]
        dbm = row.get("dBm", None)
        row_id = row["row_id"]
        point_id = row.get("ID point", row_id)

        style = offsets[row_id % len(offsets)]

        folium.Marker(
            location=[lat, lon],
            icon=folium.DivIcon(
                html=f"""
                <div style="font-size: 13px; font-weight: bold; color: black;
                            text-shadow: -1px -1px 0 white, 1px -1px 0 white,
                                         -1px 1px 0 white, 1px 1px 0 white;
                            {style}">
                    {point_id}
                </div>
                """
            )
        ).add_to(cluster)

        folium.CircleMarker(
            location=[lat, lon],
            radius=6,
            color="black",
            fill=True,
            fill_color=color_from_dbm(dbm),
            fill_opacity=0.9,
            popup=f"ID point: {point_id} | dBm: {dbm}",
        ).add_to(m)

    map_data = st_folium(m, width=1500, height=800)

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
