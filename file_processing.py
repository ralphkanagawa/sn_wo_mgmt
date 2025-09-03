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

import xml.etree.ElementTree as ET

def parse_kml_data(kml_bytes):
    """Parsea KML directamente con XML para extraer coordenadas."""
    try:
        tree = ET.ElementTree(ET.fromstring(kml_bytes))
    except Exception:
        st.error("❌ El archivo KML no es válido.")
        st.stop()

    root = tree.getroot()

    # Buscar todos los elementos <coordinates>
    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    coords = root.findall('.//kml:coordinates', ns)

    puntos = []
    for coord in coords:
        raw_text = coord.text.strip()
        for line in raw_text.split():
            parts = line.split(",")
            if len(parts) >= 2:
                lon, lat = float(parts[0]), float(parts[1])
                puntos.append({
                    "Latitude - Functional Location": lat,
                    "Longitude - Functional Location": lon
                })

    if not puntos:
        st.error("❌ No se encontraron coordenadas en el archivo.")
        st.stop()

    return pd.DataFrame(puntos)


# file_processing.py
import os, io  # añade estas importaciones si no están

def load_georadar_file(geo_file):
    """Carga Georadar desde KMZ/KML/CSV aceptando UploadedFile, ruta str/Path o file-like."""
    # Normalizar: obtener nombre y manejador reutilizable
    if isinstance(geo_file, (str, os.PathLike)):
        name = os.fspath(geo_file).lower()
        handle = geo_file  # es una ruta
    else:
        name = getattr(geo_file, "name", "") or ""
        name = name.lower()
        handle = geo_file
        # asegurar puntero al inicio si es file-like
        try:
            handle.seek(0)
        except Exception:
            pass

    if name.endswith(".kmz"):
        # ZipFile necesita un objeto "seekable": si es file-like, lo envolvemos en BytesIO
        if isinstance(handle, (str, os.PathLike)):
            kml_data = extract_kml_from_kmz(handle)
        else:
            data = handle.read()
            kml_data = extract_kml_from_kmz(io.BytesIO(data))
        if not kml_data:
            st.error("❌ No se encontró un .kml dentro del KMZ.")
            st.stop()
        return parse_kml_data(kml_data)

    elif name.endswith(".kml"):
        if isinstance(handle, (str, os.PathLike)):
            with open(handle, "rb") as f:
                kml_data = f.read()
        else:
            kml_data = handle.read()
        return parse_kml_data(kml_data)

    elif name.endswith(".csv"):
        df = pd.read_csv(handle)
        if not {"Latitud", "Longitud"}.issubset(df.columns):
            st.error("Georadar CSV debe tener columnas 'Latitud' y 'Longitud'")
            st.stop()
        return df.rename(columns={
            "Latitud": "Latitude - Functional Location",
            "Longitud": "Longitude - Functional Location"
        })

    else:
        st.error("Tipo de archivo no compatible (usa KMZ/KML/CSV).")
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

# file_processing.py

def load_and_process_files(geo_files, cov_file=None, config=None):
    """
    geo_files: lista de UploadedFile o un único UploadedFile
    cov_file: UploadedFile opcional (CSV de cobertura)
    """
    import pandas as pd
    import streamlit as st

    # Aceptar uno o varios ficheros de georadar
    files = geo_files if isinstance(geo_files, list) else [geo_files]

    # Cargar y unir todos los puntos de georadar
    frames = []
    for f in files:
        frames.append(load_georadar_file(f))
    geo_df = pd.concat(frames, ignore_index=True)

    # Completar columnas necesarias (aunque no haya cobertura)
    geo_df["Service Account - Work Order"] = "ANER_Senegal"
    geo_df["Billing Account - Work Order"] = "ANER_Senegal"
    geo_df["Work Order Type - Work Order"] = "Installation"

    # Si hay cobertura, asignar dBm y Gateway; si no, dejarlas vacías
    if cov_file is not None:
        cov_df = pd.read_csv(cov_file)

        required_cov = {"Latitud", "Longitud", "RSSI / RSCP (dBm)"}
        if not required_cov.issubset(cov_df.columns):
            st.error("Coverage CSV debe tener columnas: Latitud, Longitud y RSSI / RSCP (dBm)")
            st.stop()

        # Promedio en radio y clasificación
        geo_df = asignar_cobertura_promedio_por_radio(geo_df, cov_df, radio_metros=15)
        geo_df["Gateway"] = geo_df["dBm"].apply(classify_signal)

        st.session_state.cov_df = cov_df.copy()
        puntos_con_cobertura = geo_df["dBm"].notna().sum()
        st.info(f"Cobertura vinculada con → {puntos_con_cobertura} de {len(geo_df)} puntos (media en radio de 15 metros)")
    else:
        if "dBm" not in geo_df.columns:
            geo_df["dBm"] = pd.NA
        if "Gateway" not in geo_df.columns:
            geo_df["Gateway"] = pd.NA
        st.info("Se cargó únicamente Georadar; no se vinculó Cobertura.")

    # Guardar en estado
    st.session_state.df = geo_df.copy()
    st.session_state.geo_df = geo_df.copy()
    st.session_state.processed = True
