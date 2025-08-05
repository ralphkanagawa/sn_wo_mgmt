import pandas as pd
import streamlit as st
import numpy as np
from scipy.spatial import cKDTree
from utils import classify_signal
from zipfile import ZipFile
from shapely.geometry import Point

# ─── NUEVO: Soporte para .kmz y .kml ────────────────────────────────────────────

def extract_kml_from_kmz(kmz_file):
    """Extrae y retorna el contenido del archivo KML desde un KMZ subido."""
    with ZipFile(kmz_file, 'r') as zip_ref:
        for file in zip_ref.namelist():
            if file.endswith('.kml'):
                with zip_ref.open(file) as kml_file:
                    return kml_file.read()
    return None

def parse_kml_data(kml_bytes):
    """Extrae coordenadas desde datos binarios KML usando fastkml."""
    from fastkml import kml

    k = kml.KML()
    try:
        k.from_string(kml_bytes)
    except Exception:
        st.error("❌ Error al parsear el archivo KML: formato inválido.")
        st.stop()

    placemarks = []

    def extract_placemarks(features):
        for f in features:
            try:
                sub_features = list(f.features()) if hasattr(f, 'features') else []
                if sub_features:
                    yield from extract_placemarks(sub_features)
                elif hasattr(f, 'geometry') and isinstance(f.geometry, Point):
                    placemarks.append({
                        "Latitude - Functional Location": f.geometry.y,
                        "Longitude - Functional Location": f.geometry.x
                    })
            except Exception:
                continue

    # ← Aquí evitamos el fallo directamente:
    try:
        features = list(k.features())
        if not features:
            st.error("❌ El archivo KML no contiene ningún punto o carpeta reconocible.")
            st.stop()
        list(extract_placemarks(features))
    except Exception:
        st.error("❌ Error al procesar las características del archivo KML.")
        st.stop()

    if not placemarks:
        st.error("❌ No se encontraron puntos con coordenadas en el archivo.")
        st.stop()

    return pd.DataFrame(placemarks)

def load_georadar_file(geo_file):
    """Carga datos del georadar desde KMZ, KML o CSV"""
    name = geo_file.name.lower()
    
    if name.endswith(".kmz"):
        kml_data = extract_kml_from_kmz(geo_file)
        if kml_data:
            return parse_kml_data(kml_data)
        else:
            st.error("❌ No se encontró archivo KML dentro del KMZ.")
            st.stop()
    elif name.endswith(".kml"):
        kml_data = geo_file.read()
        return parse_kml_data(kml_data)
    elif name.endswith(".csv"):
        df = pd.read_csv(geo_file)
        if not {"Latitud", "Longitud"}.issubset(df.columns):
            st.error("Georadar CSV debe tener columnas 'Latitud' y 'Longitud'")
            st.stop()
        return df.rename(columns={
            "Latitud": "Latitude - Functional Location",
            "Longitud": "Longitude - Functional Location"
        })
    else:
        st.error("Tipo de archivo no compatible para Georadar.")
        st.stop()

# ─── Cobertura ───────────────────────────────────────────────────────────────────

def asignar_cobertura_promedio_por_radio(geo_df, cov_df, radio_metros=15):
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
                medias.append(round(np.mean(valores)))
            else:
                medias.append(None)
        else:
            medias.append(None)

    geo_df["dBm"] = medias
    return geo_df

# ─── Función principal ───────────────────────────────────────────────────────────

def load_and_process_files(geo_file, cov_file, config):
    geo_df = load_georadar_file(geo_file)
    cov_df = pd.read_csv(cov_file)

    if not {"Latitud", "Longitud", "RSSI / RSCP (dBm)"}.issubset(cov_df.columns):
        st.error("Coverage CSV debe tener columnas: Latitud, Longitud y RSSI / RSCP (dBm)")
        st.stop()

    # Completar columnas necesarias
    geo_df["Service Account - Work Order"] = "ANER_Senegal"
    geo_df["Billing Account - Work Order"] = "ANER_Senegal"
    geo_df["Work Order Type - Work Order"] = "Installation"

    # Asignar cobertura por promedio en radio
    geo_df = asignar_cobertura_promedio_por_radio(geo_df, cov_df, radio_metros=15)

    # Clasificar señal
    geo_df["Gateway"] = geo_df["dBm"].apply(classify_signal)

    # Guardar en estado
    st.session_state.df = geo_df.copy()
    st.session_state.geo_df = geo_df.copy()
    st.session_state.cov_df = cov_df.copy()
    st.session_state.processed = True

    puntos_con_cobertura = geo_df["dBm"].notna().sum()
    total_puntos = len(geo_df)
    st.info(f"Cobertura vinculada con → {puntos_con_cobertura} de {total_puntos} puntos (media en radio de 15 metros)")

