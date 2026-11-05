import pandas as pd
import streamlit as st

# ============================================================
#  Configuración de la página
# ============================================================
st.set_page_config(
    page_title="Nacimiento Estelar",
    layout="wide"
)

st.markdown("""
    <style>
    .main { padding: 2rem; }
    .stAlert { margin-top: 1rem; }
    </style>
""", unsafe_allow_html=True)

# Nombres que se reconocen como columna de tiempo (Grafana suele exportar como _time o Time)
CANDIDATAS_TIEMPO = ["time", "_time", "timestamp", "fecha", "date", "datetime"]


# ============================================================
#  Preparación de datos
# ============================================================
def preparar_datos(df):
    """Detecta la columna de tiempo y las columnas numéricas del CSV.
    Devuelve el DataFrame procesado, la lista de variables numéricas
    y el nombre original de la columna de tiempo (o None).
    """
    df = df.copy()

    # 1. Columna de tiempo → índice
    col_tiempo = next(
        (c for c in df.columns if str(c).strip().lower() in CANDIDATAS_TIEMPO),
        None
    )
    if col_tiempo is not None:
        df[col_tiempo] = pd.to_datetime(df[col_tiempo], errors="coerce")
        df = df.dropna(subset=[col_tiempo]).set_index(col_tiempo).sort_index()
        df.index.name = "Time"

    # 2. Columnas de texto que en realidad son números (p. ej. "23,5")
    for c in df.columns:
        if not pd.api.types.is_numeric_dtype(df[c]):
            convertida = pd.to_numeric(
                df[c].astype(str).str.replace(",", ".", regex=False),
                errors="coerce"
            )
            if convertida.notna().mean() >= 0.9:
                df[c] = convertida

    # 3. Variables numéricas disponibles para el análisis
    numericas = df.select_dtypes(include="number").columns.tolist()
    return df, numericas, col_tiempo


def normalizar(df):
    """Escala cada columna a 0–1 para comparar variables con unidades distintas."""
    rango = (df.max() - df.min()).replace(0, 1)
    return (df - df.min()) / rango


# ============================================================
#  Encabezado principal
# ============================================================
st.title("🌌 Análisis de datos recibidos")

banner_html = """
    <style>
    .banner-container {
        width: 100%;
        height: 350px; /* Puedes cambiar la altura del banner aquí */
        overflow: hidden;
        border-radius: 12px;
        margin-bottom: 1.5rem;
        box-shadow: 0 8px 16px rgba(0,0,0,0.2);
    }
    .banner-container img {
        width: 100%;
        height: 100%;
        object-fit: cover; /* Evita que la imagen se estire o deforme */
        object-position: center; /* Asegura que el centro de la imagen siempre sea visible */
        pointer-events: none;
    }
    </style>
    <div class="banner-container">
        <!-- Reemplaza el enlace de abajo por el enlace Raw de tu GitHub -->
        <img src="https://raw.githubusercontent.com/tu-usuario/varanalisis/main/banner.jpg" alt="Banner Genesis">
    </div>
"""
st.markdown(banner_html, unsafe_allow_html=True)

st.markdown("""
    Esta aplicación analiza los datos telemétricos exportados desde Grafana, 
    registrando la interacción de los usuarios frente al stand físico (sensores ultrasónicos) 
    durante las distintas fases interactuables en unity.
""")

# ============================================================
#  Carga del archivo
# ============================================================
uploaded_file = st.file_uploader("Seleccione el archivo CSV exportado desde Grafana", type=["csv"])

if uploaded_file is not None:
    try:
        df_original = pd.read_csv(uploaded_file)
        df1, variables, col_tiempo = preparar_datos(df_original)

        if not variables:
            st.error("No se encontraron columnas numéricas en el archivo. Verifica el formato de Grafana.")
            st.stop()

        st.success(
            f"Se detectaron **{len(variables)}** variable(s) interactiva(s): "
            + ", ".join(f"`{v}`" for v in variables)
        )
        if col_tiempo is None:
            st.info("No se encontró columna de tiempo; se usará el número de lectura del Arduino como eje X.")

        tab1, tab2, tab3, tab4 = st.tabs(
            ["📈 Visualización", "📊 Estadísticas y Alertas", "🔍 Filtros de Interacción", "⚙️ Hardware del Proyecto"]
        )

        # ----------------------------------------------------
        #  TAB 1 · Visualización
        # ----------------------------------------------------
        with tab1:
            st.subheader("Dinámica del Usuario en Tiempo Real")

            col_a, col_b = st.columns([3, 1])
            with col_a:
                vars_graf = st.multiselect(
                    "Sensores a graficar",
                    variables,
                    default=variables if len(variables) <= 4 else variables[:2]
                )
            with col_b:
                chart_type = st.selectbox("Tipo de gráfico", ["Área", "Línea", "Barra"])

            normalizado = st.checkbox(
                "Normalizar escalas (0–1)",
                help="Útil si tienes variables con escalas muy distintas (ej. proximidad vs temperatura)."
            )

            if not vars_graf:
                st.warning("Seleccione al menos un sensor de la lista.")
            else:
                datos_graf = df1[vars_graf]
                if normalizado:
                    datos_graf = normalizar(datos_graf)

                if chart_type == "Línea":
                    st.line_chart(datos_graf)
                elif chart_type == "Área":
                    st.area_chart(datos_graf)
                else:
                    st.bar_chart(datos_graf)

            if st.checkbox("Mostrar matriz de datos crudos"):
                st.dataframe(df1)

        # ----------------------------------------------------
        #  TAB 2 · Estadísticas y Alertas
        # ----------------------------------------------------
        with tab2:
            st.subheader("Análisis Estadístico de la Experiencia")

            st.write("#### Resumen del comportamiento del sensor")
            st.dataframe(df1[variables].describe().T.round(3))

            st.write("#### Alertas por Umbral (Reglas de Negocio)")
            var_stats = st.selectbox("Selecciona una variable para evaluar umbrales:", variables, key="var_stats")
            serie = df1[var_stats].dropna()

            m1, m2, m3, m4 = st.columns(4)
            m1.metric("Promedio de lectura", f"{serie.mean():.2f}")
            m2.metric("Pico Máximo", f"{serie.max():.2f}")
            m3.metric("Valle Mínimo", f"{serie.min():.2f}")
            m4.metric("Desv. Estándar (Ruido)", f"{serie.std():.2f}")

            # Lógica adaptada para identificar si la mano estuvo mucho tiempo fuera de rango
            if serie.max() <= 1.5:  # Si los datos están normalizados entre 0 y 1
                limite_superior = 0.8
                limite_inferior = 0.2
            else: # Si los datos vienen puros del sensor en centímetros
                limite_superior = serie.quantile(0.8)
                limite_inferior = serie.quantile(0.2)

            fuera_rango = serie[serie > limite_superior].count()
            muy_cerca = serie[serie < limite_inferior].count()
            
            st.info(f"**Análisis de uso para `{var_stats}`:** El usuario llevó el sensor al límite superior ({limite_superior:.2f}) en **{fuera_rango}** lecturas, y al límite inferior ({limite_inferior:.2f}) en **{muy_cerca}** lecturas.")

            if len(variables) >= 2:
                st.write("#### Correlación entre variables interactivas")
                st.dataframe(df1[variables].corr().round(2))
                st.caption(
                    "Valores cercanos a 1 o −1 indican una relación directa fuerte en los controles del usuario; "
                    "cercanos a 0, movimientos independientes."
                )

        # ----------------------------------------------------
        #  TAB 3 · Filtros
        # ----------------------------------------------------
        with tab3:
            st.subheader("Aislamiento de Fases y Filtros")

            var_filtro = st.selectbox("Variable base para el filtro", variables, key="var_filtro")
            min_value = float(df1[var_filtro].min())
            max_value = float(df1[var_filtro].max())

            if min_value == max_value:
                st.warning(f"⚠️ Todos los valores de `{var_filtro}` están estáticos en: {min_value:.2f}")
                st.info("No hubo variación en este control durante la grabación del CSV.")
                st.dataframe(df1)
            else:
                rango = st.slider(
                    f"Filtrar momentos donde `{var_filtro}` estuvo entre:",
                    min_value,
                    max_value,
                    (min_value, max_value),
                    key=f"rango_{var_filtro}"
                )

                filtrado = df1[df1[var_filtro].between(rango[0], rango[1])]
                st.write(
                    f"**{len(filtrado)}** de {len(df1)} registros capturados cumplen esta condición:"
                )
                st.dataframe(filtrado)

                st.download_button(
                    label="⬇️ Descargar segmento aislado (CSV)",
                    data=filtrado.to_csv().encode("utf-8"),
                    file_name=f"genesis_filtrado_{var_filtro}.csv",
                    mime="text/csv",
                )

        # ----------------------------------------------------
        #  TAB 4 · Información del sitio
        # ----------------------------------------------------
        with tab4:
            st.subheader("Arquitectura del Sistema - Proyecto Genesis")

            col1, col2 = st.columns(2)

            with col1:
                st.write("### Hardware de Entrada")
                st.write("- **Microcontrolador:** Arduino Uno R3")
                st.write("- **Sensores principales:** HC-SR04 (Distancia / Masa), Botón Pulsador (Ignición / Temperatura)")
                st.write("- **Frecuencia de muestreo:** ~10ms (Hardware) / 500ms (Base de Datos)")

            with col2:
                st.write("### Software y Entorno")
                st.write("- **Motor Gráfico:** Unity 6 (VFX Graph & Shader Graph)")
                st.write("- **Base de Datos:** InfluxDB Cloud")
                st.write("- **Dashboard en vivo:** Grafana")
                st.write(f"- **Registros en esta sesión:** {len(df1)} lecturas procesadas")
                if col_tiempo is not None and len(df1) > 0:
                    st.write(f"- **Hora de inicio:** {df1.index.min():%Y-%m-%d %H:%M:%S}")
                    st.write(f"- **Hora de fin:** {df1.index.max():%Y-%m-%d %H:%M:%S}")

    except Exception as e:
        st.error(f"Error al procesar el archivo: {str(e)}")
        st.info("Asegúrate de haber descargado el CSV correctamente desde el panel Inspect > Data en Grafana.")
else:
    st.warning("Por favor, sube el archivo CSV de InfluxDB/Grafana para visualizar la telemetría de tu estrella.")

# ============================================================
#  Pie de página
# ============================================================
st.markdown("""
    ---
    *Panel de análisis desarrollado para el seguimiento de interacciones físicas desde unity.*  
    *Universidad EAFIT - Diseño Interactivo*
""")
