import pandas as pd
import streamlit as st
import numpy as np
from scipy.spatial import cKDTree
from utils import classify_signal
from zipfile import ZipFile
from shapely.geometry import Point
import os, io
import xml.etree.ElementTree as ET

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
    """Parsea KML directamente con XML para extraer coordenadas."""
    try:
        tree = ET.ElementTree(ET.fromstring(kml_bytes))
    except Exception:
        st.error("❌ KML file not valid.")
        st.stop()

    root = tree.getroot()
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
        st.error("❌ Coordinates not found in the file.")
        st.stop()

    return pd.DataFrame(puntos)

def load_georadar_file(geo_file):
    """Carga Georadar desde KMZ/KML/CSV aceptando UploadedFile, ruta str/Path o file-like."""
    if isinstance(geo_file, (str, os.PathLike)):
        name = os.fspath(geo_file).lower()
        handle = geo_file
    else:
        name = getattr(geo_file, "name", "") or ""
        handle = geo_file
        try:
            handle.seek(0)
        except Exception:
            pass

    if name.endswith(".kmz"):
        if isinstance(handle, (str, os.PathLike)):
            kml_data = extract_kml_from_kmz(handle)
        else:
            data = handle.read()
            kml_data = extract_kml_from_kmz(io.BytesIO(data))
        if not kml_data:
            st.error("❌ .kml not found inside the KMZ file.")
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
            st.error("Georadar file must contain 'Latitude' and 'Longitude' columns.")
            st.stop()
        return df.rename(columns={
            "Latitud": "Latitude - Functional Location",
            "Longitud": "Longitude - Functional Location"
        })

    else:
        st.error("File type not compatible (use KMZ/KML/CSV).")
        st.stop()

# ─── Cobertura ───────────────────────────────────────────────────────────────────

def asignar_cobertura_promedio_por_radio(geo_df, cov_df, radio_metros=15):
    def latlon_to_cartesian(lat, lon):
        R = 6371000
        phi = np.radians(lat)
        theta = np.radians(lon)
        x = R * np.cos(phi) * np.cos(theta)
        y = R * np.cos(phi) * np.sin(theta)
        z = R * np.sin(phi)
        return np.vstack((x, y, z)).T

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

def load_and_process_files(geo_files, cov_file=None, config=None):
    """
    geo_files: lista de UploadedFile o un único UploadedFile
    cov_file: UploadedFile opcional (CSV de cobertura)
    """
    files = geo_files if isinstance(geo_files, list) else [geo_files]

    frames = []
    parents_detectados = set()

    # --- NUEVO: registrar número de puntos por fichero ---
    st.session_state.points_per_file = {}

    for f in files:
        df_tmp = load_georadar_file(f)
        num_points = len(df_tmp)
        st.session_state.points_per_file[getattr(f, "name", str(f))] = num_points

        # Detectar Parent y Child desde el nombre
        fname = getattr(f, "name", str(f))
        base = os.path.basename(fname)
        parts = base.split("_")
        if len(parts) < 2:
            st.error(f"File name not valid: {fname}")
            st.stop()

        child_loc = parts[0]
        parent_loc = parts[1]
        parents_detectados.add(parent_loc)

        df_tmp["Name - Parent Functional Location"] = parent_loc
        df_tmp["Name - Child Functional Location"] = child_loc

        frames.append(df_tmp)

    if len(parents_detectados) > 1:
        st.error(f"❌ The files uploaded doesn't correspond to the same Parent Location: {parents_detectados}")
        st.stop()

    geo_df = pd.concat(frames, ignore_index=True)

    # --- NUEVO: total de puntos ---
    st.session_state.total_points = sum(st.session_state.points_per_file.values())
    st.session_state["points_data"] = {
        "per_file": st.session_state.points_per_file.copy(),
        "total": st.session_state.total_points
    }


    # Completar columnas necesarias
    geo_df["Service Account - Work Order"] = "ANER_Senegal"
    geo_df["Billing Account - Work Order"] = "ANER_Senegal"
    geo_df["Work Order Type - Work Order"] = "Installation"

    # Cobertura
    if cov_file is not None:
        cov_df = pd.read_csv(cov_file)
        required_cov = {"Latitud", "Longitud", "RSSI / RSCP (dBm)"}
        if not required_cov.issubset(cov_df.columns):
            st.error("Coverage file must contain 'Latitude', 'Longitude' and 'RSSI / RSCP (dBm)' columns.")
            st.stop()

        geo_df = asignar_cobertura_promedio_por_radio(geo_df, cov_df, radio_metros=15)
        geo_df["Gateway"] = geo_df["dBm"].apply(classify_signal)

        st.session_state.cov_df = cov_df.copy()
        puntos_con_cobertura = geo_df["dBm"].notna().sum()
        st.info(f"Coverage linked with → {puntos_con_cobertura} of {len(geo_df)} points")
    else:
        if "dBm" not in geo_df.columns:
            geo_df["dBm"] = pd.NA
        if "Gateway" not in geo_df.columns:
            geo_df["Gateway"] = pd.NA
        st.info("Only Georadar file uploaded, a Coverage file hasn't been uploaded.")

    # Guardar en estado
    st.session_state.df = geo_df.copy()
    st.session_state.geo_df = geo_df.copy()
    st.session_state.processed = True

    # --- NUEVO: mostrar resumen en la app ---
    st.success("✅ Files processed successfully.")
    st.write("### Points per file")
    points_summary = pd.DataFrame.from_dict(
        st.session_state.points_per_file, orient="index", columns=["Points"]
    )
    st.dataframe(points_summary)
    st.write(f"**Total points:** {st.session_state.total_points}")
