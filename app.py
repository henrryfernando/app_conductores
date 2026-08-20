import sqlite3
from datetime import datetime, date
import calendar
import pandas as pd
import streamlit as st
import urllib.parse
import folium
from streamlit_folium import st_folium
from streamlit_js_eval import get_geolocation

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

        # Migraciones
        for col, dtype in [
            ("estado_actual", "TEXT DEFAULT 'Pendiente'"),
            ("incidencia", "TEXT DEFAULT ''"),
            ("latitud", "REAL DEFAULT 43.538100"),
            ("longitud", "REAL DEFAULT -5.663500"),
            ("fecha_especifica", "TEXT DEFAULT NULL")
        ]:
            try:
                cursor.execute(f"ALTER TABLE servicios ADD COLUMN {col} {dtype};")
            except sqlite3.OperationalError:
                pass

        conn.commit()

init_db()

# ---------------------------------------------------------
# CONFIGURACIÓN DE PÁGINA Y ESTILOS
# ---------------------------------------------------------
st.set_page_config(
    page_title="Gestión de Transporte Geriátrico",
    page_icon="🚌",
    layout="wide",
)

st.markdown("""
    <style>
    .card-route {
        background-color: #f8f9fa;
        border-left: 5px solid #007bff;
        padding: 15px;
        border-radius: 8px;
        margin-bottom: 10px;
        color: #212529;
    }
    .badge-wheelchair { background-color: #ff4b4b; color: white; padding: 3px 8px; border-radius: 12px; font-size: 12px; }
    .badge-autonomo { background-color: #28a745; color: white; padding: 3px 8px; border-radius: 12px; font-size: 12px; }
    .badge-asistencia { background-color: #ffc107; color: black; padding: 3px 8px; border-radius: 12px; font-size: 12px; }
    .mobile-container {
        max-width: 480px;
        margin: 0 auto;
        border: 10px solid #333;
        border-radius: 20px;
        padding: 15px;
        background-color: #ffffff;
    }
    .cal-header { font-weight: bold; text-align: center; background-color: #007bff; color: white; padding: 5px; border-radius: 4px; }
    </style>
""", unsafe_allow_html=True)

st.title("🚌 Sistema de Gestión de Transporte Geriátrico")

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
    conn.close()

    col_m1, col_m2, col_m3, col_m4 = st.columns(4)
    col_m1.metric("Residentes Activos", total_users)
    col_m2.metric("Conductores Disponibles", total_cond)
    col_m3.metric("Servicios Programados", total_serv)
    col_m4.metric("Requieren Silla ♿", sillas)

    st.markdown("---")
    st.subheader("🗺️ Ubicación de Ambulancias / Vehículos en Ruta")

    if not df_gps.empty:
        lat_centro = df_gps['lat'].mean()
        lon_centro = df_gps['lon'].mean()

        m = folium.Map(location=[lat_centro, lon_centro], zoom_start=15)

        for _, row in df_gps.iterrows():
            popup_text = f"<b>Conductor:</b> {row['Conductor']}<br><b>Residente:</b> {row['Residente']}<br><b>Estado:</b> {row['Estado']}<br><b>Incidencia:</b> {row['Incidencia'] or 'Ninguna'}"
            folium.Marker(
                [row['lat'], row['lon']],
                popup=popup_text,
                tooltip=f"🚗 Conductor: {row['Conductor']}",
                icon=folium.Icon(color="red", icon="ambulance", prefix="fa")
            ).add_to(m)

        st_folium(m, width=1000, height=500)
        
        st.subheader("📋 Estado Detallado del Servicio")
        st.dataframe(df_gps[['Conductor', 'Residente', 'Tipo', 'Estado', 'Incidencia']], use_container_width=True)
    else:
        st.info("No hay vehículos en trayecto activo actualmente ('En Camino' o 'Recogido'). Pasa al Módulo 4 y cambia el estado del servicio a 'En Camino' para visualizar el vehículo en el mapa.")

# ---------------------------------------------------------
# HOJAS DE RUTA POR DÍA DE LA SEMANA
# ---------------------------------------------------------
elif opcion == "📅 Hojas de Ruta por Día de Semana":
    st.header("📅 Hojas de Ruta Organizadas por Día de la Semana")
    st.caption("Consulta el cronograma global para todos los conductores y pacientes según el día seleccionado.")

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
        
        # Agrupación por conductor
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

        # 1. Buscar primero trayectos asignados específicamente a esta fecha puntual
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

        # 2. Si no hay nada programado puntualmente para esa fecha, buscar la plantilla semanal habitual
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
            st.info(f"No hay trayectos guardados para el {fecha_act.strftime('%d/%m/%Y')}. Agrega uno nuevo a continuación:")

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
                    st.toast("✅ Trayecto guardado para esta fecha")
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
                    e_hora_s = st.time_input("Hora Programada", value=datetime.strptime(datos_serv["Hora"], "%H:%M").time())
                    e_dias_serv = st.multiselect("Días:", DIAS_SEMANA, default=[d for d in datos_serv["Días"].split(", ") if d in DIAS_SEMANA])
                    
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
# MÓDULO 4: VISTA MÓVIL DEL CONDUCTOR
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
            SELECT s.id as servicio_id, s.hora as Hora, s.tipo_servicio as Tipo, u.nombre as Usuario, 
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
        st.markdown("<h3 style='text-align: center;'>📋 Ruta de Hoy</h3>", unsafe_allow_html=True)
        st.markdown("<hr>", unsafe_allow_html=True)

        if not df_ruta.empty:
            for _, fila in df_ruta.iterrows():
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
                        <strong>👤 {fila['Usuario']}</strong> {badge_html}
                    </div>
                    <div style="font-size: 13px; margin-top: 4px;">📍 {fila['Dirección']}</div>
                    <div style="font-size: 12px; color: #555;">📞 {fila['Contacto']}: {fila['Teléfono']}</div>
                </div>
                """, unsafe_allow_html=True)

                # Navegación
                direccion_encoded = urllib.parse.quote(fila['Dirección'])
                st.markdown(f"[🗺️ Abrir Ruta en Google Maps](https://www.google.com/maps/search/?api=1&query={direccion_encoded})")

                # Estado del Servicio
                estado_act = fila['estado_actual'] or "Pendiente"
                st.caption(f"Estado Actual: **{estado_act}**")
                
                c_b1, c_b2, c_b3 = st.columns(3)
                with c_b1:
                    if st.button("🚚 En camino", key=f"btn_cam_{s_id}"):
                        with get_connection() as conn:
                            conn.execute("UPDATE servicios SET estado_actual = 'En Camino' WHERE id = ?", (s_id,))
                        st.toast("✅ Guardado con éxito")
                        st.rerun()

                with c_b2:
                    if st.button("📍 Recogido", key=f"btn_rec_{s_id}"):
                        with get_connection() as conn:
                            conn.execute("UPDATE servicios SET estado_actual = 'Recogido' WHERE id = ?", (s_id,))
                        st.toast("✅ Guardado con éxito")
                        st.rerun()

                with c_b3:
                    if st.button("🏁 Entregado", key=f"btn_ent_{s_id}"):
                        with get_connection() as conn:
                            conn.execute("UPDATE servicios SET estado_actual = 'Entregado en Destino' WHERE id = ?", (s_id,))
                        st.toast("✅ Guardado con éxito")
                        st.rerun()

                # Captura GPS
                with st.expander("📡 Transmitir Ubicación GPS (Móvil / Automático)"):
                    loc = get_geolocation(component_key=f"geo_{s_id}")
                    if loc and 'coords' in loc:
                        lat_auto = loc['coords']['latitude']
                        lon_auto = loc['coords']['longitude']
                        st.success(f"GPS capturado: Lat {lat_auto:.4f}, Lon {lon_auto:.4f}")
                        
                        if st.button("Enviar Mi Ubicación Actual al Mapa", key=f"btn_gps_auto_{s_id}"):
                            with get_connection() as conn:
                                conn.execute("UPDATE servicios SET latitud = ?, longitud = ? WHERE id = ?", (lat_auto, lon_auto, s_id))
                            st.toast("✅ Guardado con éxito")
                            st.rerun()
                    else:
                        st.info("Presiona 'Permitir' cuando el navegador pida acceso a la ubicación GPS.")

                # Entrada Manual
                with st.expander("⚙️ Ajustar Coordenadas Manualmente (Pruebas)"):
                    c_lat, c_lon = st.columns(2)
                    new_lat = c_lat.number_input("Latitud", value=float(fila['latitud'] or 43.538100), format="%.6f", key=f"lat_{s_id}")
                    new_lon = c_lon.number_input("Longitud", value=float(fila['longitud'] or -5.663500), format="%.6f", key=f"lon_{s_id}")
                    if st.button("Guardar Coordenadas Manuales", key=f"btn_gps_man_{s_id}"):
                        with get_connection() as conn:
                            conn.execute("UPDATE servicios SET latitud = ?, longitud = ? WHERE id = ?", (new_lat, new_lon, s_id))
                        st.toast("✅ Guardado con éxito")
                        st.rerun()

                # Incidencias
                with st.expander("⚠️ Registrar Inconveniente / Observación"):
                    inc_texto = st.text_area("Mensaje:", value=fila['incidencia'] or "", key=f"txt_{s_id}")
                    if st.button("Guardar Nota", key=f"btn_inc_{s_id}"):
                        with get_connection() as conn:
                            conn.execute("UPDATE servicios SET incidencia = ? WHERE id = ?", (inc_texto, s_id))
                        st.toast("✅ Guardado con éxito")
                        st.rerun()

                st.markdown("---")
        else:
            st.info("Sin servicios programados hoy para este conductor.")

        st.markdown('</div>', unsafe_allow_html=True)







