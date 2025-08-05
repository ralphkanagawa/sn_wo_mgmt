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

# Configuración de la página  #
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
tab1, tab2 = st.tabs(["Work Order Management", "Report generator"])

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

    # Añadir columna 'ID punto' si no existe
    if "ID point" not in disp.columns:
        disp.insert(0, "ID point", range(1, len(disp) + 1))
    
    for c in template_cols:
        if c not in disp.columns:
            disp[c] = ""
    disp = disp[["ID point"] + [col for col in template_cols if col != "ID point"]]

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

    # Validación de valores inválidos para resaltar en la tabla
    df_for_editor = st.session_state.edited_df.copy()
    invalid_mask = pd.DataFrame(False, index=df_for_editor.index, columns=df_for_editor.columns)
    
    for col in config.required_columns:
        if col in config.dropdown_values and col in df_for_editor.columns:
            allowed = config.dropdown_values[col]
            invalid = ~df_for_editor[col].isin(allowed)
            invalid_mask[col] = invalid
    
    # Aplicar estilo: celdas inválidas resaltadas en rojo claro
    styled_df = df_for_editor.style.apply(
        lambda _: invalid_mask.replace({True: "background-color: #ffcccc", False: ""}),
        axis=None
    )
    
    # Mostrar tabla con estilos aplicados
    st.dataframe(styled_df, use_container_width=True)
    
    # Guardar edición para otros usos
    st.session_state.latest_edited = df_for_editor.copy()
    
    # Mostrar aviso si hay errores
    if invalid_mask.any().any():
        st.warning("⚠️ Se han detectado celdas con valores inválidos (marcadas en rojo). Revísalas antes de exportar.")





        # 🔎 Resaltar fila seleccionada desde el mapa
    if "selected_row_id" in st.session_state:
        selected_id = st.session_state["selected_row_id"]
        st.markdown(f"<span style='color:green;'>🟢 Selected point: row {selected_id + 1}</span>", unsafe_allow_html=True)
    
        # Opcional: hacer scroll o marcar visualmente (Streamlit no permite highlight directo, pero puedes informar al usuario)

    st.session_state.latest_edited = edited.copy()

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
                st.error(f"No se puede generar el Excel. Las siguientes columnas requeridas tienen valores vacíos: {', '.join(missing_values)}")
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
        fig, ax = plt.subplots(figsize=(10, 5))

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

        ctx.add_basemap(ax, crs="EPSG:4326", source=ctx.providers.OpenStreetMap.Mapnik)
        
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
                        file_name="informe.pdf",
                        mime="application/pdf"
                    )
    
        st.markdown(
            "<div style='text-align: center; color: gray; font-size: 0.875rem;'>"
            "Developed in Streamlit by CM SALVI • 2025"
            "</div>",
            unsafe_allow_html=True
        )
    
