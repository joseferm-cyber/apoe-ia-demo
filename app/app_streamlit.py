"""
app/app_streamlit.py
=====================
App orquestadora del sistema APOE-IA. Roles: investigador_principal,
director_revisor (ver protegido.usuario_rol). Esta app SOLO habla con
core/db_research.py para el flujo operativo; el acceso al almacén
protegido queda restringido a las vistas de gestión de participantes
(fuera del pipeline de IA).

Ejecutar con: streamlit run app/app_streamlit.py
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
from core import db_research, pipeline
from core.pipeline import ContextoCiclo

st.set_page_config(page_title="APOE-IA · Seguimiento formativo de la derivada", layout="wide")


def cargar_contrato(nombre_archivo: str) -> dict:
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "prompts", nombre_archivo)
    with open(ruta, "r", encoding="utf-8") as f:
        return json.load(f)


PROMPT1 = cargar_contrato("prompt1_analisis_individual_v1.json")
PROMPT2 = cargar_contrato("prompt2_retroalimentacion_v1.json")
PROMPT3 = cargar_contrato("prompt3_agregacion_grupal_v1.json")

st.sidebar.title("APOE-IA")
st.sidebar.caption("Sistema de seguimiento formativo — no es plataforma de calificación.")
rol_actual = st.sidebar.selectbox("Rol de sesión", ["investigador_principal", "director_revisor"])
vista = st.sidebar.radio(
    "Vista",
    [
        "1. Captura de respuesta",
        "2. Cola de revisión humana (Prompt 1)",
        "3. Retroalimentación individual (Prompt 2)",
        "4. Agregación grupal (Prompt 3)",
        "5. Ajuste didáctico",
        "6. Panel de auditoría IA",
        "7. Bitácora de ciclo",
    ],
)

st.title("Sistema de información — Proyecto APOE-IA")
st.caption("La IA generativa solo interpreta y redacta. Nunca decide ni califica. "
           "Ninguna salida llega al estudiante sin revisión humana registrada.")

# ---------------------------------------------------------------------
# 1. CAPTURA
# ---------------------------------------------------------------------
if vista == "1. Captura de respuesta":
    st.header("Captura de respuesta del estudiante")
    with st.form("form_captura"):
        codigo = st.text_input("Código seudónimo (ej. MI1A-001)")
        ciclo_id = st.number_input("ID de ciclo", min_value=1, step=1)
        tarea_id = st.number_input("ID de tarea", min_value=1, step=1)
        contenido = st.text_area("Respuesta del estudiante (texto)")
        procedimiento = st.text_area("Procedimiento (opcional)")
        tiempo = st.number_input("Tiempo empleado (segundos)", min_value=0, step=1)
        intento = st.number_input("Número de intento", min_value=1, step=1)
        ayuda = st.text_input("Ayuda utilizada (opcional)")
        enviar = st.form_submit_button("Registrar respuesta")

    if enviar:
        if not codigo or not contenido:
            st.error("Código seudónimo y respuesta son obligatorios.")
        else:
            ctx = ContextoCiclo(
                ciclo_id=int(ciclo_id), tarea_id=int(tarea_id), matriz_version="v1",
                prompt1_contrato=PROMPT1, prompt2_contrato=PROMPT2, prompt3_contrato=PROMPT3,
            )
            try:
                resultado = pipeline.paso_1_captura(
                    codigo_seudonimo=codigo, ctx=ctx, contenido_original=contenido,
                    procedimiento=procedimiento or None, tiempo_segundos=int(tiempo) or None,
                    numero_intento=int(intento), ayuda_utilizada=ayuda or None,
                )
                if resultado["ok"]:
                    st.success(f"Respuesta registrada (respuesta_id={resultado['respuesta_id']}, "
                               f"canal={resultado['canal']}).")
                    if resultado["canal"] == "manual_opt_out":
                        st.info("Este participante tiene opt-out de IA: debe procesarse por revisión docente manual, "
                                "sin pasar por el pipeline de IA generativa.")
                else:
                    st.warning(f"No se pudo registrar automáticamente: {resultado['motivo']}. "
                               "Requiere revisión manual de posible PII antes de continuar.")
            except Exception as e:
                st.error(f"Error al registrar: {e}")

# ---------------------------------------------------------------------
# 2. COLA DE REVISIÓN HUMANA — PROMPT 1
# ---------------------------------------------------------------------
elif vista == "2. Cola de revisión humana (Prompt 1)":
    st.header("Cola de revisión humana — obligatoria antes de continuar")
    ciclo_id_filtro = st.number_input("Filtrar por ID de ciclo", min_value=1, step=1, key="ciclo_cola")
    if st.button("Cargar cola pendiente"):
        filas = db_research.obtener_cola_revision_pendiente(int(ciclo_id_filtro))
        if not filas:
            st.info("No hay elementos pendientes de revisión para este ciclo.")
        for fila in filas:
            with st.expander(f"Auditoría #{fila['id']} — respuesta_id={fila['respuesta_id']} — {fila['tipo_prompt']}"):
                st.json(json.loads(fila["salida_original_json"]))
                col1, col2, col3 = st.columns(3)
                observacion = st.text_input(f"Observación (auditoría #{fila['id']})", key=f"obs_{fila['id']}")
                if col1.button("Aceptar", key=f"acc_{fila['id']}"):
                    pipeline.paso_4_revision_humana(fila["id"], "aceptada", observacion, rol_actual)
                    st.success("Marcado como aceptado.")
                if col2.button("Corregir y aceptar", key=f"cor_{fila['id']}"):
                    pipeline.paso_4_revision_humana(fila["id"], "corregida", observacion, rol_actual)
                    st.success("Marcado como corregido.")
                if col3.button("Invalidar", key=f"inv_{fila['id']}"):
                    pipeline.paso_4_revision_humana(fila["id"], "invalidada", observacion, rol_actual)
                    st.warning("Marcado como inválido. No se generará retroalimentación desde esta salida.")

# ---------------------------------------------------------------------
# 3. RETROALIMENTACIÓN INDIVIDUAL — PROMPT 2
# ---------------------------------------------------------------------
elif vista == "3. Retroalimentación individual (Prompt 2)":
    st.header("Generar retroalimentación (bloqueado sin revisión previa aceptada)")
    auditoria_id_p1 = st.number_input("ID de auditoría de Prompt 1 ya revisada", min_value=1, step=1)
    nivel_final = st.selectbox("Nivel final revisado", ["A", "P", "O", "E", "SEC"])
    contexto_tarea = st.text_area("Contexto de la tarea")
    evidencia = st.text_area("Evidencia aceptada (una por línea)")
    tono = st.text_input("Tono deseado", value="cercano, orientado a siguiente paso, sin juicios de valor")

    if st.button("Generar retroalimentación (Prompt 2)"):
        ctx = ContextoCiclo(ciclo_id=1, tarea_id=1, matriz_version="v1",
                             prompt1_contrato=PROMPT1, prompt2_contrato=PROMPT2, prompt3_contrato=PROMPT3)
        try:
            resultado = pipeline.paso_5_retroalimentacion(
                auditoria_id_prompt1=int(auditoria_id_p1), ctx=ctx, nivel_final_revisado=nivel_final,
                indicadores_confirmados=[], evidencia_aceptada=evidencia.splitlines(),
                contexto_tarea=contexto_tarea, tono_deseado=tono, revisor_usuario=rol_actual,
            )
            st.json(resultado["salida_ia"])
            st.info(f"Registrado en auditoria_id_prompt2={resultado['auditoria_id_prompt2']}. "
                    "Debe revisarse este texto también antes de mostrarlo al estudiante (paso 6).")
        except PermissionError as e:
            st.error(str(e))
        except NotImplementedError as e:
            st.warning(f"Proveedor de IA aún no configurado: {e}")

# ---------------------------------------------------------------------
# 4. AGREGACIÓN GRUPAL — PROMPT 3
# ---------------------------------------------------------------------
elif vista == "4. Agregación grupal (Prompt 3)":
    st.header("Agregación grupal del ciclo")
    st.caption("Las frecuencias se calculan de forma determinista en core/agregacion.py; "
               "la IA solo redacta la síntesis sobre esos números ya fijados.")
    st.info("Ver core/agregacion.py para las funciones de cálculo (frecuencias por nivel, "
            "por indicador y movimiento entre ciclos) que alimentan este paso.")

# ---------------------------------------------------------------------
# 5. AJUSTE DIDÁCTICO
# ---------------------------------------------------------------------
elif vista == "5. Ajuste didáctico":
    st.header("Registrar ajuste didáctico para el siguiente ciclo")
    with st.form("form_ajuste"):
        ciclo_origen = st.number_input("Ciclo de origen", min_value=1, step=1)
        ciclo_destino = st.number_input("Ciclo de destino", min_value=1, step=1)
        componente = st.selectbox("Componente ajustado", ["enfasis", "representacion", "dificultad", "orientacion", "otro"])
        descripcion = st.text_area("Descripción del ajuste")
        justificacion = st.text_area("Justificación (basada en patrones grupales del ciclo anterior)")
        version_destino = st.text_input("Versión de tarea destino")
        modifica_protocolo = st.checkbox("¿Este ajuste modifica riesgos/datos/finalidad del protocolo aprobado?")
        enviar_ajuste = st.form_submit_button("Registrar ajuste")

    if enviar_ajuste:
        pipeline.paso_8_registrar_ajuste(
            ciclo_id_origen=int(ciclo_origen), ciclo_id_destino=int(ciclo_destino),
            componente_ajustado=componente, descripcion_ajuste=descripcion,
            justificacion=justificacion, tarea_version_destino=version_destino or None,
            modifica_protocolo=modifica_protocolo,
        )
        if modifica_protocolo:
            st.warning("Este ajuste está marcado como modificación de protocolo: el avance al "
                       "siguiente ciclo debe quedar bloqueado administrativamente hasta obtener "
                       "aprobación del comité de bioética.")
        else:
            st.success("Ajuste registrado.")

# ---------------------------------------------------------------------
# 6. PANEL DE AUDITORÍA IA
# ---------------------------------------------------------------------
elif vista == "6. Panel de auditoría IA":
    st.header("Auditoría de interacciones con IA")
    ciclo_id_aud = st.number_input("ID de ciclo", min_value=1, step=1, key="ciclo_aud")
    if st.button("Consultar auditoría del ciclo"):
        with db_research.conexion() as conn:
            filas = conn.execute(
                "SELECT * FROM auditoria_ia WHERE ciclo_id = ? ORDER BY fecha_hora DESC",
                (int(ciclo_id_aud),),
            ).fetchall()
        if not filas:
            st.info("Sin registros para este ciclo.")
        for f in filas:
            st.write(f"**#{f['id']}** · {f['tipo_prompt']} · prompt_version={f['prompt_version']} · "
                     f"modelo={f['modelo_proveedor']}/{f['modelo_version']} · "
                     f"estado={f['revision_humana_estado']} · sanitización_ok={bool(f['sanitizacion_verificada'])}")

    st.divider()
    st.subheader("Reconstrucción de trazabilidad completa por respuesta")
    respuesta_id_traza = st.number_input("respuesta_id", min_value=1, step=1)
    if st.button("Reconstruir cadena completa"):
        st.json(db_research.obtener_trazabilidad_completa(int(respuesta_id_traza)))

# ---------------------------------------------------------------------
# 7. BITÁCORA DE CICLO
# ---------------------------------------------------------------------
elif vista == "7. Bitácora de ciclo":
    st.header("Bitácora de implementación por ciclo")
    with st.form("form_bitacora"):
        ciclo_id_bit = st.number_input("ID de ciclo", min_value=1, step=1)
        incidencias = st.text_area("Incidencias técnicas")
        dudas = st.text_area("Dudas recurrentes")
        sintesis = st.text_area("Síntesis de evidencias")
        revision_gen = st.text_area("Revisión del componente generativo (aceptadas/corregidas/invalidadas, errores)")
        decision = st.text_area("Decisión entre ciclos")
        enviar_bit = st.form_submit_button("Guardar entrada de bitácora")

    if enviar_bit:
        with db_research.conexion() as conn:
            conn.execute(
                """INSERT INTO bitacora_ciclo
                   (ciclo_id, incidencias_tecnicas, dudas_recurrentes, sintesis_evidencias,
                    revision_componente_generativo, decision_entre_ciclos, autor_usuario)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (int(ciclo_id_bit), incidencias, dudas, sintesis, revision_gen, decision, rol_actual),
            )
        st.success("Entrada de bitácora guardada.")
