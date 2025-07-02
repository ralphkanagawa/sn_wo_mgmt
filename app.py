import streamlit as st
import pandas as pd
import io
from datetime import date, datetime

from config_loader import load_config, load_excel_template_columns
from file_processing import load_and_process_files
from editor_utils import apply_bulk_value, generate_time_windows, fill_temporal_columns
from visualizations import render_map

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

    # Cargar archivos CSV
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
    
    # Asegurar que todos los campos del template estén en el DataFrame
    disp = st.session_state.df.copy()
    for c in template_cols:
        if c not in disp.columns:
            disp[c] = ""
    disp = disp[template_cols]
    st.session_state.edited_df = disp if st.session_state.edited_df.empty else st.session_state.edited_df
    
    # Controles superiores
    col_left, col_spacer, col_right = st.columns([2, 6, 2])
    
    with col_left:
        if st.button("🔁 Volver a cargar archivos"):
            for key in ["processed", "df", "geo_df", "cov_df", "edited_df", "latest_edited"]:
                st.session_state.pop(key, None)
            st.rerun()
    
    with col_right:
        if st.button("💾 Guardar cambios"):
            st.session_state.edited_df = st.session_state.latest_edited.copy()
    
    # Tabla editable
    edited = st.data_editor(
        st.session_state.edited_df,
        num_rows="dynamic",
        use_container_width=True,
        key="editor"
    )
    st.session_state.latest_edited = edited.copy()
    
    # Controles por columna
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
    
    # Mapa interactivo
    render_map()
    
    st.caption("Desarrollado en Streamlit • Última actualización: 2025-06-30")
    

# --- TAB 2: Generación del Informe PDF ---
with tab2:
    st.markdown("### Generación de informe PDF")

    def save_static_map(df, path="map.png"):
        fig, ax = plt.subplots(figsize=(8, 6))
        scatter = ax.scatter(
            df["Longitude - Functional Location"],
            df["Latitude - Functional Location"],
            c=df["dBm"],
            cmap="RdYlGn", s=20, alpha=0.8
        )
        ax.set_title("Mapa de cobertura (estático)")
        ax.set_xlabel("Longitud")
        ax.set_ylabel("Latitud")
        plt.colorbar(scatter, label="dBm")
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(path)
        plt.close()

    def render_pdf(template_path, context, output_path):
        with open(template_path, "r", encoding="utf-8") as f:
            html = Template(f.read()).render(**context)
        with open(output_path, "wb") as f:
            pisa.CreatePDF(html, dest=f)

    if st.session_state.edited_df.empty:
        st.warning("No hay datos disponibles. Por favor, carga y edita datos en la pestaña anterior.")
    else:
        df = st.session_state.edited_df.copy()
        save_static_map(df, "map.png")
        st.image("map.png", caption="Mapa de cobertura (estático)", use_column_width=True)

        if st.button("📄 Generar informe PDF"):
            context = {
                "fecha": datetime.now().strftime("%d/%m/%Y"),
                "total_ordenes": len(df),
                "total_yes": (df["Gateway"] == "YES").sum(),
                "total_no": (df["Gateway"] == "NO").sum(),
                "columnas": df.columns.tolist(),
                "filas": df.values.tolist()
            }
            render_pdf("report_template.html", context, "informe.pdf")
            with open("informe.pdf", "rb") as f:
                st.download_button("⬇️ Descargar informe PDF", data=f, file_name="informe.pdf", mime="application/pdf")
