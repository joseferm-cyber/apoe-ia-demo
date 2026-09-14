"""
core/db_protected.py
=====================
Conector EXCLUSIVO al almacén protegido (Bloque C.2 / db/ddl_protected.sql).

REGLA DE ARQUITECTURA VERIFICABLE: este archivo NO importa, referencia,
ni puede llegar a importar transitivamente core/ai_client.py. Se deja
como comentario explícito para que un análisis estático de imports
(ej. `grep -R "ai_client" core/db_protected.py`) devuelva vacío, lo cual
es uno de los criterios de aceptación del sistema.

Usa un archivo SQLite DISTINTO al de investigación (o, en producción,
una instancia/host distinto con credenciales propias) para materializar
la separación física.
"""

from __future__ import annotations
import os
import sqlite3
from contextlib import contextmanager
from datetime import date

# OJO: ruta y variable de entorno completamente independientes de
# APOE_DB_RESEARCH_PATH (ver core/db_research.py).
RUTA_DB_PROTECTED = os.environ.get("APOE_DB_PROTECTED_PATH", "apoe_protegido.db")


@contextmanager
def conexion():
    conn = sqlite3.connect(RUTA_DB_PROTECTED)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def inicializar_esquema(ruta_ddl_sqlite_compatible: str):
    with open(ruta_ddl_sqlite_compatible, "r", encoding="utf-8") as f:
        script = f.read()
    with conexion() as conn:
        conn.executescript(script)


def registrar_participante(codigo_seudonimo: str, nombre_completo: str, documento_identidad: str,
                            correo_institucional: str | None, telefono: str | None,
                            mayor_de_edad: bool, responsable_asignacion: str,
                            nombre_representante_legal: str | None = None) -> None:
    with conexion() as conn:
        conn.execute(
            """INSERT INTO tabla_maestra_codigos
               (codigo_seudonimo, nombre_completo, documento_identidad, correo_institucional,
                telefono, mayor_de_edad, nombre_representante_legal, responsable_asignacion)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (codigo_seudonimo, nombre_completo, documento_identidad, correo_institucional,
             telefono, int(mayor_de_edad), nombre_representante_legal, responsable_asignacion),
        )


def registrar_consentimiento(codigo_seudonimo: str, version_formato: str, fecha_firma: date,
                              acepta_participacion: bool, acepta_procesamiento_ia: bool,
                              documento_firmado_ruta: str) -> None:
    with conexion() as conn:
        conn.execute(
            """INSERT INTO consentimiento
               (codigo_seudonimo, version_formato_consentimiento, fecha_firma,
                acepta_participacion, acepta_procesamiento_ia, documento_firmado_ruta)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (codigo_seudonimo, version_formato, fecha_firma.isoformat(),
             int(acepta_participacion), int(acepta_procesamiento_ia), documento_firmado_ruta),
        )


def registrar_retiro(codigo_seudonimo: str, fecha_retiro: date, motivo: str) -> None:
    with conexion() as conn:
        conn.execute(
            """UPDATE consentimiento SET retirado = 1, fecha_retiro = ?, motivo_retiro = ?
               WHERE codigo_seudonimo = ?""",
            (fecha_retiro.isoformat(), motivo, codigo_seudonimo),
        )


def obtener_opt_out_ia(codigo_seudonimo: str) -> bool:
    """
    Única función que "cruza información" desde este almacén hacia el
    flujo operativo, y SOLO devuelve un booleano (nunca identidad). El
    valor resultante se refleja luego en
    investigacion.participantes_seudonimos.opt_out_ia mediante un job
    administrativo manual/periódico, nunca en tiempo real desde el
    pipeline de IA.
    """
    with conexion() as conn:
        fila = conn.execute(
            "SELECT acepta_procesamiento_ia FROM consentimiento WHERE codigo_seudonimo = ? "
            "ORDER BY fecha_firma DESC LIMIT 1",
            (codigo_seudonimo,),
        ).fetchone()
    if fila is None:
        return True  # sin consentimiento explícito de IA => tratar como opt-out por defecto
    return not bool(fila["acepta_procesamiento_ia"])


def reidentificar(codigo_seudonimo: str, usuario_solicitante: str, motivo: str) -> dict | None:
    """
    Única vía de reidentificación autorizada, reservada al rol
    'investigador_principal' (verificar ese rol en la capa de
    aplicación/autenticación antes de invocar esta función; este módulo
    no valida sesión web, solo datos).
    """
    with conexion() as conn:
        rol = conn.execute(
            "SELECT rol, acceso_reidentificacion FROM usuario_rol WHERE usuario = ?",
            (usuario_solicitante,),
        ).fetchone()
        if rol is None or not rol["acceso_reidentificacion"]:
            raise PermissionError(f"Usuario '{usuario_solicitante}' no tiene permiso de reidentificación.")

        fila = conn.execute(
            "SELECT * FROM tabla_maestra_codigos WHERE codigo_seudonimo = ?",
            (codigo_seudonimo,),
        ).fetchone()
    return dict(fila) if fila else None
