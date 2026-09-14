"""
core/db_research.py
====================
Conector EXCLUSIVO a la base de investigación (Bloque C.1 / db/ddl_research.sql).
Este módulo puede ser importado por core/pipeline.py y por core/ai_client.py
de forma indirecta (a través del pipeline), porque solo contiene datos
seudonimizados.

Usa SQLite por defecto para desarrollo local; para producción, apuntar
DATABASE_URL_RESEARCH a una instancia PostgreSQL separada de la de
core/db_protected.py (credenciales y, si es posible, host distintos).
"""

from __future__ import annotations
import os
import sqlite3
import json
from contextlib import contextmanager

RUTA_DB_RESEARCH = os.environ.get("APOE_DB_RESEARCH_PATH", "apoe_investigacion.db")


@contextmanager
def conexion():
    conn = sqlite3.connect(RUTA_DB_RESEARCH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def inicializar_esquema(ruta_ddl_sqlite_compatible: str):
    """
    Ejecuta un DDL adaptado a SQLite (sin SERIAL/JSONB/GENERATED ALWAYS;
    ver db/ddl_research.sql para la versión de referencia PostgreSQL y
    adaptar tipos: SERIAL -> INTEGER PRIMARY KEY AUTOINCREMENT, etc.)
    """
    with open(ruta_ddl_sqlite_compatible, "r", encoding="utf-8") as f:
        script = f.read()
    with conexion() as conn:
        conn.executescript(script)


def insertar_respuesta_cruda(codigo_seudonimo: str, ciclo_id: int, tarea_id: int,
                              contenido_original_sanitizado: str, procedimiento: str | None,
                              tiempo_segundos: int | None, numero_intento: int,
                              ayuda_utilizada: str | None, canal_procesamiento: str) -> int:
    """
    IMPORTANTE: contenido_original_sanitizado debe llegar YA pasado por
    core.sanitizacion antes de esta llamada. Este módulo no vuelve a
    sanitizar: es responsabilidad del pipeline garantizarlo antes de
    persistir y antes de enviar a IA.
    """
    with conexion() as conn:
        cur = conn.execute(
            """INSERT INTO respuesta_cruda
               (codigo_seudonimo, ciclo_id, tarea_id, contenido_original, procedimiento,
                tiempo_segundos, numero_intento, ayuda_utilizada, canal_procesamiento)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (codigo_seudonimo, ciclo_id, tarea_id, contenido_original_sanitizado, procedimiento,
             tiempo_segundos, numero_intento, ayuda_utilizada, canal_procesamiento),
        )
        return cur.lastrowid


def registrar_auditoria_ia(respuesta_id: int | None, ciclo_id: int, tipo_prompt: str,
                            prompt_version: str, modelo_proveedor: str, modelo_version: str,
                            entrada_enviada: dict, salida_original: dict,
                            sanitizacion_verificada: bool) -> int:
    """
    Se inserta SIEMPRE con revision_humana_estado='pendiente'. Ninguna
    fila se crea ya como 'aceptada': eso solo lo puede hacer
    marcar_revision_humana() a través de una acción explícita del revisor.
    """
    if not sanitizacion_verificada:
        raise ValueError(
            "No se puede registrar auditoria_ia con sanitizacion_verificada=False. "
            "El gate de core.sanitizacion debe ejecutarse antes de llamar a esta función."
        )
    with conexion() as conn:
        cur = conn.execute(
            """INSERT INTO auditoria_ia
               (respuesta_id, ciclo_id, tipo_prompt, prompt_version, modelo_proveedor, modelo_version,
                entrada_enviada_json, salida_original_json, revision_humana_estado, sanitizacion_verificada)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pendiente', ?)""",
            (respuesta_id, ciclo_id, tipo_prompt, prompt_version, modelo_proveedor, modelo_version,
             json.dumps(entrada_enviada, ensure_ascii=False), json.dumps(salida_original, ensure_ascii=False),
             1 if sanitizacion_verificada else 0),
        )
        return cur.lastrowid


def marcar_revision_humana(auditoria_id: int, estado: str, observacion: str | None,
                            revisor_usuario: str, texto_mostrado_final: str | None = None):
    if estado not in ("aceptada", "corregida", "invalidada"):
        raise ValueError("estado inválido para revisión humana")
    with conexion() as conn:
        conn.execute(
            """UPDATE auditoria_ia
               SET revision_humana_estado = ?, revision_humana_observacion = ?,
                   revisor_usuario = ?, texto_mostrado_final = ?
               WHERE id = ?""",
            (estado, observacion, revisor_usuario, texto_mostrado_final, auditoria_id),
        )


def obtener_cola_revision_pendiente(ciclo_id: int) -> list[sqlite3.Row]:
    with conexion() as conn:
        cur = conn.execute(
            """SELECT * FROM auditoria_ia
               WHERE ciclo_id = ? AND revision_humana_estado = 'pendiente'
               ORDER BY fecha_hora ASC""",
            (ciclo_id,),
        )
        return cur.fetchall()


def obtener_trazabilidad_completa(respuesta_id: int) -> dict:
    """
    Reconstruye la cadena completa exigida en criterios de aceptación:
    respuesta cruda -> indicadores -> nivel sugerido -> revisión humana
    -> texto mostrado -> (agregación/ajuste se consultan aparte por ciclo_id).
    """
    with conexion() as conn:
        respuesta = conn.execute("SELECT * FROM respuesta_cruda WHERE respuesta_id = ?", (respuesta_id,)).fetchone()
        indicadores = conn.execute("SELECT * FROM indicador_identificado WHERE respuesta_id = ?", (respuesta_id,)).fetchall()
        nivel = conn.execute("SELECT * FROM nivel_derivado WHERE respuesta_id = ?", (respuesta_id,)).fetchone()
        auditoria = conn.execute("SELECT * FROM auditoria_ia WHERE respuesta_id = ?", (respuesta_id,)).fetchall()

    return {
        "respuesta_cruda": dict(respuesta) if respuesta else None,
        "indicadores_identificados": [dict(r) for r in indicadores],
        "nivel_derivado": dict(nivel) if nivel else None,
        "auditoria_ia": [dict(r) for r in auditoria],
    }
