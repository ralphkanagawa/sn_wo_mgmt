import pandas as pd
import streamlit as st
from utils import classify_signal

from scipy.spatial import cKDTree
import numpy as np

def asignar_cobertura_por_proximidad(geo_df, cov_df, max_dist_metros=10):
    def latlon_to_cartesian(lat, lon):
        R = 6371000  # radio de la Tierra en metros
        phi = np.radians(lat)
        theta = np.radians(lon)
        x = R * np.cos(phi) * np.cos(theta)
        y = R * np.cos(phi) * np.sin(theta)
        z = R * np.sin(phi)
        return np.vstack((x, y, z)).T

    geo_coords = latlon_to_cartesian(geo_df["Latitude - Functional Location"], geo_df["Longitude - Functional Location"])
    cov_coords = latlon_to_cartesian(cov_df["Latitud"], cov_df["Longitud"])

    tree = cKDTree(cov_coords)
    distancias, indices = tree.query(geo_coords, distance_upper_bound=max_dist_metros)

    rssi = []
    for d, idx in zip(distancias, indices):
        if idx < len(cov_df):
            rssi.append(cov_df.iloc[idx]["RSSI / RSCP (dBm)"])
        else:
            rssi.append(None)

    geo_df["dBm"] = rssi
    return geo_df

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

    gdf = asignar_cobertura_por_proximidad(gdf, cov_df)
    gdf["Gateway"] = gdf["dBm"].apply(classify_signal)


    st.session_state.df = gdf.copy()
    st.session_state.geo_df = geo_df.copy()
    st.session_state.cov_df = cov_df.copy()
    st.session_state.processed = True
