import streamlit as st
import pandas as pd
import io
from datetime import date, datetime

from config_loader import load_config, load_excel_template_columns
from file_processing import load_and_process_files
from editor_utils import apply_bulk_value, generate_time_windows, fill_temporal_columns
from visualizations import render_map

from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter

# Configuración de la página
st.set_page_config(page_title="Potential Work Orders Management", layout="wide")

# Inicialización
if "processed" not in st.session_state:
    st.session_state.processed = False
if "edited_df" not in st.session_state:
    st.session_state.edited_df = pd.DataFrame()
if "latest_edited" not in st.session_state:
    st.session_state.latest_edited = pd.DataFrame()

# Cargar configuración
config = load_config()
template_cols = load_excel_template_columns(config.excel_template_path)

# Encabezado con logo
st.image("logotipo-salvi-2024.png", width=120)

# Crear pestañas inferiores
tab1, tab2 = st.tabs(["Gestión de órdenes", "Generar informe"])

# TAB 1 - Todo el flujo actual
with tab1:
    if not st.session_state.processed:
        col_geo, col_cov = st.columns(2)
        with col_geo:
            geo_file = st.file_uploader("📍 Georadar CSV", type="csv")
        with col_cov:
            cov_file = st.file_uploader("📶 Coverage CSV", type="csv")

        if geo_file and cov_file:
            load_and_process_files(geo_file, cov_file, config)
            st.rerun()
        else:
            st.stop()

    disp = st.session_state.df.copy()
    for c in template_cols:
        if c not in disp.columns:
            disp[c] = ""
    disp = disp[template_cols]
    st.session_state.edited_df = disp if st.session_state.edited_df.empty else st.session_state.edited_df

    col_left, col_spacer, col_right = st.columns([2, 6, 2])

    with col_left:
        if st.button("🔁 Volver a cargar archivos"):
            for key in ["processed", "df", "geo_df", "cov_df", "edited_df", "latest_edited"]:
                st.session_state.pop(key, None)
            st.rerun()

    with col_right:
        if st.button("💾 Guardar cambios"):
            st.session_state.edited_df = st.session_state.latest_edited.copy()

    edited = st.data_editor(
        st.session_state.edited_df,
        num_rows="dynamic",
        use_container_width=True,
        key="editor"
    )
    st.session_state.latest_edited = edited.copy()

    col1, col2, col3 = st.columns(3)

    with col1:
        st.write("➕ Añadir datos en bloque")
        editable_cols = [c for c in edited.columns if c not in config.protected_columns]
        col_sel = st.selectbox("Columna", editable_cols)

        val = ""
        if col_sel == "Name - Child Functional Location":
            parents = edited["Name - Parent Functional Location"].dropna().unique()
            par = parents[0] if len(parents) else None
            if par and par in config.parent_child_map:
                val = st.selectbox("Valor hijo", config.parent_child_map[par])
            else:
                st.warning("Define primero 'Parent Functional Location'.")
        elif col_sel in config.dropdown_values:
            val = st.selectbox("Valor", config.dropdown_values[col_sel])
        else:
            val = st.text_input("Valor")

        if st.button("📌 Aplicar valor"):
            new_df = apply_bulk_value(st.session_state.latest_edited.copy(), col_sel, val)
            st.session_state.edited_df = new_df
            st.session_state.latest_edited = new_df.copy()
            st.rerun()

    with col2:
        st.write("⏱️ Autocompletar fechas/horas")
        d0 = st.date_input("Fecha inicial", value=date.today())
        t0 = st.time_input("Hora inicial", value=datetime.now().time().replace(second=0, microsecond=0))
        if st.button("🕒 Generar cada 27 min"):
            incs = generate_time_windows(d0, t0, len(st.session_state.latest_edited))
            new_df = fill_temporal_columns(st.session_state.latest_edited.copy(), incs)
            st.session_state.edited_df = new_df
            st.session_state.latest_edited = new_df.copy()
            st.rerun()

    with col3:
        st.write("💾 Descargar Excel")
        if st.button("Generar Excel"):
            df_out = st.session_state.edited_df.copy()
            for c in template_cols:
                if c not in df_out.columns:
                    df_out[c] = ""
            df_out = df_out[template_cols]

            buf = io.BytesIO()
            with pd.ExcelWriter(buf, engine="openpyxl") as w:
                df_out.to_excel(w, index=False)
            buf.seek(0)

            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            st.download_button(
                "⬇️ Descargar Excel",
                data=buf,
                file_name=f"workorders_{ts}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

    render_map()
    col1, col2, col3, col4, col_spacer, col_spacer, col_spacer, col_spacer = st.columns(8)
    
    with col1:
        st.markdown("🟢 **Buena**", unsafe_allow_html=True)
    with col2:
        st.markdown("🟠 **Justa**", unsafe_allow_html=True)
    with col3:
        st.markdown("🔴 **Insuficiente**", unsafe_allow_html=True)
    with col4:
        st.markdown("⚪ **Sin datos**", unsafe_allow_html=True)

    st.caption("Desarrollado en Streamlit • Última actualización: 2025-06-30")

# --- TAB 2: Generación del Informe PDF ---
with tab2:
    st.markdown("### Generación de informe PDF")

    from jinja2 import Template
    from xhtml2pdf import pisa
    import contextily as ctx
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    def save_geoposition_map(df, path="map_contextual.png"):
        fig, ax = plt.subplots(figsize=(8, 6))

        df_with = df[df["dBm"].notna()]
        df_without = df[df["dBm"].isna()]

        if not df_without.empty:
            ax.scatter(
                df_without["Longitude - Functional Location"],
                df_without["Latitude - Functional Location"],
                color="lightgray",
                s=50,
                alpha=0.9,
                edgecolors="black"
            )

        if not df_with.empty:
            ax.scatter(
                df_with["Longitude - Functional Location"],
                df_with["Latitude - Functional Location"],
                c=df_with["dBm"],
                cmap="RdYlGn",
                s=60,
                alpha=0.9,
                edgecolors="black"
            )

        ctx.add_basemap(ax, crs="EPSG:4326", source=ctx.providers.OpenStreetMap.Mapnik)

        legend_patches = [
            mpatches.Patch(color="#009933", label="Buena cobertura (≥ -70 dBm)"),
            mpatches.Patch(color="#FFA500", label="Cobertura media (-80 a -70 dBm)"),
            mpatches.Patch(color="#FF0000", label="Poca cobertura (< -80 dBm)"),
            mpatches.Patch(color="lightgray", label="Sin datos")
        ]
        ax.legend(handles=legend_patches, loc="lower left")

        ax.axis("off")
        plt.tight_layout()
        plt.savefig(path, bbox_inches="tight", pad_inches=0)
        plt.close()

    def obtener_calles_por_geocodificacion(df, lat_col, lon_col):
        geolocator = Nominatim(user_agent="cm_salvi_app")
        geocode = RateLimiter(geolocator.reverse, min_delay_seconds=1, return_value_on_exception=None)
    
        calles = []
        for _, row in df.iterrows():
            lat, lon = row[lat_col], row[lon_col]
            if pd.notna(lat) and pd.notna(lon):
                location = geocode((lat, lon), language="es")
                calle = location.raw["address"].get("road") if location else None
                calles.append(calle)
            else:
                calles.append(None)
        return calles


    def render_pdf(template_path, context, output_path):
        with open(template_path, "r", encoding="utf-8") as f:
            html = Template(f.read()).render(**context)
        with open(output_path, "wb") as f:
            pisa.CreatePDF(html, dest=f)

    if st.session_state.edited_df.empty:
        st.warning("No hay datos disponibles. Por favor, carga y edita datos en la pestaña anterior.")
    else:
        df_full = st.session_state.df.copy()
        save_geoposition_map(df_full, "map_contextual.png")


        col1, col2, col3 = st.columns([1, 2, 1])  # columna central más ancha
        
        with col2:
            st.image("map_contextual.png", caption="Mapa de cobertura (base OSM)", use_container_width=True)


        if st.button("📄 Generar informe PDF"):
            df_full = st.session_state.df.copy()
            save_geoposition_map(df_full, "map_contextual.png")
        
            # Obtener calles a partir de coordenadas
            df_full["Calle (por coordenadas)"] = obtener_calles_por_geocodificacion(
                df_full,
                "Latitude - Functional Location",
                "Longitude - Functional Location"
            )
            calles_validas = df_full["Calle (por coordenadas)"].dropna()
            calles_unicas = calles_validas.unique().tolist()
            ordenes_por_calle = calles_validas.value_counts().to_dict()
        
            # Preparar métricas
            total_ordenes = len(df_full)
            total_yes = (df_full["Gateway"] == "YES").sum()
            total_no = (df_full["Gateway"] == "NO").sum()
        
            parent_locations = df_full["Name - Parent Functional Location"].dropna().unique().tolist()
            child_locations = df_full["Name - Child Functional Location"].dropna().unique().tolist()
        
            incident_types = df_full["Incident Type - Work Order"].dropna().unique().tolist()
            owners = df_full["Owner - Work Order"].dropna().unique().tolist()
            resources = df_full["Name - Bookable Resource Booking"].dropna().unique().tolist()
        
            context = {
                "fecha": datetime.now().strftime("%d/%m/%Y"),
                "total_ordenes": total_ordenes,
                "total_yes": total_yes,
                "total_no": total_no,
                "parent_locations": parent_locations,
                "child_locations": child_locations,
                "calles": calles_unicas,
                "ordenes_por_calle": ordenes_por_calle,
                "incident_types": incident_types,
                "owners": owners,
                "resources": resources,
            }
        
            render_pdf("report_template.html", context, "informe.pdf")
            with open("informe.pdf", "rb") as f:
                st.download_button(
                    "⬇️ Descargar informe PDF",
                    data=f,
                    file_name="informe.pdf",
                    mime="application/pdf"
                )
