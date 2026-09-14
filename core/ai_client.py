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


def obtener_proveedor_activo() -> AIProvider:
    """
    Punto de configuración único. Cambiar aquí para apuntar al proveedor
    real una vez definido/contratado y registrado en
    docs/ficha_control_proveedor_ia.md.
    """
    return ProveedorNoConfigurado()
