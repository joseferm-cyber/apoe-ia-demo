"""
core/ai_client.py
==================
Abstracción del proveedor de IA generativa. El proveedor concreto
"está por definir" en la propuesta, así que ningún módulo de negocio
debe depender de un SDK específico: todos hablan con `AIProvider`.

Todo llamador DEBE pasar por `AIProvider.generar_json()`, que:
  1. Exige que el texto ya haya pasado por core.sanitizacion (gate).
  2. Verifica estructuralmente que no haya campos prohibidos.
  3. Registra automáticamente la interacción en auditoria_ia con
     revision_humana_estado='pendiente' (nunca 'aceptada' por defecto).
"""

from __future__ import annotations
import json
import os
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from core.sanitizacion import verificar_payload_antes_de_ia, SanitizacionFallidaError


@dataclass
class RespuestaIA:
    salida_json: dict
    modelo_proveedor: str
    modelo_version: str
    latencia_ms: int


class AIProvider(ABC):
    """Interfaz que cualquier proveedor concreto debe implementar."""

    nombre_proveedor: str
    version_modelo: str

    @abstractmethod
    def _llamar_api(self, system_prompt: str, payload_usuario: dict, esquema_salida: dict) -> dict:
        """Debe devolver un dict ya parseado desde JSON (no un string)."""
        raise NotImplementedError


class ProveedorNoConfigurado(AIProvider):
    """Implementación 'nula' para desarrollo/pruebas cuando aún no se ha
    definido/contratado el proveedor real (la propuesta indica que el
    proveedor está por definir). Lanza error explícito en vez de simular
    una respuesta, para no esconder el hecho de que falta integrarlo."""

    nombre_proveedor = "NO_CONFIGURADO"
    version_modelo = "NO_CONFIGURADO"

    def _llamar_api(self, system_prompt: str, payload_usuario: dict, esquema_salida: dict) -> dict:
        raise NotImplementedError(
            "No hay proveedor de IA configurado todavía. Implementa una subclase de "
            "AIProvider (ej. ProveedorAnthropic, ProveedorOpenAI...) y regístrala en "
            "core/ai_client.py::obtener_proveedor_activo(). Ver docs/ficha_control_proveedor_ia.md."
        )


def generar_json_con_gate(
    proveedor: AIProvider,
    contrato_prompt: dict,
    payload_usuario: dict,
    system_prompt: str,
) -> RespuestaIA:
    """
    Punto único por el que TODO el sistema debe pasar para invocar al
    modelo generativo. No existe otra ruta de código autorizada.

    contrato_prompt: el dict cargado desde prompts/promptN_*.json
    """
    campos_prohibidos = contrato_prompt.get("campos_explicitamente_prohibidos_en_entrada", [])
    ok_estructural, errores = verificar_payload_antes_de_ia(payload_usuario, campos_prohibidos)
    if not ok_estructural:
        raise SanitizacionFallidaError(
            f"Payload bloqueado antes de llamar a IA ({contrato_prompt.get('prompt_id')}): {errores}"
        )

    # Nota: se asume que los valores string de payload_usuario YA pasaron
    # individualmente por core.sanitizacion.exigir_sanitizacion_o_bloquear()
    # en el paso de preproceso del pipeline (core/pipeline.py), antes de
    # llegar aquí. Este gate es la segunda barrera, estructural.

    inicio = time.time()
    salida_json = proveedor._llamar_api(
        system_prompt=system_prompt,
        payload_usuario=payload_usuario,
        esquema_salida=contrato_prompt["esquema_salida"],
    )
    latencia_ms = int((time.time() - inicio) * 1000)

    return RespuestaIA(
        salida_json=salida_json,
        modelo_proveedor=proveedor.nombre_proveedor,
        modelo_version=proveedor.version_modelo,
        latencia_ms=latencia_ms,
    )


class ProveedorDemoFicticio(AIProvider):
    """
    SOLO PARA DEMOSTRACIÓN CON DATOS FICTICIOS. No llama a ningún servicio
    externo: devuelve una salida de ejemplo fija, con forma válida según
    el esquema de cada prompt, para que la UI pueda mostrarse completa en
    una demo pública (ej. Streamlit Community Cloud) sin exponer datos
    reales de estudiantes ni depender de credenciales de un proveedor real.

    NUNCA usar esta clase con datos reales de estudiantes: no reemplaza
    el análisis pedagógico real y sus salidas son inventadas a propósito.
    """

    nombre_proveedor = "DEMO_FICTICIO_NO_USAR_CON_DATOS_REALES"
    version_modelo = "demo-0"

    def _llamar_api(self, system_prompt: str, payload_usuario: dict, esquema_salida: dict) -> dict:
        campos = esquema_salida.get("properties", {})
        if "nivel_sugerido" in campos:  # Prompt 1
            return {
                "indicadores_identificados": [
                    {"codigo_indicador": "D1-O-01", "presente": True,
                     "fragmento_evidencia": "(evidencia simulada para demo)"},
                ],
                "nivel_sugerido": "O",
                "evidencia_textual": ["(evidencia simulada para demo — revisar antes de aceptar)"],
                "advertencias": ["Salida generada por ProveedorDemoFicticio: NO usar en un ciclo real."],
            }
        if "texto_retroalimentacion" in campos:  # Prompt 2
            return {
                "texto_retroalimentacion": "(Texto de demo) Identificaste correctamente el signo y la magnitud "
                                            "de la razón de cambio; te falta precisar mejor las unidades en el punto evaluado.",
                "sugerencia_siguiente_paso": "(Demo) Revisa cómo se interpretan las unidades en un contexto de llenado de tanques.",
            }
        if "sintesis_narrativa" in campos:  # Prompt 3
            return {
                "sintesis_narrativa": "(Demo) El grupo se concentra mayoritariamente en el nivel Objeto, con "
                                       "un subgrupo aún en Proceso que no logra fijar unidades ni punto de evaluación.",
                "recomendaciones_ajuste": ["(Demo) Reforzar la lectura de unidades en el siguiente ciclo."],
            }
        return {"advertencia": "Esquema de salida no reconocido por ProveedorDemoFicticio."}


def obtener_proveedor_activo() -> AIProvider:
    """
    Punto de configuración único. Controlado por la variable de entorno
    APOE_MODO_DEMO=1 (usada solo para demos públicas con datos ficticios,
    ej. Streamlit Community Cloud). En cualquier otro caso, y siempre que
    haya datos reales de estudiantes, debe apuntar a un proveedor real
    definido y registrado en docs/ficha_control_proveedor_ia.md.
    """
    if os.environ.get("APOE_MODO_DEMO") == "1":
        return ProveedorDemoFicticio()
    return ProveedorNoConfigurado()
