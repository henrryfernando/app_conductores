import sqlite3
from datetime import datetime, date
import calendar
import pandas as pd
import streamlit as st
import urllib.parse
import folium
from streamlit_folium import st_folium
from streamlit_geolocation import streamlit_geolocation
import hashlib
import os

DB_NAME = "transporte_mayores.db"

# ---------------------------------------------------------
# FUNCIONES DE SEGURIDAD (HASH DE CONTRASEÑAS)
# ---------------------------------------------------------
def hash_password(password: str, salt: bytes = None) -> str:
    if salt is None:
        salt = os.urandom(16)
    key = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, 100000)
    return salt.hex() + ":" + key.hex()

def verify_password(stored_password: str, provided_password: str) -> bool:
    try:
        salt_hex, key_hex = stored_password.split(":")
        salt = bytes.fromhex(salt_hex)
        new_key = hashlib.pbkdf2_hmac('sha256', provided_password.encode('utf-8'), salt, 100000)
        return new_key.hex() == key_hex
    except Exception:
        return False

# ---------------------------------------------------------
# CONEXIÓN Y CREACIÓN DE BASE DE DATOS EXTENDIDA
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

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS app_usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nombre TEXT NOT NULL,
                apellidos TEXT NOT NULL,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password TEXT NOT NULL,
                rol TEXT NOT NULL,
                estado TEXT DEFAULT 'Activo',
                fecha_creacion TEXT,
                ultimo_acceso TEXT,
                conductor_id INTEGER DEFAULT NULL,
                FOREIGN KEY (conductor_id) REFERENCES conductores(id) ON DELETE SET NULL
            );
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS roles_permisos (
                rol TEXT NOT NULL,
                modulo TEXT NOT NULL,
                p_ver INTEGER DEFAULT 0,
                p_crear INTEGER DEFAULT 0,
                p_editar INTEGER DEFAULT 0,
                p_eliminar INTEGER DEFAULT 0,
                PRIMARY KEY (rol, modulo)
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

        cursor.execute("SELECT COUNT(*) FROM app_usuarios;")
        if cursor.fetchone()[0] == 0:
            pass_admin = hash_password("admin123")
            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cursor.execute("""
                INSERT INTO app_usuarios (nombre, apellidos, username, email, password, rol, estado, fecha_creacion)
                VALUES ('Administrador', 'Sistema', 'admin', 'admin@rutassenior.com', ?, 'Administrador', 'Activo', ?)
            """, (pass_admin, now_str))

        cursor.execute("SELECT COUNT(*) FROM roles_permisos;")
        if cursor.fetchone()[0] == 0:
            permisos_defecto = [
                ('Administrador', 'Dashboard', 1, 1, 1, 1),
                ('Administrador', 'HojasRuta', 1, 1, 1, 1),
                ('Administrador', 'Calendario', 1, 1, 1, 1),
                ('Administrador', 'Pacientes', 1, 1, 1, 1),
                ('Administrador', 'Conductores', 1, 1, 1, 1),
                ('Administrador', 'Servicios', 1, 1, 1, 1),
                ('Administrador', 'VistaMovil', 1, 1, 1, 1),
                ('Administrador', 'GestionUsuarios', 1, 1, 1, 1),
                ('Consultor', 'Dashboard', 1, 0, 0, 0),
                ('Consultor', 'HojasRuta', 1, 0, 0, 0),
                ('Consultor', 'Calendario', 1, 1, 1, 0),
                ('Consultor', 'Pacientes', 1, 1, 1, 0),
                ('Consultor', 'Conductores', 1, 0, 0, 0),
                ('Consultor', 'Servicios', 1, 1, 1, 0),
                ('Consultor', 'VistaMovil', 1, 0, 0, 0),
                ('Consultor', 'GestionUsuarios', 0, 0, 0, 0),
                ('Conductor', 'Dashboard', 0, 0, 0, 0),
                ('Conductor', 'HojasRuta', 0, 0, 0, 0),
                ('Conductor', 'Calendario', 0, 0, 0, 0),
                ('Conductor', 'Pacientes', 0, 0, 0, 0),
                ('Conductor', 'Conductores', 0, 0, 0, 0),
                ('Conductor', 'Servicios', 0, 0, 0, 0),
                ('Conductor', 'VistaMovil', 1, 1, 1, 0),
                ('Conductor', 'GestionUsuarios', 0, 0, 0, 0),
            ]
            cursor.executemany("INSERT INTO roles_permisos VALUES (?, ?, ?, ?, ?, ?)", permisos_defecto)

        conn.commit()

init_db()

# ---------------------------------------------------------
# FUNCIONES AUXILIARES DE CONTROL DE ACCESO (RBC)
# ---------------------------------------------------------
def obtener_permiso(rol, modulo):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT p_ver, p_crear, p_editar, p_eliminar FROM roles_permisos WHERE rol = ? AND modulo = ?", (rol, modulo))
    res = cursor.fetchone()
    conn.close()
    if res:
        return {"ver": bool(res[0]), "crear": bool(res[1]), "editar": bool(res[2]), "eliminar": bool(res[3])}
    return {"ver": False, "crear": False, "editar": False, "eliminar": False}

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
    
    /* Badges de Estados de Trayecto */
    .status-pendiente { background-color: #6c757d; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }
    .status-encamino { background-color: #0284c7; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }
    .status-recogido { background-color: #f59e0b; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }
    .status-entregado { background-color: #10b981; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }
    .status-incidencia { background-color: #ef4444; color: white; padding: 4px 10px; border-radius: 12px; font-size: 11px; font-weight: 600; }

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

# ---------------------------------------------------------
# PANTALLA DE LOGIN Y AUTENTICACIÓN DE SESIÓN
# ---------------------------------------------------------
if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False
if "user_info" not in st.session_state:
    st.session_state["user_info"] = None

if not st.session_state["authenticated"]:
    st.markdown("""
        <div class="app-header" style="text-align: center;">
            <h1>🩵 Rutas Senior</h1>
            <p>Acceso Protegido al Sistema de Gestión de Transporte</p>
        </div>
    """, unsafe_allow_html=True)

    col_center1, col_center2, col_center3 = st.columns([1, 1.2, 1])
    with col_center2:
        st.subheader("🔑 Iniciar Sesión")
        tab_login, tab_reset = st.tabs(["Acceso", "Recuperar Contraseña"])

        with tab_login:
            with st.form("form_login"):
                usuario_input = st.text_input("Usuario o Correo Electrónico")
                password_input = st.text_input("Contraseña", type="password")
                recordar = st.checkbox("Recordar sesión")
                btn_login = st.form_submit_button("Ingresar al Sistema", use_container_width=True)

                if btn_login:
                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        SELECT id, nombre, apellidos, username, email, password, rol, estado, conductor_id 
                        FROM app_usuarios 
                        WHERE (username = ? OR email = ?)
                    """, (usuario_input.strip(), usuario_input.strip()))
                    user = cursor.fetchone()

                    if user:
                        u_id, u_nom, u_ape, u_user, u_email, u_pass, u_rol, u_est, u_cond_id = user
                        if u_est != "Activo":
                            st.error("⚠️ Tu cuenta se encuentra inactiva. Contacta al Administrador.")
                        elif verify_password(u_pass, password_input):
                            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            cursor.execute("UPDATE app_usuarios SET ultimo_acceso = ? WHERE id = ?", (now_str, u_id))
                            conn.commit()

                            st.session_state["authenticated"] = True
                            st.session_state["user_info"] = {
                                "id": u_id,
                                "nombre": f"{u_nom} {u_ape}",
                                "username": u_user,
                                "email": u_email,
                                "rol": u_rol,
                                "conductor_id": u_cond_id
                            }
                            conn.close()
                            st.success("✅ Acceso correcto.")
                            st.rerun()
                        else:
                            st.error("❌ Contraseña incorrecta.")
                            conn.close()
                    else:
                        st.error("❌ El usuario o correo no existe.")
                        conn.close()

        with tab_reset:
            st.info("Para restablecer tu contraseña, ingresa tu correo electrónico registrado para notificar al Administrador.")
            email_rec = st.text_input("Correo Registrado", key="email_rec")
            if st.button("Solicitar Restablecimiento", use_container_width=True):
                if email_rec:
                    st.success("✅ Si el correo existe en el sistema, se ha enviado la solicitud de restablecimiento al Administrador.")
                else:
                    st.warning("Por favor ingresa un correo válido.")
    st.stop()

# ---------------------------------------------------------
# CABECERA Y MENÚ DINÁMICO POR ROLES Y PERMISOS
# ---------------------------------------------------------
user_session = st.session_state["user_info"]
user_rol = user_session["rol"]

st.markdown(f"""
    <div class="app-header">
        <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
                <h1>🩵 Rutas Senior</h1>
                <p>Plataforma de Gestión de Transporte y Movilidad de Personas Mayores</p>
            </div>
            <div style="text-align: right; font-size: 13px;">
                👤 <b>{user_session['nombre']}</b> ({user_rol})<br>
                <small>{user_session['email']}</small>
            </div>
        </div>
    </div>
""", unsafe_allow_html=True)

MAPPING_MODULOS = {
    "📊 Dashboard / Resumen General": "Dashboard",
    "📅 Hojas de Ruta por Día de Semana": "HojasRuta",
    "📆 Calendario Mensual y Programación": "Calendario",
    "👤 Módulo 1: Usuarios (Alta/Baja/Edición)": "Pacientes",
    "🚘 Módulo 2: Conductores": "Conductores",
    "📋 Módulo 3: Programación de Servicios": "Servicios",
    "📱 Módulo 4: Vista Móvil Conductor (Hoja de Ruta)": "VistaMovil",
    "⚙️ Administración de Usuarios y Sistema": "GestionUsuarios"
}

opciones_menu_disponibles = []
for label_menu, mod_clave in MAPPING_MODULOS.items():
    perm = obtener_permiso(user_rol, mod_clave)
    if perm["ver"]:
        opciones_menu_disponibles.append(label_menu)

if not opciones_menu_disponibles:
    st.error("⚠️ No tienes permisos asignados para ver ningún módulo. Contacta al Administrador.")
    if st.sidebar.button("🚪 Cerrar Sesión"):
        st.session_state["authenticated"] = False
        st.session_state["user_info"] = None
        st.rerun()
    st.stop()

st.sidebar.markdown(f"### 👤 {user_session['username']}")
st.sidebar.caption(f"Rol: **{user_rol}**")

opcion = st.sidebar.selectbox("📌 MENÚ DE NAVEGACIÓN", opciones_menu_disponibles)

if st.sidebar.button("🚪 Cerrar Sesión", use_container_width=True):
    st.session_state["authenticated"] = False
    st.session_state["user_info"] = None
    st.rerun()

OPCIONES_MOVILIDAD = ["Autónomo", "Silla de ruedas", "Asistencia"]
DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
PARENTESCOS = ["Hijo/a", "Padre", "Madre", "Tío/a", "Hermano/a", "Otros"]

# ---------------------------------------------------------
# DASHBOARD GENERAL CON MAPA
# ---------------------------------------------------------
if opcion == "📊 Dashboard / Resumen General":
    p = obtener_permiso(user_rol, "Dashboard")
    if not p["ver"]:
        st.error("⛔ No tienes permisos para acceder a este módulo.")
        st.stop()

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

    m1, m2, m3, m4 = st.columns(4)
    m1.markdown(f'<div class="kpi-card"><div class="kpi-card-title">Residentes Activos</div><div class="kpi-card-value">{total_users}</div></div>', unsafe_allow_html=True)
    m2.markdown(f'<div class="kpi-card"><div class="kpi-card-title">Conductores Disponibles</div><div class="kpi-card-value">{total_cond}</div></div>', unsafe_allow_html=True)
    m3.markdown(f'<div class="kpi-card"><div class="kpi-card-title">Servicios Programados</div><div class="kpi-card-value">{total_serv}</div></div>', unsafe_allow_html=True)
    m4.markdown(f'<div class="kpi-card"><div class="kpi-card-title">Requieren Silla ♿</div><div class="kpi-card-value">{sillas}</div></div>', unsafe_allow_html=True)

    st.markdown("---")

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

    with col_der:
        st.subheader("🗺️ Monitoreo de Ambulancias en Ruta")

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
            st.dataframe(df_gps_filtered[['Conductor', 'Residente', 'Tipo', 'Estado', 'Incidencia']], use_container_width=True)
        else:
            st.info("No hay vehículos en trayecto activo actualmente para la selección actual.")

# ---------------------------------------------------------
# HOJAS DE RUTA POR DÍA DE LA SEMANA
# ---------------------------------------------------------
elif opcion == "📅 Hojas de Ruta por Día de Semana":
    p = obtener_permiso(user_rol, "HojasRuta")
    if not p["ver"]:
        st.error("⛔ No tienes permisos para acceder a este módulo.")
        st.stop()

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
    p = obtener_permiso(user_rol, "Calendario")
    if not p["ver"]:
        st.error("⛔ No tienes permisos para acceder a este módulo.")
        st.stop()

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

        if p["crear"]:
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
# MÓDULO 1: USUARIOS (PACIENTES)
# ---------------------------------------------------------
elif opcion == "👤 Módulo 1: Usuarios (Alta/Baja/Edición)":
    p = obtener_permiso(user_rol, "Pacientes")
    if not p["ver"]:
        st.error("⛔ No tienes permisos para acceder a este módulo.")
        st.stop()

    st.header("👤 Gestión de Residentes y Usuarios")
    
    tabs_pacientes = []
    if p["crear"]: tabs_pacientes.append("➕ Registrar Usuario")
    if p["editar"]: tabs_pacientes.append("✏️ Editar / Suspender Usuario")
    tabs_pacientes.append("🗑️ Listado de Pacientes")

    tabs_obj = st.tabs(tabs_pacientes)
    tab_idx = 0

    if p["crear"]:
        with tabs_obj[tab_idx]:
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
        tab_idx += 1

    if p["editar"]:
        with tabs_obj[tab_idx]:
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
        tab_idx += 1

    with tabs_obj[tab_idx]:
        conn = get_connection()
        df_u = pd.read_sql_query("SELECT * FROM usuarios", conn)
        conn.close()
        st.dataframe(df_u, use_container_width=True)

# ---------------------------------------------------------
# MÓDULO 2: CONDUCTORES
# ---------------------------------------------------------
elif opcion == "🚘 Módulo 2: Conductores":
    p = obtener_permiso(user_rol, "Conductores")
    if not p["ver"]:
        st.error("⛔ No tienes permisos para acceder a este módulo.")
        st.stop()

    st.header("🚘 Gestión de Conductores")

    tabs_cond = []
    if p["crear"]: tabs_cond.append("➕ Registrar Conductor")
    if p["editar"]: tabs_cond.append("✏️ Editar Conductor")
    if p["eliminar"]: tabs_cond.append("🗑️ Eliminar Conductor")

    if tabs_cond:
        tabs_c_obj = st.tabs(tabs_cond)
        t_c_idx = 0

        if p["crear"]:
            with tabs_c_obj[t_c_idx]:
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
            t_c_idx += 1

        if p["editar"]:
            with tabs_c_obj[t_c_idx]:
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
            t_c_idx += 1

        if p["eliminar"]:
            with tabs_c_obj[t_c_idx]:
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
    p = obtener_permiso(user_rol, "Servicios")
    if not p["ver"]:
        st.error("⛔ No tienes permisos para acceder a este módulo.")
        st.stop()

    st.header("📋 Programación General y Asignación de Trayectos")
    conn = get_connection()
    df_activos = pd.read_sql_query("SELECT * FROM usuarios WHERE estado = 'Activo'", conn)
    df_conductores = pd.read_sql_query("SELECT * FROM conductores WHERE estado = 'Activo'", conn)
    conn.close()

    col1, col2 = st.columns([1, 1.2])

    with col1:
        if p["crear"]:
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
            
            subtabs_serv = []
            if p["editar"]: subtabs_serv.append("✏️ Editar Servicio")
            if p["eliminar"]: subtabs_serv.append("❌ Cancelar Servicio")

            if subtabs_serv:
                tabs_s_obj = st.tabs(subtabs_serv)
                s_idx = 0

                if p["editar"]:
                    with tabs_s_obj[s_idx]:
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
                    s_idx += 1

                if p["eliminar"]:
                    with tabs_s_obj[s_idx]:
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
    p = obtener_permiso(user_rol, "VistaMovil")
    if not p["ver"]:
        st.error("⛔ No tienes permisos para acceder a este módulo.")
        st.stop()

    st.header("📱 Panel Móvil del Conductor")
    
    conn = get_connection()
    
    if user_rol == "Conductor":
        c_sel = user_session["conductor_id"]
        if not c_sel:
            st.error("⚠️ Tu usuario de conductor no tiene ningún registro de Conductor asociado. Contacta al Administrador.")
            st.stop()
        df_cond = pd.read_sql_query("SELECT * FROM conductores WHERE id = ? AND estado = 'Activo'", conn, params=(c_sel,))
    else:
        df_cond = pd.read_sql_query("SELECT * FROM conductores WHERE estado = 'Activo'", conn)

    conn.close()

    if not df_cond.empty:
        if user_rol == "Conductor":
            st.info(f"🚗 Conductor identificado: **{df_cond.iloc[0]['nombre']}**")
        else:
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

        st.subheader("📍 Capturar mi GPS actual")
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
                estado_actual_val = fila['estado_actual'] if fila['estado_actual'] in opciones_estados else "Pendiente"
                
                # Badge de Movilidad
                badge_movilidad = (
                    '<span class="badge-wheelchair">♿ Silla</span>' if mov == 'Silla de ruedas' 
                    else '<span class="badge-asistencia">🤝 Asistencia</span>' if mov == 'Asistencia' 
                    else '<span class="badge-autonomo">🚶 Autónomo</span>'
                )

                # Badge de Estado con Color
                mapa_colores_estado = {
                    "Pendiente": '<span class="status-pendiente">⚪ Pendiente</span>',
                    "En Camino": '<span class="status-encamino">🔵 En Camino</span>',
                    "Paciente Recogido": '<span class="status-recogido">🟡 Paciente Recogido</span>',
                    "Entregado en Destino": '<span class="status-entregado">🟢 Entregado en Destino</span>',
                    "Incidencia": '<span class="status-incidencia">🔴 Incidencia</span>'
                }
                badge_estado = mapa_colores_estado.get(estado_actual_val, '<span class="status-pendiente">⚪ Pendiente</span>')

                # Tarjeta limpia sin mapa interno
                st.markdown(f"""
                <div class="card-route">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <strong>⏰ {fila['Hora']}</strong>
                        <small><b>{fila['Tipo']}</b></small>
                    </div>
                    <div style="margin-top: 6px; display: flex; justify-content: space-between; align-items: center;">
                        <span><strong>👤 {fila['Paciente']}</strong> {badge_movilidad}</span>
                    </div>
                    <div style="margin-top: 6px;">
                        <b>Estado:</b> {badge_estado}
                    </div>
                    <div style="font-size: 13px; margin-top: 8px;">📍 <b>Dirección:</b> {fila['Dirección']}</div>
                    <div style="font-size: 13px; color: #333; margin-top: 4px;">📞 <b>Contacto:</b> {fila['Contacto']} - {fila['Teléfono']}</div>
                </div>
                """, unsafe_allow_html=True)

                # Formatear teléfono para el link de WhatsApp (remueve caracteres no numéricos)
                tel_raw = str(fila['Teléfono'] or '')
                tel_clean = "".join([char for char in tel_raw if char.isdigit()])

                col_btn_maps, col_btn_wsp = st.columns(2)

                # Link a Google Maps
                direccion_encoded = urllib.parse.quote(fila['Dirección'])
                col_btn_maps.markdown(f"""
                    <a href="https://www.google.com/maps/search/?api=1&query={direccion_encoded}" target="_blank" style="text-decoration:none;">
                        <button style="width:100%; background-color:#4285F4; color:white; border:none; padding:8px 10px; border-radius:6px; font-weight:bold; cursor:pointer;">
                            🗺️ Abrir GPS
                        </button>
                    </a>
                """, unsafe_allow_html=True)

                # Link directo a WhatsApp
                if tel_clean:
                    col_btn_wsp.markdown(f"""
                        <a href="https://wa.me/{tel_clean}" target="_blank" style="text-decoration:none;">
                            <button style="width:100%; background-color:#25D366; color:white; border:none; padding:8px 10px; border-radius:6px; font-weight:bold; cursor:pointer;">
                                💬 WhatsApp
                            </button>
                        </a>
                    """, unsafe_allow_html=True)
                else:
                    col_btn_wsp.button("💬 Sin Teléfono", disabled=True, key=f"btn_wsp_disabled_{s_id}")

                idx_est = opciones_estados.index(estado_actual_val)

                if p["editar"]:
                    with st.expander("📍 Actualizar Estado del Trayecto", expanded=False):
                        nuevo_estado = st.selectbox("Nuevo Estado del Trayecto:", opciones_estados, index=idx_est, key=f"est_{s_id}")

                        if st.button("💾 Guardar Cambios", key=f"btn_save_{s_id}"):
                            lat_amb = fila['latitud'] if pd.notna(fila['latitud']) else 43.538100
                            lon_amb = fila['longitud'] if pd.notna(fila['longitud']) else -5.663500

                            final_lat = gps_lat if gps_lat is not None else float(lat_amb)
                            final_lon = gps_lon if gps_lon is not None else float(lon_amb)

                            with get_connection() as conn:
                                conn.execute("""
                                    UPDATE servicios 
                                    SET estado_actual = ?, latitud = ?, longitud = ? 
                                    WHERE id = ?
                                """, (nuevo_estado, final_lat, final_lon, s_id))
                            st.toast("✅ Estado y ubicación guardados")
                            st.rerun()

                st.markdown("<hr style='margin:15px 0;'>", unsafe_allow_html=True)

        st.markdown('</div>', unsafe_allow_html=True)
    else:
        st.info("No hay conductores activos para mostrar.")

# ---------------------------------------------------------
# MÓDULO NUEVO: ADMINISTRACIÓN DE USUARIOS, ROLES Y PERMISOS
# ---------------------------------------------------------
elif opcion == "⚙️ Administración de Usuarios y Sistema":
    p = obtener_permiso(user_rol, "GestionUsuarios")
    if not p["ver"]:
        st.error("⛔ No tienes permisos para acceder a este módulo.")
        st.stop()

    st.header("⚙️ Administración de Usuarios del Sistema, Roles y Permisos")
    
    t_usr, t_roles, t_perm = st.tabs(["👤 Usuarios del Sistema", "🛡️ Gestión de Roles", "🔑 Configuración de Permisos"])

    with t_usr:
        st.subheader("Gestión de Usuarios de la Aplicación")
        
        with st.expander("➕ Crear Nuevo Usuario del Sistema", expanded=False):
            conn = get_connection()
            df_roles_db = pd.read_sql_query("SELECT DISTINCT rol FROM roles_permisos", conn)
            df_cond_db = pd.read_sql_query("SELECT id, nombre FROM conductores WHERE estado='Activo'", conn)
            conn.close()

            roles_disponibles = df_roles_db["rol"].tolist() if not df_roles_db.empty else ["Administrador", "Consultor", "Conductor"]

            with st.form("form_crear_app_usuario", clear_on_submit=True):
                c1, c2 = st.columns(2)
                with c1:
                    u_nom = st.text_input("Nombre*")
                    u_username = st.text_input("Nombre de Usuario (Username)*")
                    u_pass = st.text_input("Contraseña*", type="password")
                    u_rol = st.selectbox("Rol de Acceso*", roles_disponibles)
                with c2:
                    u_ape = st.text_input("Apellidos*")
                    u_email = st.text_input("Email*")
                    u_est = st.selectbox("Estado", ["Activo", "Inactivo"])
                    
                    cond_options = [("Ninguno", None)] + [(row["nombre"], row["id"]) for _, row in df_cond_db.iterrows()]
                    u_cond_assoc = st.selectbox("Asociar con Conductor Existente (Obligatorio si Rol=Conductor):", 
                                                options=cond_options, format_func=lambda x: x[0])

                if st.form_submit_button("Crear Usuario"):
                    if u_nom and u_ape and u_username and u_email and u_pass:
                        pass_hash = hash_password(u_pass)
                        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                        c_id_final = u_cond_assoc[1]

                        try:
                            with get_connection() as conn:
                                conn.execute("""
                                    INSERT INTO app_usuarios (nombre, apellidos, username, email, password, rol, estado, fecha_creacion, conductor_id)
                                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (u_nom, u_ape, u_username.strip(), u_email.strip(), pass_hash, u_rol, u_est, now_str, c_id_final))
                            st.toast("✅ Usuario del sistema creado exitosamente")
                            st.rerun()
                        except sqlite3.IntegrityError:
                            st.error("❌ El Username o Email ya se encuentra registrado.")
                    else:
                        st.error("Por favor completa los campos obligatorios (*).")

        conn = get_connection()
        df_app_u = pd.read_sql_query("""
            SELECT u.id, u.nombre, u.apellidos, u.username, u.email, u.rol, u.estado, 
                   u.ultimo_acceso, c.nombre as ConductorAsociado
            FROM app_usuarios u
            LEFT JOIN conductores c ON u.conductor_id = c.id
        """, conn)
        conn.close()

        st.dataframe(df_app_u, use_container_width=True)

        if not df_app_u.empty:
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                st.subheader("✏️ Modificar Usuario / Cambiar Contraseña")
                u_sel_id = st.selectbox("Seleccionar usuario a editar:", options=df_app_u["id"].tolist(), 
                                        format_func=lambda x: f"{df_app_u[df_app_u['id']==x]['username'].values[0]} ({df_app_u[df_app_u['id']==x]['nombre'].values[0]})")
                
                row_u = df_app_u[df_app_u["id"] == u_sel_id].iloc[0]

                with st.form("form_edit_app_u"):
                    e_rol = st.selectbox("Rol:", roles_disponibles, index=roles_disponibles.index(row_u["rol"]) if row_u["rol"] in roles_disponibles else 0)
                    e_est = st.selectbox("Estado:", ["Activo", "Inactivo"], index=0 if row_u["estado"] == "Activo" else 1)
                    e_new_pass = st.text_input("Nueva Contraseña (dejar en blanco para conservar la actual)", type="password")

                    if st.form_submit_button("Actualizar Usuario"):
                        with get_connection() as conn:
                            if e_new_pass.strip():
                                new_pass_hash = hash_password(e_new_pass.strip())
                                conn.execute("UPDATE app_usuarios SET rol = ?, estado = ?, password = ? WHERE id = ?", (e_rol, e_est, new_pass_hash, u_sel_id))
                            else:
                                conn.execute("UPDATE app_usuarios SET rol = ?, estado = ? WHERE id = ?", (e_rol, e_est, u_sel_id))
                        st.toast("✅ Usuario actualizado correctamente")
                        st.rerun()

            with col_u2:
                st.subheader("🗑️ Eliminar Usuario")
                u_del_id = st.selectbox("Seleccionar usuario a eliminar:", options=df_app_u["id"].tolist(), 
                                        format_func=lambda x: f"{df_app_u[df_app_u['id']==x]['username'].values[0]}", key="del_u_sel")
                if st.button("🗑️ Confirmar Eliminar Usuario", type="primary"):
                    if u_del_id == user_session["id"]:
                        st.error("❌ No puedes eliminar tu propio usuario en sesión.")
                    else:
                        with get_connection() as conn:
                            conn.execute("DELETE FROM app_usuarios WHERE id = ?", (u_del_id,))
                        st.toast("✅ Usuario eliminado")
                        st.rerun()

    with t_roles:
        st.subheader("🛡️ Gestión de Roles de Sistema")
        
        with st.form("form_crear_rol", clear_on_submit=True):
            nuevo_rol_nombre = st.text_input("Nombre del Nuevo Rol Personalizado")
            if st.form_submit_button("Añadir Rol"):
                if nuevo_rol_nombre.strip():
                    rol_clean = nuevo_rol_nombre.strip()
                    modulos_lista = ["Dashboard", "HojasRuta", "Calendario", "Pacientes", "Conductores", "Servicios", "VistaMovil", "GestionUsuarios"]
                    
                    with get_connection() as conn:
                        for mod in modulos_lista:
                            conn.execute("INSERT OR IGNORE INTO roles_permisos VALUES (?, ?, 0, 0, 0, 0)", (rol_clean, mod))
                    st.toast(f"✅ Rol '{rol_clean}' creado correctamente.")
                    st.rerun()

    with t_perm:
        st.subheader("🔑 Configuración Granular de Permisos por Rol")
        
        conn = get_connection()
        df_roles_list = pd.read_sql_query("SELECT DISTINCT rol FROM roles_permisos", conn)
        conn.close()

        if not df_roles_list.empty:
            rol_config_sel = st.selectbox("Selecciona Rol para configurar:", df_roles_list["rol"].tolist())

            conn = get_connection()
            df_perm_rol = pd.read_sql_query("SELECT modulo, p_ver, p_crear, p_editar, p_eliminar FROM roles_permisos WHERE rol = ?", conn, params=(rol_config_sel,))
            conn.close()

            st.markdown(f"**Matriz de Permisos para el Rol:** `{rol_config_sel}`")

            with st.form("form_guardar_permisos"):
                perm_updates = []
                for idx, row in df_perm_rol.iterrows():
                    mod = row["modulo"]
                    st.markdown(f"**Módulo: {mod}**")
                    c1, c2, c3, c4 = st.columns(4)
                    v = c1.checkbox("Ver", value=bool(row["p_ver"]), key=f"v_{mod}")
                    c = c2.checkbox("Crear", value=bool(row["p_crear"]), key=f"c_{mod}")
                    e = c3.checkbox("Editar", value=bool(row["p_editar"]), key=f"e_{mod}")
                    d = c4.checkbox("Eliminar", value=bool(row["p_eliminar"]), key=f"d_{mod}")
                    perm_updates.append((int(v), int(c), int(e), int(d), rol_config_sel, mod))
                    st.markdown("---")

                if st.form_submit_button("💾 Guardar Permisos del Rol"):
                    with get_connection() as conn:
                        for item in perm_updates:
                            conn.execute("UPDATE roles_permisos SET p_ver=?, p_crear=?, p_editar=?, p_eliminar=? WHERE rol=? AND modulo=?", item)
                    st.toast("✅ Permisos actualizados correctamente")
                    st.rerun()

