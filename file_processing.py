import pandas as pd
import streamlit as st
import numpy as np
from scipy.spatial import cKDTree
from utils import classify_signal
from zipfile import ZipFile
import os, io, xml.etree.ElementTree as ET

# ─── Extracción del KML desde KMZ ───────────────────────────────────────────────

def extract_kml_from_kmz(kmz_file):
    with ZipFile(kmz_file, 'r') as zip_ref:
        for file in zip_ref.namelist():
            if file.endswith('.kml'):
                with zip_ref.open(file) as kml_file:
                    return kml_file.read()
    return None

# ─── Parser de KML con filtros específicos ─────────────────────────────────────

def parse_kml_data(kml_bytes):
    """Lee los <Placemark> cuyo <name> empiece por 'MapExport', 
    excluye los de color rojo (ff0000ff) o con descripción 'Obstacle'."""
    try:
        tree = ET.ElementTree(ET.fromstring(kml_bytes))
    except Exception:
        st.error("❌ KML file not valid.")
        st.stop()

    ns = {'kml': 'http://www.opengis.net/kml/2.2'}
    root = tree.getroot()

    # Mapear estilos (id -> color)
    style_map = {}
    for style in root.findall(".//kml:Style", ns):
        style_id = style.attrib.get("id", "")
        color_el = style.find(".//kml:LineStyle/kml:color", ns)
        if color_el is not None:
            style_map[style_id] = color_el.text.strip().lower()

    puntos = []

    for placemark in root.findall(".//kml:Placemark", ns):
        name_el = placemark.find("kml:name", ns)
        desc_el = placemark.find("kml:description", ns)
        style_url_el = placemark.find("kml:styleUrl", ns)

        name = name_el.text.strip() if name_el is not None else ""
        description = desc_el.text.strip() if desc_el is not None else ""
        style_ref = style_url_el.text.strip().replace("#", "") if style_url_el is not None else ""

        # Filtros de exclusión
        if not name.startswith("MapExport"):
            continue
        if "obstacle" in description.lower():
            continue
        if style_ref in style_map and style_map[style_ref] == "ff0000ff":
            continue

        # Extraer coordenadas
        coords_list = placemark.findall(".//kml:coordinates", ns)
        for coord in coords_list:
            raw_text = coord.text.strip()
            for line in raw_text.split():
                parts = line.split(",")
                if len(parts) >= 2:
                    lon, lat = float(parts[0]), float(parts[1])
                    puntos.append({
                        "Latitude - Functional Location": lat,
                        "Longitude - Functional Location": lon,
                        "Service Address - Functional Location": name,
                        "Summary - Work Order": name,
                    })

    if not puntos:
        st.error("❌ No valid coordinates found in KML after filtering.")
        st.stop()

    return pd.DataFrame(puntos)

# ─── Carga de ficheros Georadar ────────────────────────────────────────────────

def load_georadar_file(geo_file):
    """Carga Georadar desde KMZ/KML/CSV, aplicando los filtros definidos."""
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
        df = df.rename(columns={
            "Latitud": "Latitude - Functional Location",
            "Longitud": "Longitude - Functional Location"
        })
        df["Service Address - Functional Location"] = "CSV import"
        df["Summary - Work Order"] = "CSV import"
        return df

    else:
        st.error("File type not compatible (use KMZ/KML/CSV).")
        st.stop()

# ─── Cobertura ─────────────────────────────────────────────────────────────────

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
            medias.append(round(np.mean(valores)) if valores else None)
        else:
            medias.append(None)

    geo_df["dBm"] = medias
    return geo_df

# ─── Proceso principal ─────────────────────────────────────────────────────────

def load_and_process_files(geo_files, cov_file=None, config=None):
    """Procesa ficheros de georadar y cobertura, sin depender del nombre."""
    files = geo_files if isinstance(geo_files, list) else [geo_files]
    frames = []

    for f in files:
        df_tmp = load_georadar_file(f)
        frames.append(df_tmp)

    geo_df = pd.concat(frames, ignore_index=True)

    # Completar columnas mínimas
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
        st.info(f"Coverage linked with → {geo_df['dBm'].notna().sum()} of {len(geo_df)} points")
    else:
        if "dBm" not in geo_df.columns:
            geo_df["dBm"] = pd.NA
        if "Gateway" not in geo_df.columns:
            geo_df["Gateway"] = pd.NA
        st.info("Only Georadar file uploaded, a Coverage file hasn't been uploaded.")

    st.session_state.df = geo_df.copy()
    st.session_state.geo_df = geo_df.copy()
    st.session_state.processed = True
