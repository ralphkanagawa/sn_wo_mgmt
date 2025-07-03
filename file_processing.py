import pandas as pd
import streamlit as st
import numpy as np
from scipy.spatial import cKDTree
from utils import classify_signal


def asignar_cobertura_promedio_por_radio(geo_df, cov_df, radio_metros=10):
    def latlon_to_cartesian(lat, lon):
        R = 6371000  # radio de la Tierra en metros
        phi = np.radians(lat)
        theta = np.radians(lon)
        x = R * np.cos(phi) * np.cos(theta)
        y = R * np.cos(phi) * np.sin(theta)
        z = R * np.sin(phi)
        return np.vstack((x, y, z)).T

    # Convertir coordenadas a cartesianas
    geo_coords = latlon_to_cartesian(
        geo_df["Latitude - Functional Location"],
        geo_df["Longitude - Functional Location"]
    )
    cov_coords = latlon_to_cartesian(
        cov_df["Latitud"],
        cov_df["Longitud"]
    )

    tree = cKDTree(cov_coords)
    vecinos_por_punto = tree.query_ball_point(geo_coords, r=radio_metros)

    medias = []
    for vecinos in vecinos_por_punto:
        if vecinos:
            valores = cov_df.iloc[vecinos]["RSSI / RSCP (dBm)"].dropna().tolist()
            if valores:
                medias.append(np.mean(valores))
            else:
                medias.append(None)
        else:
            medias.append(None)

    geo_df["dBm"] = medias
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

    # Renombrar y añadir columnas necesarias
    gdf = geo_df.rename(columns={
        "Latitud": "Latitude - Functional Location",
        "Longitud": "Longitude - Functional Location",
    })
    gdf["Service Account - Work Order"] = "ANER_Senegal"
    gdf["Billing Account - Work Order"] = "ANER_Senegal"
    gdf["Work Order Type - Work Order"] = "Installation"

    # Asignar cobertura por promedio en radio
    gdf = asignar_cobertura_promedio_por_radio(gdf, cov_df, radio_metros=10)

    # Clasificar señal
    gdf["Gateway"] = gdf["dBm"].apply(classify_signal)

    # Guardar en estado
    st.session_state.df = gdf.copy()
    st.session_state.geo_df = geo_df.copy()
    st.session_state.cov_df = cov_df.copy()
    st.session_state.processed = True

    puntos_con_cobertura = gdf["dBm"].notna().sum()
    total_puntos = len(gdf)
    st.info(f"Cobertura vinculada con → {puntos_con_cobertura} de {total_puntos} puntos (media en radio de 10 metros)")
