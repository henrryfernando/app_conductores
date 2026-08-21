import sqlite3
from datetime import datetime, date
import calendar
import pandas as pd
import streamlit as st
import urllib.parse
import folium
from streamlit_folium import st_folium
from streamlit_geolocation import streamlit_geolocation

DB_NAME = "transporte_mayores.db"

# ---------------------------------------------------------
# CONEXIÓN Y CREACIÓN DE BASE DE DATOS
# ---------------------------------------------------------
def get_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    with get_connection() as conn:
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                estado_movilidad TEXT DEFAULT 'Autónomo',
                direccion TEXT NOT NULL,
                persona_contacto TEXT,
                parentesco_contacto TEXT,
                telefono_contacto TEXT,
                dias_recogida TEXT,
                estado TEXT DEFAULT 'Activo'
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conductores (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                telefono TEXT,
                estado TEXT DEFAULT 'Activo'
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS servicios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER,
                tipo_servicio TEXT,
                hora TEXT NOT NULL,
                conductor_id INTEGER,
                dias_servicio TEXT,
                fecha_especifica TEXT DEFAULT NULL,
                estado_actual TEXT DEFAULT 'Pendiente',
                incidencia TEXT DEFAULT '',
                latitud REAL DEFAULT 43.538100,
                longitud REAL DEFAULT -5.663500,
                FOREIGN KEY (usuario_id) REFERENCES usuarios(id) ON DELETE CASCADE,
                FOREIGN KEY (conductor_id) REFERENCES conductores(id) ON DELETE CASCADE
            );
        """)

        cursor.execute("PRAGMA table_info(servicios);")
        columnas_existentes = [col[1] for col in cursor.fetchall()]

        columnas_a_agregar = [
            ("estado_actual", "TEXT DEFAULT 'Pendiente'"),
            ("incidencia", "TEXT DEFAULT ''"),
            ("latitud", "REAL DEFAULT 43.538100"),
            ("longitud", "REAL DEFAULT -5.663500"),
            ("fecha_especifica", "TEXT DEFAULT NULL")
        ]

        for col, dtype in columnas_a_agregar:
            if col not in columnas_existentes:
                cursor.execute(f"ALTER TABLE servicios ADD COLUMN {col} {dtype};")

        conn.commit()

init_db()

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA Y ESTILOS
# ---------------------------------------------------------
st.set_page_config(
    page_title="Rutas Senior - Gestión de Transporte",
    page_icon="🩵",
    layout="wide",
)

st.markdown("""
    <style>
    body {
        background-color: #f4f6f9;
        font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
    }
    .main .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2rem;
    }
    
    .app-header {
        background: linear-gradient(135deg, #0b2545 0%, #134074 100%);
        padding: 22px 30px;
        border-radius: 12px;
        color: white;
        margin-bottom: 25px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.08);
    }
    .app-header h1 {
        color: #ffffff;
        margin: 0;
        font-size: 26px;
        font-weight: 700;
    }
    .app-header p {
        color: #8da9c4;
        margin: 4px 0 0 0;
        font-size: 14px;
    }

    /* KPI Cards Dashboard */
    .kpi-card {
        background-color: #ffffff;
        border-radius: 10px;
        padding: 16px 20px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05);
        border-top: 4px solid #134074;
        text-align: center;
    }
    .kpi-card-title {
        font-size: 13px;
        color: #6c757d;
        font-weight: 600;
        text-transform: uppercase;
        margin-bottom: 5px;
    }
    .kpi-card-value {
        font-size: 28px;
        font-weight: 700;
        color: #0b2545;
    }

    .card-route {
        background-color: #ffffff;
        border-left: 5px solid #00b4d8;
        padding: 14px 16px;
        border-radius: 8px;
        margin-bottom: 12px;
        color: #1d2d44;
        box-shadow: 0 2px 5px rgba(0,0,0,0.05);
    }
    
    .badge-wheelchair { background-color: #e63946; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }
    .badge-autonomo { background-color: #2a9d8f; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }
    .badge-asistencia { background-color: #e9c46a; color: #1d2d44; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }
    
    .mobile-container {
        max-width: 480px;
        margin: 0 auto;
        border: 12px solid #1d2d44;
        border-radius: 30px;
        padding: 18px;
        background-color: #f8f9fa;
        box-shadow: 0 10px 25px rgba(0,0,0,0.15);
    }
    
    .cal-header { 
        font-weight: 600; 
        text-align: center; 
        background-color: #134074; 
        color: white; 
        padding: 6px; 
        border-radius: 6px; 
        font-size: 12px;
    }
    
    /* SIDEBAR TEXT COLOR & SELECTBOX CONTRAST */
    [data-testid="stSidebar"] {
        background-color: #0b2545;
    }
    [data-testid="stSidebar"] * {
        color: #e0e1dd;
    }
    [data-testid="stSidebar"] div[data-baseweb="select"] * {
        color: #1d2d44 !important;
        font-weight: 600;
    }
    [data-testid="stSidebar"] div[role="listbox"] * {
        color: #1d2d44 !important;
    }
    </style>
""", unsafe_allow_html=True)

st.markdown("""
    <div class="app-header">
        <div>
            <h1>🩵 Rutas Senior</h1>
            <p>Plataforma de Gestión de Transporte y Movilidad de Personas Mayores</p>
        </div>
    </div>
""", unsafe_allow_html=True)

opcion = st.sidebar.selectbox(
    "📌 MENÚ DE NAVEGACIÓN",
    [
        "📊 Dashboard / Resumen General",
        "📅 Hojas de Ruta por Día de Semana",
        "📆 Calendario Mensual y Programación",
        "👤 Módulo 1: Usuarios (Alta/Baja/Edición)",
        "🚘 Módulo 2: Conductores",
        "📋 Módulo 3: Programación de Servicios",
        "📱 Módulo 4: Vista Móvil Conductor (Hoja de Ruta)",
    ],
)

OPCIONES_MOVILIDAD = ["Autónomo", "Silla de ruedas", "Asistencia"]
DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
PARENTESCOS = ["Hijo/a", "Padre", "Madre", "Tío/a", "Hermano/a", "Otros"]

# ---------------------------------------------------------
# DASHBOARD GENERAL CON MAPA
# ---------------------------------------------------------
if opcion == "📊 Dashboard / Resumen General":
    st.header("📊 Vista General y Mapa de Monitoreo en Vivo")

    conn = get_connection()
    total_users = pd.read_sql_query("SELECT COUNT(*) as cant FROM usuarios WHERE estado='Activo'", conn).iloc[0]["cant"]
    total_cond = pd.read_sql_query("SELECT COUNT(*) as cant FROM conductores WHERE estado='Activo'", conn).iloc[0]["cant"]
    total_serv = pd.read_sql_query("SELECT COUNT(*) as cant FROM servicios", conn).iloc[0]["cant"]
    sillas = pd.read_sql_query("SELECT COUNT(*) as cant FROM usuarios WHERE estado_movilidad='Silla de ruedas' AND estado='Activo'", conn).iloc[0]["cant"]
    
    query_gps = """
        SELECT s.id, c.nombre as Conductor, u.nombre as Residente, 
               s.tipo_servicio as Tipo, s.estado_actual as Estado, 
               s.latitud as lat, s.longitud as lon, s.incidencia as Incidencia
        FROM servicios s
        JOIN usuarios u ON s.usuario_id = u.id
        JOIN conductores c ON s.conductor_id = c.id
        WHERE s.estado_actual != 'Pendiente' AND s.estado_actual != 'Entregado en Destino'
    """
    df_gps = pd.read_sql_query(query_gps, conn)
    df_todos_cond = pd.read_sql_query("SELECT id, nombre FROM conductores WHERE estado='Activo'", conn)
    conn.close()

    # Métricas de Estilo Tarjeta Acomodadas
    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(f'<div class="kpi-card"><div class="kpi-card-title">Residentes Activos</div><div class="kpi-card-value">{total_users}</div></div>', unsafe_allow_html=True)
    m2.markdown(f'<div class="kpi-card"><div class="kpi-card-title">Conductores Disponibles</div><div class="kpi-card-value">{total_cond}</div></div>', unsafe_allow_html=True)
    m3.markdown(f'<div class="kpi-card"><div class="kpi-card-title">Servicios Programados</div><div class="kpi-card-value">{total_serv}</div></div>', unsafe_allow_html=True)
    m4.markdown(f'<div class="kpi-card"><div class="kpi-card-title">Requieren Silla ♿</div><div class="kpi-card-value">{sillas}</div></div>', unsafe_allow_html=True)

    st.markdown("---")

    # Layout Principal: Selector a la izquierda, Mapa a la derecha
    col_izq, col_der = st.columns([1, 2.3])

    with col_izq:
        st.subheader("🚐 Selección de Vehículo")
        if not df_todos_cond.empty:
            conductor_fuerza = st.selectbox(
                "Filtrar Ambulancia / Vehículo:",
                options=["Todas las Ambulancias"] + df_todos_cond["nombre"].tolist(),
                key="dash_cond_filter"
            )
        else:
            conductor_fuerza = "Todas las Ambulancias"
            st.info("No hay conductores registrados.")

        st.markdown("""
        **Resumen de Ruta Activa**  
        Selecciona un vehículo para enfocar la posición GPS y sus datos de monitoreo en tiempo real sobre el mapa de la derecha.
        """)

    with col_der:
        st.subheader("🗺️ Monitoreo de Ambulancias en Ruta")

        # Filtrado de DataFrame GPS
        df_gps_filtered = df_gps.copy()
        if conductor_fuerza != "Todas las Ambulancias" and not df_gps.empty:
            df_gps_filtered = df_gps[df_gps['Conductor'] == conductor_fuerza]

        if not df_gps_filtered.empty:
            lat_centro = df_gps_filtered['lat'].mean()
            lon_centro = df_gps_filtered['lon'].mean()

            m = folium.Map(location=[lat_centro, lon_centro], zoom_start=15)

            for _, row in df_gps_filtered.iterrows():
                popup_text = f"<b>Conductor:</b> {row['Conductor']}<br><b>Residente:</b> {row['Residente']}<br><b>Estado:</b> {row['Estado']}<br><b>Incidencia:</b> {row['Incidencia'] or 'Ninguna'}"
                folium.Marker(
                    [row['lat'], row['lon']],
                    popup=popup_text,
                    tooltip=f"🚗 Conductor: {row['Conductor']}",
                    icon=folium.Icon(color="red", icon="ambulance", prefix="fa")
                ).add_to(m)

            st_folium(m, width=800, height=450)
            
            st.subheader("📋 Estado Detallado del Servicio")
            st.dataframe(df_gps_filtered[['Conductor', 'Residente', 'Tipo', 'Estado', 'Incidencia']], use_container_width=True)
        else:
            st.info("No hay vehículos en trayecto activo actualmente para la selección actual.")

# ---------------------------------------------------------
# HOJAS DE RUTA POR DÍA DE LA SEMANA
# ---------------------------------------------------------
elif opcion == "📅 Hojas de Ruta por Día de Semana":
    st.header("📅 Hojas de Ruta Organizadas por Día de la Semana")

    dia_sel = st.selectbox("🗓️ Selecciona un día de la semana:", DIAS_SEMANA)

    conn = get_connection()
    query_dia = """
        SELECT s.hora as Hora, s.tipo_servicio as 'Tipo de Servicio', 
               u.nombre as Paciente, u.estado_movilidad as Movilidad, 
               u.direccion as 'Dirección Recogida/Entrega', u.persona_contacto as 'Contacto', 
               u.telefono_contacto as 'Teléfono', c.nombre as 'Conductor Asignado',
               s.dias_servicio as 'Días Programados'
        FROM servicios s
        JOIN usuarios u ON s.usuario_id = u.id
        JOIN conductores c ON s.conductor_id = c.id
        WHERE s.dias_servicio LIKE ? AND u.estado = 'Activo'
        ORDER BY s.hora ASC
    """
    df_dia = pd.read_sql_query(query_dia, conn, params=(f"%{dia_sel}%",))
    conn.close()

    if not df_dia.empty:
        st.subheader(f"📋 Cronograma Global - {dia_sel} ({len(df_dia)} trayectos)")
        conductores_unicos = df_dia['Conductor Asignado'].unique()
        for cond in conductores_unicos:
            with st.expander(f"🚗 Conductor: {cond}", expanded=True):
                df_cond = df_dia[df_dia['Conductor Asignado'] == cond]
                st.dataframe(df_cond.drop(columns=['Conductor Asignado']), use_container_width=True)
        st.markdown("---")
        st.subheader("📊 Tabla Consolidada")
        st.dataframe(df_dia, use_container_width=True)
    else:
        st.warning(f"No hay servicios asignados en el sistema para el día **{dia_sel}**.")

# ---------------------------------------------------------
# CALENDARIO MENSUAL Y PROGRAMACIÓN DÍA A DÍA
# ---------------------------------------------------------
elif opcion == "📆 Calendario Mensual y Programación":
    st.header("📆 Almanaque y Programación por Fecha Exacta")

    col_cal, col_det = st.columns([1, 1.2])

    with col_cal:
        st.subheader("🗓️ Selección de Fecha")
        fecha_seleccionada = st.date_input("Selecciona un día del almanaque:", value=date.today())
        
        anio = fecha_seleccionada.year
        mes = fecha_seleccionada.month
        cal = calendar.monthcalendar(anio, mes)
        
        st.markdown(f"#### 📅 {calendar.month_name[mes]} {anio}")
        cols_dias = st.columns(7)
        dias_abr = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
        for i, d in enumerate(dias_abr):
            cols_dias[i].markdown(f"<div class='cal-header'>{d}</div>", unsafe_allow_html=True)
        
        for semana in cal:
            cols = st.columns(7)
            for i, dia in enumerate(semana):
                if dia != 0:
                    es_seleccionado = (dia == fecha_seleccionada.day)
                    btn_label = f"**[{dia}]**" if es_seleccionado else str(dia)
                    if cols[i].button(btn_label, key=f"cal_day_{dia}"):
                        st.session_state["fecha_cal"] = date(anio, mes, dia)
                        st.rerun()

    fecha_act = st.session_state.get("fecha_cal", fecha_seleccionada)

    with col_det:
        st.subheader(f"📋 Cronograma para el {fecha_act.strftime('%d/%m/%Y')}")

        conn = get_connection()
        dias_map = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves", 4: "Viernes", 5: "Sábado", 6: "Domingo"}
        nombre_dia_sem = dias_map[fecha_act.weekday()]
        fecha_str = fecha_act.strftime("%Y-%m-%d")

        query_especificos = """
            SELECT s.id, s.hora as Hora, s.tipo_servicio as Tipo, u.nombre as Paciente, 
                   c.nombre as Conductor, s.estado_actual as Estado
            FROM servicios s
            JOIN usuarios u ON s.usuario_id = u.id
            JOIN conductores c ON s.conductor_id = c.id
            WHERE s.fecha_especifica = ? AND u.estado = 'Activo'
            ORDER BY s.hora ASC
        """
        df_fecha = pd.read_sql_query(query_especificos, conn, params=(fecha_str,))

        es_rutina_semanal = False
        if df_fecha.empty:
            query_rutina = """
                SELECT s.id, s.hora as Hora, s.tipo_servicio as Tipo, u.nombre as Paciente, 
                       c.nombre as Conductor, s.estado_actual as Estado
                FROM servicios s
                JOIN usuarios u ON s.usuario_id = u.id
                JOIN conductores c ON s.conductor_id = c.id
                WHERE (s.fecha_especifica IS NULL OR s.fecha_especifica = '') 
                  AND s.dias_servicio LIKE ? AND u.estado = 'Activo'
                ORDER BY s.hora ASC
            """
            df_fecha = pd.read_sql_query(query_rutina, conn, params=(f"%{nombre_dia_sem}%",))
            if not df_fecha.empty:
                es_rutina_semanal = True

        df_activos = pd.read_sql_query("SELECT * FROM usuarios WHERE estado = 'Activo'", conn)
        df_conductores = pd.read_sql_query("SELECT * FROM conductores WHERE estado = 'Activo'", conn)
        conn.close()

        if not df_fecha.empty:
            if es_rutina_semanal:
                st.info(f"📌 Mostrando rutina habitual asignada para los **{nombre_dia_sem}s**:")
            else:
                st.success(f"✅ Hay {len(df_fecha)} trayectos programados exclusivamente para la fecha **{fecha_act.strftime('%d/%m/%Y')}**:")
            
            st.dataframe(df_fecha, use_container_width=True)
        else:
            st.info(f"No hay trayectos guardados para el {fecha_act.strftime('%d/%m/%Y')}.")

        st.markdown("---")
        st.subheader(f"➕ Añadir Trayecto Específico al {fecha_act.strftime('%d/%m/%Y')}")
        if not df_activos.empty and not df_conductores.empty:
            with st.form("form_servicio_fecha", clear_on_submit=True):
                u_id = st.selectbox("Paciente / Residente:", options=df_activos["id"].tolist(), format_func=lambda x: f"{df_activos[df_activos['id'] == x]['nombre'].values[0]}")
                tipo_s = st.selectbox("Tipo de Servicio:", ["Recogida", "Vuelta a Casa"])
                hora_s = st.time_input("Hora Programada")
                c_id = st.selectbox("Conductor:", options=df_conductores["id"].tolist(), format_func=lambda x: f"{df_conductores[df_conductores['id'] == x]['nombre'].values[0]}")

                if st.form_submit_button("Guardar Fecha Puntual"):
                    hora_str = hora_s.strftime("%H:%M")
                    with get_connection() as conn:
                        conn.execute("""
                            INSERT INTO servicios (usuario_id, tipo_servicio, hora, conductor_id, dias_servicio, fecha_especifica)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (u_id, tipo_s, hora_str, c_id, nombre_dia_sem, fecha_str))
                    st.toast("✅ Guardado con éxito")
                    st.rerun()

# ---------------------------------------------------------
# MÓDULO 1: USUARIOS
# ---------------------------------------------------------
elif opcion == "👤 Módulo 1: Usuarios (Alta/Baja/Edición)":
    st.header("👤 Gestión de Residentes y Usuarios")
    tab1, tab2, tab3 = st.tabs(["➕ Registrar Usuario", "✏️ Editar / Suspender Usuario", "🗑️ Baja Definitiva / Listado"])

    with tab1:
        with st.form("form_alta_usuario", clear_on_submit=True):
            col_nom, col_mov = st.columns([2, 1])
            with col_nom: nombre = st.text_input("Nombre Completo del Usuario*")
            with col_mov: estado_movilidad = st.selectbox("Estado de Movilidad", OPCIONES_MOVILIDAD)
            direccion = st.text_input("Dirección Exacta*")
            col1, col2, col3 = st.columns(3)
            with col1: contacto = st.text_input("Nombre Persona Contacto")
            with col2: parentesco = st.selectbox("Parentesco", PARENTESCOS)
            with col3: telefono = st.text_input("Teléfono de Contacto")
            dias_habituales = st.multiselect("Días Habituales de Recogida", DIAS_SEMANA)
            
            if st.form_submit_button("Guardar Usuario"):
                if nombre and direccion:
                    str_dias = ", ".join(dias_habituales)
                    with get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("""
                            INSERT INTO usuarios (nombre, estado_movilidad, direccion, persona_contacto, parentesco_contacto, telefono_contacto, dias_recogida)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (nombre, estado_movilidad, direccion, contacto, parentesco, telefono, str_dias))
                        conn.commit()
                    st.toast("✅ Guardado con éxito")
                    st.success(f"Usuario {nombre} registrado correctamente.")
                else: st.error("Por favor completa los campos obligatorios (*).")

    with tab2:
        conn = get_connection()
        df_usuarios = pd.read_sql_query("SELECT * FROM usuarios", conn)
        conn.close()
        if not df_usuarios.empty:
            usuario_sel = st.selectbox("Selecciona usuario:", options=df_usuarios["id"].tolist(), format_func=lambda x: f"{df_usuarios[df_usuarios['id'] == x]['nombre'].values[0]}")
            datos_user = df_usuarios[df_usuarios["id"] == usuario_sel].iloc[0]
            with st.form("form_edit_usuario"):
                e_nombre = st.text_input("Nombre Completo", value=datos_user["nombre"])
                e_direccion = st.text_input("Dirección", value=datos_user["direccion"])
                if st.form_submit_button("Actualizar"):
                    with get_connection() as conn:
                        conn.execute("UPDATE usuarios SET nombre=?, direccion=? WHERE id=?", (e_nombre, e_direccion, usuario_sel))
                    st.toast("✅ Guardado con éxito")
                    st.rerun()

    with tab3:
        conn = get_connection()
        df_u = pd.read_sql_query("SELECT * FROM usuarios", conn)
        conn.close()
        st.dataframe(df_u, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 2: CONDUCTORES
# ---------------------------------------------------------
elif opcion == "🚘 Módulo 2: Conductores":
    st.header("🚘 Gestión de Conductores")
    tab_reg, tab_edit_c, tab_del_c = st.tabs(["➕ Registrar Conductor", "✏️ Editar Conductor", "🗑️ Eliminar Conductor"])

    with tab_reg:
        with st.form("form_cond", clear_on_submit=True):
            nombre_c = st.text_input("Nombre Conductor*")
            tel_c = st.text_input("Teléfono")
            if st.form_submit_button("Guardar Conductor"):
                if nombre_c.strip():
                    with get_connection() as conn:
                        cursor = conn.cursor()
                        cursor.execute("SELECT id FROM conductores WHERE LOWER(nombre) = LOWER(?) AND telefono = ?", (nombre_c.strip(), tel_c.strip()))
                        existe = cursor.fetchone()
                        
                        if existe:
                            st.warning("⚠️ Este conductor ya se encuentra registrado con los mismos datos.")
                        else:
                            cursor.execute("INSERT INTO conductores (nombre, telefono) VALUES (?, ?)", (nombre_c.strip(), tel_c.strip()))
                            conn.commit()
                            st.toast("✅ Guardado con éxito")
                            st.success(f"Conductor {nombre_c} registrado.")
                            st.rerun()
                else:
                    st.error("Ingresa el nombre del conductor.")

    with tab_edit_c:
        conn = get_connection()
        df_c_list = pd.read_sql_query("SELECT * FROM conductores", conn)
        conn.close()

        if not df_c_list.empty:
            c_edit_id = st.selectbox("Selecciona conductor para editar:", options=df_c_list["id"].tolist(), format_func=lambda x: f"{df_c_list[df_c_list['id'] == x]['nombre'].values[0]} ({df_c_list[df_c_list['id'] == x]['telefono'].values[0]})", key="sel_edit_c")
            datos_c = df_c_list[df_c_list["id"] == c_edit_id].iloc[0]

            with st.form("form_edit_cond"):
                edit_nom = st.text_input("Nombre Conductor", value=datos_c["nombre"])
                edit_tel = st.text_input("Teléfono", value=datos_c["telefono"])
                if st.form_submit_button("Guardar Cambios"):
                    with get_connection() as conn:
                        conn.execute("UPDATE conductores SET nombre = ?, telefono = ? WHERE id = ?", (edit_nom, edit_tel, c_edit_id))
                    st.toast("✅ Guardado con éxito")
                    st.rerun()
        else:
            st.info("No hay conductores registrados.")

    with tab_del_c:
        conn = get_connection()
        df_c_del = pd.read_sql_query("SELECT * FROM conductores", conn)
        conn.close()

        if not df_c_del.empty:
            c_del_id = st.selectbox("Selecciona conductor para eliminar:", options=df_c_del["id"].tolist(), format_func=lambda x: f"{df_c_del[df_c_del['id'] == x]['nombre'].values[0]} - {df_c_del[df_c_del['id'] == x]['telefono'].values[0]}", key="sel_del_c")
            if st.button("🗑️ Confirmar Eliminar Conductor", type="primary"):
                with get_connection() as conn:
                    conn.execute("DELETE FROM conductores WHERE id = ?", (c_del_id,))
                st.toast("✅ Guardado con éxito")
                st.success("Conductor eliminado correctamente.")
                st.rerun()
        else:
            st.info("No hay conductores registrados para eliminar.")

    st.markdown("---")
    st.subheader("📋 Lista de Conductores Registrados")
    conn = get_connection()
    df_todos_cond = pd.read_sql_query("SELECT id, nombre as Nombre, telefono as Teléfono, estado as Estado FROM conductores", conn)
    conn.close()
    st.dataframe(df_todos_cond, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 3: PROGRAMACIÓN GENERAL DE SERVICIOS
# ---------------------------------------------------------
elif opcion == "📋 Módulo 3: Programación de Servicios":
    st.header("📋 Programación General y Asignación de Trayectos")
    conn = get_connection()
    df_activos = pd.read_sql_query("SELECT * FROM usuarios WHERE estado = 'Activo'", conn)
    df_conductores = pd.read_sql_query("SELECT * FROM conductores WHERE estado = 'Activo'", conn)
    conn.close()

    col1, col2 = st.columns([1, 1.2])

    with col1:
        st.subheader("Asignar Nuevo Trayecto")
        if not df_activos.empty and not df_conductores.empty:
            with st.form("form_servicio", clear_on_submit=True):
                u_id = st.selectbox("Usuario:", options=df_activos["id"].tolist(), format_func=lambda x: f"{df_activos[df_activos['id'] == x]['nombre'].values[0]}")
                tipo_s = st.selectbox("Tipo:", ["Recogida", "Vuelta a Casa"])
                hora_s = st.time_input("Hora Programada")
                c_id = st.selectbox("Conductor:", options=df_conductores["id"].tolist(), format_func=lambda x: f"{df_conductores[df_conductores['id'] == x]['nombre'].values[0]}")
                dias_serv = st.multiselect("Días de Aplicación:", DIAS_SEMANA)

                if st.form_submit_button("Programar Servicio"):
                    if dias_serv:
                        str_dias = ", ".join(dias_serv)
                        hora_str = hora_s.strftime("%H:%M")
                        with get_connection() as conn:
                            conn.execute("INSERT INTO servicios (usuario_id, tipo_servicio, hora, conductor_id, dias_servicio) VALUES (?, ?, ?, ?, ?)",
                                         (u_id, tipo_s, hora_str, c_id, str_dias))
                        st.toast("✅ Guardado con éxito")
                        st.rerun()

    with col2:
        st.subheader("Servicios Programados")
        conn = get_connection()
        query_serv = """
            SELECT s.id, s.usuario_id, s.conductor_id, u.nombre as Usuario, 
                   s.tipo_servicio as Tipo, s.hora as Hora, c.nombre as Conductor, s.dias_servicio as Días
            FROM servicios s
            JOIN usuarios u ON s.usuario_id = u.id
            JOIN conductores c ON s.conductor_id = c.id
            ORDER BY s.hora ASC
        """
        df_servicios = pd.read_sql_query(query_serv, conn)
        conn.close()

        if not df_servicios.empty:
            st.dataframe(df_servicios[["id", "Usuario", "Tipo", "Hora", "Conductor", "Días"]], use_container_width=True)
            
            tab_edit, tab_del = st.tabs(["✏️ Editar Servicio", "❌ Cancelar Servicio"])
            with tab_edit:
                serv_edit_id = st.selectbox("Selecciona servicio a editar:", options=df_servicios["id"].tolist(), key="sel_edit_serv")
                datos_serv = df_servicios[df_servicios["id"] == serv_edit_id].iloc[0]
                
                with st.form("form_edit_servicio"):
                    e_tipo_s = st.selectbox("Tipo de Servicio:", ["Recogida", "Vuelta a Casa"], index=0 if datos_serv["Tipo"] == "Recogida" else 1)
                    
                    hora_str = str(datos_serv["Hora"])
                    fmt = "%H:%M:%S" if len(hora_str) == 8 else "%H:%M"
                    e_hora_s = st.time_input("Hora Programada", value=datetime.strptime(hora_str, fmt).time())
                    
                    dias_val = datos_serv["Días"]
                    dias_lista = str(dias_val).split(", ") if pd.notna(dias_val) and dias_val is not None else []
                    default_dias = [d for d in dias_lista if d in DIAS_SEMANA]
                    
                    e_dias_serv = st.multiselect("Días:", DIAS_SEMANA, default=default_dias)
                    
                    if st.form_submit_button("Guardar Cambios"):
                        with get_connection() as conn:
                            conn.execute("UPDATE servicios SET tipo_servicio=?, hora=?, dias_servicio=? WHERE id=?",
                                         (e_tipo_s, e_hora_s.strftime("%H:%M"), ", ".join(e_dias_serv), serv_edit_id))
                        st.toast("✅ Guardado con éxito")
                        st.rerun()

            with tab_del:
                serv_del = st.selectbox("Seleccionar para eliminar:", options=df_servicios["id"].tolist(), key="sel_del_serv")
                if st.button("❌ Eliminar Servicio"):
                    with get_connection() as conn:
                        conn.execute("DELETE FROM servicios WHERE id = ?", (serv_del,))
                    st.toast("✅ Guardado con éxito")
                    st.rerun()

# ---------------------------------------------------------
# MÓDULO 4: VISTA MÓVIL DEL CONDUCTOR (MI RUTA DE HOY)
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

        if not df_ruta.empty:
            opciones_estados = ["Pendiente", "En Camino", "Paciente Recogido", "Entregado en Destino", "Incidencia"]

            for idx, fila in df_ruta.iterrows():
                s_id = fila['servicio_id']
                mov = fila['Movilidad']
                
                badge_html = (
                    '<span class="badge-wheelchair">♿ Silla</span>' if mov == 'Silla de ruedas' 
                    else '<span class="badge-asistencia">🤝 Asistencia</span>' if mov == 'Asistencia' 
                    else '<span class="badge-autonomo">🚶 Autónomo</span>'
                )

                st.markdown(f"""
                <div class="card-route">
                    <div style="display: flex; justify-content: space-between;">
                        <strong>⏰ {fila['Hora']}</strong>
                        <small><b>{fila['Tipo']}</b></small>
                    </div>
                    <div style="margin-top: 5px;">
                        <strong>👤 {fila['Paciente']}</strong> {badge_html}
                    </div>
                    <div style="font-size: 13px; margin-top: 4px;">📍 {fila['Dirección']}</div>
                    <div style="font-size: 12px; color: #555;">📞 {fila['Contacto']}: {fila['Teléfono']}</div>
                </div>
                """, unsafe_allow_html=True)

                # --- MINIMAPA GPS ESTILO GOOGLE MAPS ---
                lat_amb = fila['latitud'] if pd.notna(fila['latitud']) else 43.538100
                lon_amb = fila['longitud'] if pd.notna(fila['longitud']) else -5.663500

                mini_map = folium.Map(location=[lat_amb, lon_amb], zoom_start=15, zoom_control=False)
                
                folium.Marker(
                    [lat_amb, lon_amb],
                    popup=f"Ambulancia / Vehículo ({fila['Tipo']})",
                    tooltip="🚑 Ubicación GPS de Ambulancia",
                    icon=folium.Icon(color="red", icon="ambulance", prefix="fa")
                ).add_to(mini_map)

                st_folium(mini_map, key=f"minimap_{s_id}_{idx}", width=410, height=200)

                # Enlace directo a Google Maps
                direccion_encoded = urllib.parse.quote(fila['Dirección'])
                st.markdown(f"[🗺️ Abrir Navegación en Google Maps](https://www.google.com/maps/search/?api=1&query={direccion_encoded})")

                # Selector de cambio de Estado y capturador GPS automático
                estado_actual_val = fila['estado_actual'] if fila['estado_actual'] in opciones_estados else "Pendiente"
                idx_est = opciones_estados.index(estado_actual_val)

                with st.expander("📍 Actualizar Estado / Ubicación GPS", expanded=False):
                    nuevo_estado = st.selectbox("Estado del Trayecto:", opciones_estados, index=idx_est, key=f"est_{s_id}")
                    
                    st.write("Presiona para obtener tu ubicación GPS:")
                    location = streamlit_geolocation()

                    if location and location.get("latitude") and location.get("longitude"):
                        nueva_lat = location["latitude"]
                        nueva_lon = location["longitude"]
                        st.success(f"📍 GPS Detectado: {nueva_lat:.5f}, {nueva_lon:.5f}")
                    else:
                        nueva_lat = float(lat_amb)
                        nueva_lon = float(lon_amb)

                    if st.button("💾 Guardar Estado y GPS", key=f"btn_save_{s_id}"):
                        with get_connection() as conn:
                            conn.execute("""
                                UPDATE servicios 
                                SET estado_actual = ?, latitud = ?, longitud = ? 
                                WHERE id = ?
                            """, (nuevo_estado, nueva_lat, nueva_lon, s_id))
                        st.toast("✅ Estado y ubicación GPS actualizados")
                        st.rerun()

                st.markdown("<hr style='margin:15px 0;'>", unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("No hay conductores activos para mostrar.")

