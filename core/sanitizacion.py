"""
core/sanitizacion.py
=====================
Gate programático de minimización/anonimización de datos.

Regla del sistema (no negociable): NINGUNA llamada al modelo generativo
puede ejecutarse si esta verificación no se completó con éxito. No basta
con instruir al prompt para que "ignore" PII: aquí se valida el texto
real que va a salir hacia el proveedor de IA.

Este módulo NO decide si algo es correcto pedagógicamente; solo decide
si el texto es seguro de enviar a un tercero externo (el proveedor de IA).
"""

from __future__ import annotations
import re
import unicodedata
from dataclasses import dataclass, field


# ---------------------------------------------------------------------
# Patrones de PII a bloquear/enmascarar. Ajustar y ampliar según
# contexto institucional real (formatos de documento en Colombia, etc.)
# ---------------------------------------------------------------------
PATRON_CORREO = re.compile(r"[\w\.\-+]+@[\w\-]+\.[\w\.\-]+")
PATRON_TELEFONO = re.compile(r"\b(\+?57)?[\s\-]?(3\d{2}|60[1-8])[\s\-]?\d{3}[\s\-]?\d{4}\b")
PATRON_DOCUMENTO = re.compile(r"\b\d{6,12}\b")  # cédulas/documentos: 6-12 dígitos consecutivos
PATRON_CODIGO_INSTITUCIONAL = re.compile(r"\b[A-Z]{1,4}-?\d{4,10}\b")  # ej. carnés institucionales

# Lista de nombres/apellidos NO se puede resolver con regex de forma
# confiable. Se exige una lista de nombres conocidos del curso (cargada
# desde el almacén protegido, NUNCA embebida en código fuente) para
# hacer reemplazo exacto, más una heurística de mayúsculas consecutivas
# como señal de alerta para revisión manual adicional.
PATRON_NOMBRE_PROPIO_HEURISTICO = re.compile(r"\b([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\s){1,3}[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+\b")


@dataclass
class ResultadoSanitizacion:
    texto_sanitizado: str
    ok_para_enviar_ia: bool
    hallazgos: list[str] = field(default_factory=list)
    requiere_revision_manual: bool = False


def _normalizar(texto: str) -> str:
    return unicodedata.normalize("NFC", texto)


def sanitizar_texto(texto: str, nombres_conocidos_curso: list[str] | None = None) -> ResultadoSanitizacion:
    """
    Aplica reemplazo determinista de patrones de PII conocidos.

    nombres_conocidos_curso: lista de nombres/apellidos reales del curso,
    obtenida SOLO en tiempo de ejecución desde el almacén protegido (nunca
    persistida en este módulo ni en el código fuente). Se usa para
    enmascarado exacto adicional al de los patrones regex.
    """
    if texto is None:
        texto = ""

    texto = _normalizar(texto)
    hallazgos: list[str] = []

    if PATRON_CORREO.search(texto):
        hallazgos.append("correo_electronico")
        texto = PATRON_CORREO.sub("[CORREO_REDACTADO]", texto)

    if PATRON_TELEFONO.search(texto):
        hallazgos.append("telefono")
        texto = PATRON_TELEFONO.sub("[TELEFONO_REDACTADO]", texto)

    if PATRON_DOCUMENTO.search(texto):
        hallazgos.append("posible_documento_identidad")
        texto = PATRON_DOCUMENTO.sub("[NUMERO_REDACTADO]", texto)

    if PATRON_CODIGO_INSTITUCIONAL.search(texto):
        hallazgos.append("posible_codigo_institucional")
        texto = PATRON_CODIGO_INSTITUCIONAL.sub("[CODIGO_REDACTADO]", texto)

    if nombres_conocidos_curso:
        for nombre in nombres_conocidos_curso:
            nombre = nombre.strip()
            if nombre and nombre.lower() in texto.lower():
                hallazgos.append("nombre_propio_conocido")
                patron_nombre = re.compile(re.escape(nombre), re.IGNORECASE)
                texto = patron_nombre.sub("[NOMBRE_REDACTADO]", texto)

    requiere_revision_manual = False
    if PATRON_NOMBRE_PROPIO_HEURISTICO.search(texto):
        # No se reemplaza automáticamente (alto riesgo de falsos positivos
        # sobre términos matemáticos capitalizados), pero se marca para
        # que un humano revise antes de continuar.
        hallazgos.append("heuristica_posible_nombre_propio_no_confirmado")
        requiere_revision_manual = True

    ok_para_enviar_ia = not requiere_revision_manual

    return ResultadoSanitizacion(
        texto_sanitizado=texto,
        ok_para_enviar_ia=ok_para_enviar_ia,
        hallazgos=hallazgos,
        requiere_revision_manual=requiere_revision_manual,
    )


def verificar_payload_antes_de_ia(payload: dict, campos_prohibidos: list[str]) -> tuple[bool, list[str]]:
    """
    Gate estructural: verifica que el diccionario que se va a enviar al
    proveedor de IA NO contenga ninguna de las llaves prohibidas por el
    contrato del prompt (ver prompts/*.json -> campos_explicitamente_prohibidos_en_entrada).

    Esto se ejecuta ADEMÁS de sanitizar_texto sobre los valores string,
    como segunda barrera independiente basada en estructura, no en texto.
    """
    errores = []
    for campo in campos_prohibidos:
        if campo in payload:
            errores.append(f"Campo prohibido presente en payload: '{campo}'")
    return (len(errores) == 0, errores)


class SanitizacionFallidaError(Exception):
    """Se lanza cuando el gate de sanitización no puede garantizar que el
    texto es seguro para salir hacia el proveedor de IA. El pipeline debe
    capturar esta excepción y enrutar el caso a revisión manual, nunca
    reintentar automáticamente enviando el texto sin cambios."""
    pass


def exigir_sanitizacion_o_bloquear(texto: str, nombres_conocidos_curso: list[str] | None = None) -> str:
    """
    Punto único de entrada que TODO llamador de core/ai_client.py debe
    usar antes de construir el payload de la API. Si no se puede
    garantizar sanitización, bloquea con excepción (no deja pasar nada
    "por defecto").
    """
    resultado = sanitizar_texto(texto, nombres_conocidos_curso=nombres_conocidos_curso)
    if not resultado.ok_para_enviar_ia:
        raise SanitizacionFallidaError(
            f"Texto requiere revisión manual antes de enviar a IA. Hallazgos: {resultado.hallazgos}"
        )
    return resultado.texto_sanitizado
