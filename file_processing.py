import pandas as pd
import streamlit as st
from utils import classify_signal

def load_and_process_files(geo_file, cov_file, config):
    geo_df = pd.read_csv(geo_file)
    cov_df = pd.read_csv(cov_file)

    if not {"Latitud", "Longitud"}.issubset(geo_df.columns):
        st.error("Georadar debe tener columnas Latitud y Longitud")
        st.stop()
    if not {"Latitud", "Longitud", "RSSI / RSCP (dBm)"}.issubset(cov_df.columns):
        st.error("Coverage debe tener Latitud, Longitud y RSSI / RSCP (dBm)")
        st.stop()

    gdf = geo_df.rename(columns={
        "Latitud": "Latitude - Functional Location",
        "Longitud": "Longitude - Functional Location",
    })

    gdf["Service Account - Work Order"] = "ANER_Senegal"
    gdf["Billing Account - Work Order"] = "ANER_Senegal"
    gdf["Work Order Type - Work Order"] = "Installation"

    gdf["LatBin"] = gdf["Latitude - Functional Location"].round(10)
    gdf["LonBin"] = gdf["Longitude - Functional Location"].round(10)
    cov_df["LatBin"] = cov_df["Latitud"].round(10)
    cov_df["LonBin"] = cov_df["Longitud"].round(10)

    cov_map = cov_df.set_index(["LatBin", "LonBin"])["RSSI / RSCP (dBm)"].to_dict()
    gdf["dBm"] = gdf.apply(lambda r: cov_map.get((r.LatBin, r.LonBin)), axis=1)
    gdf["Gateway"] = gdf["dBm"].apply(classify_signal)
    gdf.drop(columns=["LatBin", "LonBin"], inplace=True)

    st.session_state.df = gdf.copy()
    st.session_state.geo_df = geo_df.copy()
    st.session_state.cov_df = cov_df.copy()
    st.session_state.processed = True
