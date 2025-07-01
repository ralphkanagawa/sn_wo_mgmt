import pydeck as pdk
import pandas as pd
import streamlit as st

def color_from_dbm(v):
    if pd.isna(v):
        return [255, 255, 255]
    if v >= -70:
        return [0, 153, 51]
    if -80 <= v < -70:
        return [255, 165, 0]
    return [255, 0, 0]

def render_map():
    if "edited_df" not in st.session_state:
        return

    geo_points = (
        st.session_state.edited_df[[
            "Latitude - Functional Location",
            "Longitude - Functional Location",
            "dBm",
        ]]
       .dropna(subset=["Latitude - Functional Location", "Longitude - Functional Location"])
        .copy()
    )
    geo_points.rename(columns={
        "Latitude - Functional Location": "lat",
        "Longitude - Functional Location": "lon",
        "dBm": "coverage",
    }, inplace=True)
    geo_points["color"] = geo_points["coverage"].apply(color_from_dbm)

    cov_points = (
        st.session_state.cov_df[["Latitud", "Longitud", "RSSI / RSCP (dBm)"]]
        .dropna()
        .copy()
    )
    cov_points.rename(columns={
        "Latitud": "lat",
        "Longitud": "lon",
        "RSSI / RSCP (dBm)": "coverage",
    }, inplace=True)
    cov_points["color"] = [[128, 128, 128]] * len(cov_points)

    layers = [
        pdk.Layer(
            "ScatterplotLayer",
            data=cov_points,
            get_position="[lon, lat]",
            get_radius=3,
            get_fill_color="color",
            opacity=0.4,
            pickable=True,
        ),
        pdk.Layer(
            "ScatterplotLayer",
            data=geo_points,
            get_position="[lon, lat]",
            get_radius=2,
            get_fill_color="color",
            pickable=True,
        ),
    ]

    if not geo_points.empty:
        init_view_state = pdk.ViewState(
            latitude=geo_points["lat"].mean(),
            longitude=geo_points["lon"].mean(),
            zoom=17,
        )
    else:
        init_view_state = pdk.ViewState(latitude=0, longitude=0, zoom=2)

    tooltip = {
        "html": "<b>dBm:</b> {coverage}",
        "style": {"color": "white"},
    }

    st.pydeck_chart(pdk.Deck(layers=layers, initial_view_state=init_view_state, tooltip=tooltip), height=700)
