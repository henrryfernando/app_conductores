import streamlit as st
import pandas as pd
import sqlite3
import folium
from streamlit_folium import st_folium
from streamlit_geolocation import streamlit_geolocation
import urllib.parse

# ---------------------------------------------------------
# INICIALIZACIÓN AUTOMÁTICA DE BASE DE DATOS
# ---------------------------------------------------------
def init_db():
    conn = sqlite3.connect("ambulancias.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            direccion TEXT,
            estado_movilidad TEXT,
            persona_contacto TEXT,
            telefono_contacto TEXT,
            estado TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS conductores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            estado TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS servicios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            conductor_id INTEGER,
            tipo_servicio TEXT,
            estado_actual TEXT,
            latitud REAL,
            longitud REAL,
            hora TEXT,
            incidencia TEXT,
            FOREIGN KEY(usuario_id) REFERENCES usuarios(id),
            FOREIGN KEY(conductor_id) REFERENCES conductores(id)
        )
    """)
    conn.commit()
    conn.close()

init_db()

# ---------------------------------------------------------
# CONFIGURACIÓN DE LA PÁGINA
# ---------------------------------------------------------
st.set_page_config(
    page_title="Gestión de Ambulancias y Rutas",
    page_icon="🚑",
    layout="wide"
)

DB_FILE = "ambulancias.db"

def get_connection():
    return sqlite3.connect(DB_FILE)

# ---------------------------------------------------------
# ESTILOS CSS PERSONALIZADOS
# ---------------------------------------------------------
st.markdown("""
    <style>
    .card-route {
        background-color: #f8f9fa;
        padding: 12px;
        border-radius: 8px;
        border-left: 5px solid #134074;
        margin-bottom: 10px;
    }
    .badge-wheelchair {
        background-color: #0d6efd;
        color: white;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 11px;
    }
    .badge-asistencia {
        background-color: #ffc107;
        color: black;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 11px;
    }
    .badge-autonomo {
        background-color: #198754;
        color: white;
        padding: 2px 6px;
        border-radius: 4px;
        font-size: 11px;
    }
    .badge-estado-pendiente {
        background-color: #6c757d;
        color: white;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: bold;
    }
    .badge-estado-encamino {
        background-color: #ffc107;
        color: #000;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: bold;
    }
    .badge-estado-recogido {
        background-color: #0d6efd;
        color: white;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: bold;
    }
    .badge-estado-entregado {
        background-color: #198754;
        color: white;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: bold;
    }
    .badge-estado-incidencia {
        background-color: #dc3545;
        color: white;
        padding: 3px 8px;
        border-radius: 6px;
        font-size: 12px;
        font-weight: bold;
    }
    .mobile-container {
        max-width: 500px;
        margin: 0 auto;
    }
    </style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------
# BARRA LATERAL - NAVEGACIÓN
# ---------------------------------------------------------
st.sidebar.title("🚑 Menú Principal")
opcion = st.sidebar.radio(
    "Seleccione una opción:",
    [
        "📊 Módulo 1: Resumen General / Dashboard",
        "👥 Módulo 2: Gestión de Pacientes y Conductores",
        "📅 Módulo 3: Programación de Servicios",
        "📱 Módulo 4: Vista Móvil Conductor (Hoja de Ruta)"
    ]
)

# ---------------------------------------------------------
# MÓDULO 1: RESUMEN GENERAL / DASHBOARD
# ---------------------------------------------------------
if opcion == "📊 Módulo 1: Resumen General / Dashboard":
    st.header("📊 Monitoreo General de Ambulancias")
    
    conn = get_connection()
    df_servicios = pd.read_sql_query("""
        SELECT s.id, c.nombre as Conductor, u.nombre as Paciente, u.direccion as Dirección,
               s.tipo_servicio, s.estado_actual, s.latitud, s.longitud, s.hora
        FROM servicios s
        LEFT JOIN conductores c ON s.conductor_id = c.id
        LEFT JOIN usuarios u ON s.usuario_id = u.id
    """, conn)
    conn.close()

    if not df_servicios.empty:
        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("📋 Lista de Trayectos")
            st.dataframe(df_servicios[['Conductor', 'Paciente', 'estado_actual', 'hora']], use_container_width=True)

        with col2:
            st.subheader("🗺️ Ubicación Global")
            mapa_global = folium.Map(location=[43.538100, -5.663500], zoom_start=13)

            for _, fila in df_servicios.iterrows():
                if pd.notna(fila['latitud']) and pd.notna(fila['longitud']):
                    folium.Marker(
                        [fila['latitud'], fila['longitud']],
                        popup=f"Conductor: {fila['Conductor']} | Paciente: {fila['Paciente']}",
                        tooltip=f"Estado: {fila['estado_actual']}",
                        icon=folium.Icon(color="red" if fila['estado_actual'] == "En Camino" else "blue", icon="ambulance", prefix="fa")
                    ).add_to(mapa_global)

            st_folium(mapa_global, width=700, height=450, key="mapa_dashboard")
    else:
        st.info("No hay servicios programados actualmente.")

# ---------------------------------------------------------
# MÓDULO 2: GESTIÓN DE PACIENTES Y CONDUCTORES
# ---------------------------------------------------------
elif opcion == "👥 Módulo 2: Gestión de Pacientes y Conductores":
    st.header("👥 Gestión de Pacientes y Conductores")
    
    tab_pacientes, tab_conductores = st.tabs(["👤 Pacientes", "🚗 Conductores"])

    with tab_pacientes:
        conn = get_connection()
        df_u = pd.read_sql_query("SELECT * FROM usuarios", conn)
        conn.close()
        st.subheader("Listado de Pacientes Registrados")
        st.dataframe(df_u, use_container_width=True)

    with tab_conductores:
        conn = get_connection()
        df_c = pd.read_sql_query("SELECT * FROM conductores", conn)
        conn.close()
        st.subheader("Listado de Conductores")
        st.dataframe(df_c, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 3: PROGRAMACIÓN DE SERVICIOS
# ---------------------------------------------------------
elif opcion == "📅 Módulo 3: Programación de Servicios":
    st.header("📅 Almanaque y Programación por Fecha Exacta")
    
    col_cal, col_det = st.columns([1, 1.2])

    with col_cal:
        st.subheader("📅 Selección de Fecha")
        fecha_sel = st.date_input("Fecha de Servicio:")

    with col_det:
        st.subheader("📋 Servicios Programados")
        conn = get_connection()
        df_prog = pd.read_sql_query("SELECT * FROM servicios", conn)
        conn.close()
        st.dataframe(df_prog, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 4: VISTA MÓVIL DEL CONDUCTOR (HOJA DE RUTA)
# ---------------------------------------------------------
elif opcion == "📱 Módulo 4: Vista Móvil Conductor (Hoja de Ruta)":
    st.header("📱 Panel Móvil del Conductor")
    
    conn = get_connection()
    df_cond = pd.read_sql_query("SELECT * FROM conductores WHERE estado = 'Activo'", conn)
    conn.close()

    if not df_cond.empty:
        c_sel = st.selectbox("Seleccionar Conductor:", options=df_cond['id'].tolist(),
                             format_func=lambda x: f"🚗 {df_cond[df_cond['id'] == x]['nombre'].values[0]}")

        conn = get_connection()
        query_ruta = """
            SELECT s.id as servicio_id, s.hora as Hora, s.tipo_servicio as Tipo, u.nombre as Paciente, 
                   u.estado_movilidad as Movilidad, u.direccion as Dirección, 
                   u.persona_contacto as Contacto, u.telefono_contacto as Teléfono, 
                   s.estado_actual, s.incidencia, s.latitud, s.longitud
            FROM servicios s
            JOIN usuarios u ON s.usuario_id = u.id
            WHERE s.conductor_id = ? AND u.estado = 'Activo'
            ORDER BY s.hora ASC
        """
        df_ruta = pd.read_sql_query(query_ruta, conn, params=(c_sel,))
        conn.close()

        st.markdown('<div class="mobile-container">', unsafe_allow_html=True)
        st.markdown("<h3 style='text-align: center; color: #134074;'>📋 Mi Ruta de Hoy</h3>", unsafe_allow_html=True)
        st.markdown("<hr style='margin-top:0;'>", unsafe_allow_html=True)

        st.subheader("📍 Detectar mi ubicación GPS actual")
        location = streamlit_geolocation()
        
        gps_lat, gps_lon = None, None
        if location and location.get("latitude") and location.get("longitude"):
            gps_lat = location["latitude"]
            gps_lon = location["longitude"]
            st.success(f"📍 Posición GPS detectada: {gps_lat:.5f}, {gps_lon:.5f}")

        st.markdown("---")

        if not df_ruta.empty:
            opciones_estados = ["Pendiente", "En Camino", "Paciente Recogido", "Entregado en Destino", "Incidencia"]

            for idx, fila in df_ruta.iterrows():
                s_id = fila['servicio_id']
                mov = fila['Movilidad']
                estado_actual = fila['estado_actual'] if fila['estado_actual'] in opciones_estados else "Pendiente"
                
                badge_html = (
                    '<span class="badge-wheelchair">♿ Silla</span>' if mov == 'Silla de ruedas' 
                    else '<span class="badge-asistencia">🤝 Asistencia</span>' if mov == 'Asistencia' 
                    else '<span class="badge-autonomo">🚶 Autónomo</span>'
                )

                if estado_actual == "Pendiente":
                    badge_estado_html = '<span class="badge-estado-pendiente">⏳ Pendiente</span>'
                elif estado_actual == "En Camino":
                    badge_estado_html = '<span class="badge-estado-encamino">🚗 En Camino</span>'
                elif estado_actual == "Paciente Recogido":
                    badge_estado_html = '<span class="badge-estado-recogido">👤 Paciente Recogido</span>'
                elif estado_actual == "Entregado en Destino":
                    badge_estado_html = '<span class="badge-estado-entregado">🏁 Entregado en Destino</span>'
                elif estado_actual == "Incidencia":
                    badge_estado_html = '<span class="badge-estado-incidencia">⚠️ Incidencia</span>'
                else:
                    badge_estado_html = f'<span class="badge-estado-pendiente">{estado_actual}</span>'

                st.markdown(f"""
                <div class="card-route">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong>⏰ {fila['Hora']} ({fila['Tipo']})</strong>
                        {badge_estado_html}
                    </div>
                    <div style="margin-top: 8px;">
                        <strong>👤 {fila['Paciente']}</strong> {badge_html}
                    </div>
                    <div style="font-size: 13px; margin-top: 4px;">📍 Dirección Paciente: {fila['Dirección']}</div>
                    <div style="font-size: 12px; color: #555;">📞 {fila['Contacto']}: {fila['Teléfono']}</div>
                </div>
                """, unsafe_allow_html=True)

                if estado_actual == "Paciente Recogido":
                    sound_url = "https://www.soundjay.com/buttons/sounds/button-3.mp3"
                    st.components.v1.html(
                        f"""
                        <audio autoplay>
                            <source src="{sound_url}" type="audio/mpeg">
                        </audio>
                        """,
                        height=0
                    )

                tab_paciente, tab_navegacion = st.tabs(["📍 Ubicación Paciente", "🗺️ Ruta GPS en Vivo (Google Maps)"])

                with tab_paciente:
                    lat_paciente = fila['latitud'] if pd.notna(fila['latitud']) else 43.538100
                    lon_paciente = fila['longitud'] if pd.notna(fila['longitud']) else -5.663500

                    mini_map = folium.Map(location=[lat_paciente, lon_paciente], zoom_start=15, zoom_control=False)
                    
                    folium.Marker(
                        [lat_paciente, lon_paciente],
                        popup=f"Paciente: {fila['Paciente']}",
                        tooltip=f"📍 {fila['Dirección']}",
                        icon=folium.Icon(color="red", icon="user", prefix="fa")
                    ).add_to(mini_map)

                    st_folium(mini_map, key=f"minimap_{s_id}_{idx}", width=410, height=200)

                with tab_navegacion:
                    direccion_encoded = urllib.parse.quote(fila['Dirección'])
                    
                    if gps_lat is not None and gps_lon is not None:
                        map_route_url = f"https://maps.google.com/maps?saddr={gps_lat},{gps_lon}&daddr={direccion_encoded}&output=embed"
                        st.components.v1.iframe(map_route_url, height=300, scrolling=True)
                    else:
                        st.info("💡 Haz clic en la parte superior ('Obtener ubicación GPS') para calcular la ruta exacta en vivo desde tu vehículo.")
                        map_dest_url = f"https://maps.google.com/maps?q={direccion_encoded}&output=embed"
                        st.components.v1.iframe(map_dest_url, height=300, scrolling=True)

                idx_est = opciones_estados.index(estado_actual)

                with st.expander("📍 Actualizar Estado / Ubicación GPS", expanded=False):
                    nuevo_estado = st.selectbox("Cambiar Estado del Trayecto:", opciones_estados, index=idx_est, key=f"est_{s_id}")

                    if st.button("💾 Guardar Estado y Transmitir GPS", key=f"btn_save_{s_id}"):
                        final_lat = gps_lat if gps_lat is not None else 43.538100
                        final_lon = gps_lon if gps_lon is not None else -5.663500

                        with get_connection() as conn:
                            conn.execute("""
                                UPDATE servicios 
                                SET estado_actual = ?, latitud = ?, longitud = ? 
                                WHERE id = ?
                            """, (nuevo_estado, final_lat, final_lon, s_id))
                        
                        st.toast(f"✅ Estado cambiado a '{nuevo_estado}'")
                        st.rerun()

                st.markdown("<hr style='margin:15px 0;'>", unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("No hay conductores activos para mostrar.")


