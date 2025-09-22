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
from docx import Document

# Configuración de la página
st.set_page_config(page_title="Work Orders WebApp", layout="wide")

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

# --- NUEVO: cargar columnas visibles desde config.ini ---
import configparser
cfg = configparser.ConfigParser()
cfg.optionxform = str
cfg.read("config.ini")
visible_cols = []
if cfg.has_section("VISIBLE_COLUMNS"):
    visible_cols = [c.strip() for c in cfg.get("VISIBLE_COLUMNS", "columns").split(",") if c]

# Encabezado con logo
st.image("logotipo-salvi-2024.png", width=120)

# Crear pestañas inferiores
tab1, tab2 = st.tabs(["Work Order Management", "Report generator"])

# TAB 1
with tab1:
    if not st.session_state.processed:
        col_geo, col_cov = st.columns(2)
        with col_geo:
            geo_files = st.file_uploader(
                "📍 Georadar (KMZ / KML / CSV) — puedes subir varios",
                type=["kmz", "kml", "csv"],
                accept_multiple_files=True
            )
        with col_cov:
            cov_file = st.file_uploader("📶 Coverage CSV (opcional)", type="csv")

        procesar = st.button("⚙️ Process files")

        if procesar and geo_files:
            load_and_process_files(geo_files, cov_file, config)
            st.rerun()
        else:
            st.stop()

    disp = st.session_state.df.copy()

    # Añadir columna 'ID point'
    if "ID point" not in disp.columns:
        disp.insert(0, "ID point", range(1, len(disp) + 1))

    for c in template_cols:
        if c not in disp.columns:
            disp[c] = ""

    disp = disp[["ID point"] + [col for col in template_cols if col != "ID point"]]

    # --- NUEVO: limitar al conjunto visible si está definido ---
    #if visible_cols:
        # Siempre conservar ID point aunque no esté en visibles
        #keep = ["ID point"] + [c for c in visible_cols if c in disp.columns]
        #disp = disp[keep]

    st.session_state.edited_df = disp if st.session_state.edited_df.empty else st.session_state.edited_df

    col_left, col_spacer, col_right = st.columns([3, 12, 2])

    with col_left:
        if st.button("🔁 Reload files"):
            for key in ["processed", "df", "geo_df", "cov_df", "edited_df", "latest_edited"]:
                st.session_state.pop(key, None)
            st.rerun()

    with col_right:
        if st.button("💾 Save changes"):
            st.session_state.edited_df = st.session_state.latest_edited.copy()

    # Editor
    edited = st.data_editor(
        st.session_state.edited_df,
        num_rows="dynamic",
        use_container_width=True,
        key="editor"
    )

    # Validación
    invalid_mask = pd.DataFrame(False, index=edited.index, columns=edited.columns)
    for col in config.required_columns:
        if col in config.dropdown_values and col in edited.columns:
            allowed = config.dropdown_values[col]
            invalid_mask[col] = ~edited[col].isin(allowed)
    if "Name - Child Functional Location" in edited.columns:
        all_children = [child for children in config.parent_child_map.values() for child in children]
        invalid_mask["Name - Child Functional Location"] = ~edited["Name - Child Functional Location"].isin(all_children)

    if invalid_mask.any().any():
        st.warning("⚠️ Invalid cell values have been detected. Please review the content before exporting.")

    st.session_state.latest_edited = edited.copy()

    # (resto de la lógica de TAB 1 sin cambios)
    # ...
    # TAB 2 sigue igual

    
    # Mostrar fila seleccionada desde el mapa
    if "selected_row_id" in st.session_state:
        selected_id = st.session_state["selected_row_id"]
        st.markdown(f"<span style='color:green;'>🟢 Selected point: row {selected_id + 1}</span>", unsafe_allow_html=True)


    col_spacer, col1, col_spacer, col2, col_spacer, col3, col_spacer = st.columns([2, 3, 2, 3, 2, 3, 2])

    with col1:
        st.write("➕ Add data")
        editable_cols = [c for c in edited.columns if c not in config.protected_columns]
        col_sel = st.selectbox("Column", editable_cols)

        val = ""
        if col_sel == "Name - Child Functional Location":
            parents = edited["Name - Parent Functional Location"].dropna().unique()
            par = parents[0] if len(parents) else None
            if par and par in config.parent_child_map:
                val = st.selectbox("Child value", config.parent_child_map[par])
            else:
                st.warning("Define first 'Parent Functional Location'.")
        elif col_sel in config.dropdown_values:
            val = st.selectbox("Valor", config.dropdown_values[col_sel])
        else:
            val = st.text_input("Valor")

        if st.button("📌 Apply value"):
            new_df = apply_bulk_value(st.session_state.latest_edited.copy(), col_sel, val)
            st.session_state.edited_df = new_df
            st.session_state.latest_edited = new_df.copy()
            st.rerun()

    with col2:
        st.write("⏱️ Autofill date/time")
        d0 = st.date_input("Initial Date", value=date.today())
        t0 = st.time_input("Initial Time", value=datetime.now().time().replace(second=0, microsecond=0))
        if st.button("🕒 Generate each 27 min"):
            incs = generate_time_windows(d0, t0, len(st.session_state.latest_edited))
            new_df = fill_temporal_columns(st.session_state.latest_edited.copy(), incs)
            st.session_state.edited_df = new_df
            st.session_state.latest_edited = new_df.copy()
            st.rerun()

    with col3:
        st.write("💾 Download Excel")
    
        if st.button("Generate Excel"):
            df_check = st.session_state.edited_df.copy()
    
            # Verificación estricta: columnas requeridas deben estar completas (no NaN, no "", no espacios)
            missing_values = []
            for col in config.required_columns:
                if col in df_check.columns:
                    if df_check[col].apply(lambda x: pd.isna(x) or str(x).strip() == "").any():
                        missing_values.append(col)
    
            if missing_values:
                st.error(f"The Excel file cannot be generated. The following required columns have empty values: {', '.join(missing_values)}")
            else:
                df_out = df_check.copy()
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
                    "⬇️ Download Excel",
                    data=buf,
                    file_name="Staging Dimensioned Records_Prod.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                )

                
    st.markdown("---")

    col_spacer, col_spacer, col_spacer, col_spacer, col1, col2, col3, col4, col_spacer, col_spacer, col_spacer, col_spacer = st.columns(12)
    
    with col1:
        st.markdown("🟢 **Good**", unsafe_allow_html=True)
    with col2:
        st.markdown("🟠 **Enough**", unsafe_allow_html=True)
    with col3:
        st.markdown("🔴 **Insufficient**", unsafe_allow_html=True)
    with col4:
        st.markdown("⚪ **No data**", unsafe_allow_html=True)
    
    render_map()

    st.markdown(
        "<div style='text-align: center; color: gray; font-size: 0.875rem;'>"
        "Developed in Streamlit by CM SALVI • 2025"
        "</div>",
        unsafe_allow_html=True
    )

    
###########################################
# --- TAB 2: Generación del Informe PDF ---
###########################################

with tab2:
    #st.markdown("#### Generación de informe PDF con mapa de puntos")

    from jinja2 import Template
    from xhtml2pdf import pisa
    import contextily as ctx
    import matplotlib.pyplot as plt
    import matplotlib.patches as mpatches

    def save_geoposition_map(df, path="map_contextual.png"):
        fig, ax = plt.subplots(figsize=(12, 8))
    
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
            def color_for_dbm(dbm):
                if dbm >= -69:
                    return "#009933"  # verde
                elif -80 <= dbm < -69:
                    return "#FFA500"  # naranja
                elif dbm < -80:
                    return "#FF0000"  # rojo
                return "lightgray"
            
            colors = df_with["dBm"].apply(color_for_dbm)
            
            ax.scatter(
                df_with["Longitude - Functional Location"],
                df_with["Latitude - Functional Location"],
                color=colors,
                s=60,
                alpha=0.9,
                edgecolors="black"
            )
    
        # --- Usar bounding box dinámico ---
        min_lon, max_lon = df["Longitude - Functional Location"].min(), df["Longitude - Functional Location"].max()
        min_lat, max_lat = df["Latitude - Functional Location"].min(), df["Latitude - Functional Location"].max()
    
        #lon_margin = (max_lon - min_lon) * 0.5  # 10% margen extra
        #lat_margin = (max_lat - min_lat) * 0.5
    
        #ax.set_xlim(min_lon - lon_margin, max_lon + lon_margin)
        #ax.set_ylim(min_lat - lat_margin, max_lat + lat_margin)

        valid_df = df.dropna(subset=["Latitude - Functional Location", "Longitude - Functional Location"])
        if valid_df.empty:
            return  # o st.warning("No hay coordenadas válidas")
        
        lat_min, lat_max = valid_df["Latitude - Functional Location"].min(), valid_df["Latitude - Functional Location"].max()
        lon_min, lon_max = valid_df["Longitude - Functional Location"].min(), valid_df["Longitude - Functional Location"].max()
        
        lat_center = (lat_max + lat_min) / 2
        lon_center = (lon_max + lon_min) / 2
        
        lat_delta = (lat_max - lat_min) / 2
        lon_delta = (lon_max - lon_min) / 2
        
        margin = 0.05
        delta = max(lat_delta, lon_delta) + margin
        
        ax.set_xlim(lon_center - delta, lon_center + delta)
        ax.set_ylim(lat_center - delta, lat_center + delta)

        ctx.add_basemap(ax, crs="EPSG:4326", source=ctx.providers.OpenStreetMap.Mapnik)

        #ax.set_aspect("equal", adjustable="box")  # mantiene proporción
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

    def render_docx(context, meta, output_path="informe.docx"):
        doc = Document()
        doc.add_heading("Compte rendu visite", 0)
            
        # Datos básicos
        doc.add_paragraph(f"Date : {meta.get('date','')}")
        doc.add_paragraph(f"Région–Département : {meta.get('region','')}")
        doc.add_paragraph(f"Point Focal : {meta.get('point_focal','')}")
        doc.add_paragraph(f"Représentant ANER : {meta.get('rep_aner','')}")
        doc.add_paragraph(f"Représentant SALVI Sénégal : {meta.get('rep_salvi','')}")
        doc.add_paragraph(f"Restants/Surplus : {meta.get('restants','')}")
        doc.add_paragraph(f"Observations : {meta.get('observations','')}")
            
        # Totales del contexto
        doc.add_paragraph(f"Total ordres : {context.get('total_ordenes','')}")
        doc.add_paragraph(f"Avec couverture : {context.get('total_yes','')}  Sans : {context.get('total_no','')}")
            
        doc.save(output_path)

    # Inputs para metadatos
    report_meta = {
        "date": st.text_input("Date", value=datetime.now().strftime("%d/%m/%Y")),
        "region_departement": st.text_input("Région–Département"),
        "point_focal": st.text_input("Point Focal"),
        "rep_aner": st.text_input("Représentant ANER"),
        "rep_salvi": st.text_input("Représentant SALVI Sénégal"),
        "total_commune": st.text_input("Total lampadaires attribués à la commune"),
        "total_affectes": st.text_input("Total lampadaires affectés à la suite des visites"),
        "surplus": st.text_input("Restants/Surplus"),
        "observations": st.text_area("Observations globales"),
        "nom_salvi": st.text_input("Nom représentant SALVI"),
        "date_salvi": st.text_input("Date SALVI"),
        "nom_aner": st.text_input("Nom représentant ANER"),
        "date_aner": st.text_input("Date ANER"),
        "nom_prefet": st.text_input("Nom Préfet/Sous-Préfet"),
        "date_prefet": st.text_input("Date Préfet/Sous-Préfet"),
    }


    
    def safe_unique(df, col):
        return df[col].dropna().unique().tolist() if col in df.columns else []
    
    if st.session_state.edited_df.empty:
        st.warning("No data available. Please, load and edit on the Work Order Management tab.")
    else:
        df_full = st.session_state.df.copy()
        save_geoposition_map(df_full, "map_contextual.png")

        col1, col2, col3 = st.columns([1, 2, 1])  # columna central más ancha
        
        with col2:
            st.image("map_contextual.png", use_container_width=True)
            col_spacer, col1, col2, col3, col4, col_spacer, = st.columns(6)
    
            with col1:
                st.markdown("🟢 **Good**", unsafe_allow_html=True)
            with col2:
                st.markdown("🟠 **Enough**", unsafe_allow_html=True)
            with col3:
                st.markdown("🔴 **Insufficient**", unsafe_allow_html=True)
            with col4:
                st.markdown("⚪ **No data**", unsafe_allow_html=True)

        b1, b2, b3 = st.columns([5, 2, 4])
        with b2:
            if st.button("📄 Generate Report PDF"):
                df_full = st.session_state.df.copy()
            
                # Añadir columnas complementarias desde la edición manual
                cols_complementarias = [
                    "Name - Parent Functional Location",
                    "Name - Child Functional Location",
                    "Incident Type - Work Order",
                    "Owner - Work Order",
                    "Name - Bookable Resource Booking"
                ]
                edited_df = st.session_state.edited_df.copy()
                for col in cols_complementarias:
                    if col in edited_df.columns:
                        df_full[col] = edited_df[col]
            
                # Guardar mapa con cobertura
                save_geoposition_map(df_full, "map_contextual.png")
            
                # Obtener calles a partir de coordenadas
                df_full["Street (by coords)"] = obtener_calles_por_geocodificacion(
                    df_full,
                    "Latitude - Functional Location",
                    "Longitude - Functional Location"
                )
                calles_validas = df_full["Street (by coords)"].dropna()
                calles_unicas = calles_validas.unique().tolist()
                ordenes_por_calle = calles_validas.value_counts().to_dict()
            
                # Métricas del resumen
                total_ordenes = len(df_full)
                total_yes = (df_full["Gateway"] == "YES").sum()
                total_no = (df_full["Gateway"] == "NO").sum()
            
                # Nuevos conteos por categoría
                incident_type_counts = df_full["Incident Type - Work Order"].value_counts(dropna=True).to_dict()
                owner_counts = df_full["Owner - Work Order"].value_counts(dropna=True).to_dict()
                resource_counts = df_full["Name - Bookable Resource Booking"].value_counts(dropna=True).to_dict()
                parent_location_counts = df_full["Name - Parent Functional Location"].value_counts(dropna=True).to_dict()
                child_location_counts = df_full["Name - Child Functional Location"].value_counts(dropna=True).to_dict()
            
            
                context = {
                    "fecha": datetime.now().strftime("%d/%m/%Y"),
                    "total_ordenes": total_ordenes,
                    "total_yes": total_yes,
                    "total_no": total_no,
                    "parent_locations": safe_unique(df_full, "Name - Parent Functional Location"),
                    "child_locations": safe_unique(df_full, "Name - Child Functional Location"),
                    "calles": calles_unicas,
                    "ordenes_por_calle": ordenes_por_calle,
                    "incident_types": safe_unique(df_full, "Incident Type - Work Order"),
                    "owners": safe_unique(df_full, "Owner - Work Order"),
                    "resources": safe_unique(df_full, "Name - Bookable Resource Booking"),
                    "incident_type_counts": df_full["Incident Type - Work Order"].value_counts(dropna=True).to_dict(),
                    "owner_counts": df_full["Owner - Work Order"].value_counts(dropna=True).to_dict(),
                    "resource_counts": df_full["Name - Bookable Resource Booking"].value_counts(dropna=True).to_dict(),
                    "parent_location_counts": df_full["Name - Parent Functional Location"].value_counts(dropna=True).to_dict(),
                    "child_location_counts": df_full["Name - Child Functional Location"].value_counts(dropna=True).to_dict(),
                }
                
                render_pdf("report_template.html", context, "informe.pdf")
                with open("informe.pdf", "rb") as f:
                    st.download_button(
                        "⬇️ Download Report PDF",
                        data=f,
                        file_name="report.pdf",
                        mime="application/pdf"
                    )

            if st.button("📄 Generate Report DOCX"):
                render_docx(context, report_meta, "informe.docx")
                with open("informe.docx", "rb") as f:
                    st.download_button(
                        "⬇️ Download Report DOCX",
                        data=f,
                        file_name="informe.docx",
                        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                    )

        st.markdown(
            "<div style='text-align: center; color: gray; font-size: 0.875rem;'>"
            "Developed in Streamlit by CM SALVI • 2025"
            "</div>",
            unsafe_allow_html=True
        )
