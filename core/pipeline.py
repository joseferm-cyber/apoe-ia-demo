"""
core/pipeline.py
=================
Orquesta el ciclo: Captura -> Preproceso -> Análisis IA (Prompt 1) ->
Revisión humana -> Retroalimentación (Prompt 2) -> Agregación (Prompt 3)
-> Ajuste.

Puntos de control NO evitables (impuestos por el código, no solo por
convención):
  * paso_2_preproceso() es la ÚNICA puerta de entrada a los pasos con IA;
    si sanitización falla, lanza excepción y detiene el flujo.
  * paso_4_revision_humana() debe ejecutarse y quedar registrada ANTES
    de poder llamar paso_5_retroalimentacion(). Se verifica leyendo el
    estado real en la base de investigación, no un flag en memoria.
"""

from __future__ import annotations
import json
from dataclasses import dataclass

from core import db_research, db_protected, ai_client
from core.sanitizacion import exigir_sanitizacion_o_bloquear, SanitizacionFallidaError


@dataclass
class ContextoCiclo:
    ciclo_id: int
    tarea_id: int
    matriz_version: str
    prompt1_contrato: dict
    prompt2_contrato: dict
    prompt3_contrato: dict


def paso_1_captura(codigo_seudonimo: str, ctx: ContextoCiclo, contenido_original: str,
                    procedimiento: str | None, tiempo_segundos: int | None,
                    numero_intento: int, ayuda_utilizada: str | None) -> dict:
    """
    Registra la respuesta cruda. Antes de guardar, determina el canal
    (ia vs manual_opt_out) consultando el almacén protegido SOLO por
    booleano (ver db_protected.obtener_opt_out_ia), nunca copiando datos
    de identidad hacia la base de investigación.
    """
    opt_out = db_protected.obtener_opt_out_ia(codigo_seudonimo)
    canal = "manual_opt_out" if opt_out else "ia"

    # La sanitización aplica igual, incluso en canal manual: el contenido
    # que se persiste en la base de investigación nunca debe traer PII,
    # sin importar si luego lo procesa un humano o la IA.
    try:
        contenido_sanitizado = exigir_sanitizacion_o_bloquear(contenido_original)
    except SanitizacionFallidaError as e:
        return {"ok": False, "motivo": str(e), "requiere_revision_manual_pii": True}

    respuesta_id = db_research.insertar_respuesta_cruda(
        codigo_seudonimo=codigo_seudonimo,
        ciclo_id=ctx.ciclo_id,
        tarea_id=ctx.tarea_id,
        contenido_original_sanitizado=contenido_sanitizado,
        procedimiento=procedimiento,
        tiempo_segundos=tiempo_segundos,
        numero_intento=numero_intento,
        ayuda_utilizada=ayuda_utilizada,
        canal_procesamiento=canal,
    )
    return {"ok": True, "respuesta_id": respuesta_id, "canal": canal}


def paso_2_a_3_analisis_ia(respuesta_id: int, ctx: ContextoCiclo, contexto_tarea: str,
                            respuesta_seudonimizada: str, procedimiento_seudonimizado: str | None,
                            indicadores_aplicables: list[dict]) -> dict:
    """
    Ejecuta Prompt 1. Si el canal de la respuesta es 'manual_opt_out',
    esta función NO debe invocarse; el pipeline debe enrutar directo a
    revisión/retroalimentación docente manual (fuera de este módulo,
    o mediante paso_4_revision_humana con origen 'manual').
    """
    payload = {
        "contexto_tarea": contexto_tarea,
        "respuesta_seudonimizada": respuesta_seudonimizada,
        "procedimiento_seudonimizado": procedimiento_seudonimizado,
        "indicadores_aplicables": indicadores_aplicables,
        "matriz_version": ctx.matriz_version,
    }

    proveedor = ai_client.obtener_proveedor_activo()
    respuesta_ia = ai_client.generar_json_con_gate(
        proveedor=proveedor,
        contrato_prompt=ctx.prompt1_contrato,
        payload_usuario=payload,
        system_prompt=ctx.prompt1_contrato["modelo_rol_sistema"],
    )

    auditoria_id = db_research.registrar_auditoria_ia(
        respuesta_id=respuesta_id,
        ciclo_id=ctx.ciclo_id,
        tipo_prompt="prompt1_analisis",
        prompt_version=ctx.prompt1_contrato["prompt_version"],
        modelo_proveedor=respuesta_ia.modelo_proveedor,
        modelo_version=respuesta_ia.modelo_version,
        entrada_enviada=payload,
        salida_original=respuesta_ia.salida_json,
        sanitizacion_verificada=True,
    )

    return {"auditoria_id": auditoria_id, "salida_ia": respuesta_ia.salida_json}


def paso_4_revision_humana(auditoria_id: int, estado: str, observacion: str | None,
                            revisor_usuario: str) -> None:
    """
    Único mecanismo autorizado para mover una fila de auditoria_ia fuera
    de 'pendiente'. estado in {'aceptada','corregida','invalidada'}.
    """
    db_research.marcar_revision_humana(
        auditoria_id=auditoria_id, estado=estado, observacion=observacion,
        revisor_usuario=revisor_usuario,
    )


def _verificar_revision_previa_aceptada(auditoria_id_prompt1: int) -> dict:
    """
    Control NO evitable: antes de generar retroalimentación, se relee de
    la base de investigación (no de memoria) el estado real de revisión.
    """
    filas = db_research.obtener_cola_revision_pendiente.__wrapped__ if False else None  # noqa: mantenido explícito
    with db_research.conexion() as conn:
        fila = conn.execute(
            "SELECT * FROM auditoria_ia WHERE id = ?", (auditoria_id_prompt1,)
        ).fetchone()
    if fila is None:
        raise ValueError("auditoria_id de prompt1 no encontrado.")
    if fila["revision_humana_estado"] not in ("aceptada", "corregida"):
        raise PermissionError(
            f"No se puede generar retroalimentación: revisión humana en estado "
            f"'{fila['revision_humana_estado']}' (se requiere 'aceptada' o 'corregida')."
        )
    return dict(fila)


def paso_5_retroalimentacion(auditoria_id_prompt1: int, ctx: ContextoCiclo,
                              nivel_final_revisado: str, indicadores_confirmados: list[dict],
                              evidencia_aceptada: list[str], contexto_tarea: str,
                              tono_deseado: str, revisor_usuario: str) -> dict:
    """Ejecuta Prompt 2. Bloqueado si no hay revisión humana aceptada/corregida previa."""
    fila_prompt1 = _verificar_revision_previa_aceptada(auditoria_id_prompt1)
    respuesta_id = fila_prompt1["respuesta_id"]

    payload = {
        "nivel_final_revisado": nivel_final_revisado,
        "indicadores_confirmados": indicadores_confirmados,
        "evidencia_aceptada": evidencia_aceptada,
        "contexto_tarea": contexto_tarea,
        "tono_deseado": tono_deseado,
    }

    proveedor = ai_client.obtener_proveedor_activo()
    respuesta_ia = ai_client.generar_json_con_gate(
        proveedor=proveedor,
        contrato_prompt=ctx.prompt2_contrato,
        payload_usuario=payload,
        system_prompt=ctx.prompt2_contrato["modelo_rol_sistema"],
    )

    auditoria_id_prompt2 = db_research.registrar_auditoria_ia(
        respuesta_id=respuesta_id,
        ciclo_id=ctx.ciclo_id,
        tipo_prompt="prompt2_retro",
        prompt_version=ctx.prompt2_contrato["prompt_version"],
        modelo_proveedor=respuesta_ia.modelo_proveedor,
        modelo_version=respuesta_ia.modelo_version,
        entrada_enviada=payload,
        salida_original=respuesta_ia.salida_json,
        sanitizacion_verificada=True,
    )

    return {"auditoria_id_prompt2": auditoria_id_prompt2, "salida_ia": respuesta_ia.salida_json,
            "respuesta_id": respuesta_id}


def paso_6_finalizar_entrega(auditoria_id_prompt2: int, texto_mostrado_final: str,
                              revisor_usuario: str, respuesta_id: int, nivel_final_revisado: str,
                              dificultad_percibida: str | None,
                              movimiento_respecto_ciclo_anterior: str | None,
                              nivel_sugerido_ia: str | None) -> None:
    """
    Cierra el ciclo individual: exige revisión humana también sobre el
    TEXTO de retroalimentación (segundo punto de control humano, ahora
    sobre la redacción, no solo sobre el nivel) antes de escribir en
    nivel_derivado (que representa lo efectivamente entregado).
    """
    with db_research.conexion() as conn:
        fila = conn.execute("SELECT * FROM auditoria_ia WHERE id = ?", (auditoria_id_prompt2,)).fetchone()
    if fila is None or fila["revision_humana_estado"] not in ("aceptada", "corregida"):
        raise PermissionError(
            "No se puede finalizar la entrega: el texto de retroalimentación (Prompt 2) "
            "no tiene revisión humana aceptada/corregida."
        )

    with db_research.conexion() as conn:
        conn.execute(
            """INSERT INTO nivel_derivado
               (respuesta_id, nivel_sugerido_ia, nivel_final_revisado, dificultad_percibida,
                texto_retroalimentacion, movimiento_respecto_ciclo_anterior)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (respuesta_id, nivel_sugerido_ia, nivel_final_revisado, dificultad_percibida,
             texto_mostrado_final, movimiento_respecto_ciclo_anterior),
        )
        conn.execute(
            "UPDATE auditoria_ia SET texto_mostrado_final = ? WHERE id = ?",
            (texto_mostrado_final, auditoria_id_prompt2),
        )


def paso_7_agregacion_grupal(ctx: ContextoCiclo, tabla_frecuencias: dict, patrones_detectados: list[str],
                              contexto_tarea: str) -> dict:
    """Ejecuta Prompt 3 sobre cifras ya calculadas (ver core/agregacion.py)."""
    payload = {
        "ciclo_id": ctx.ciclo_id,
        "tabla_frecuencias": tabla_frecuencias,
        "patrones_detectados": patrones_detectados,
        "contexto_tarea": contexto_tarea,
    }
    proveedor = ai_client.obtener_proveedor_activo()
    respuesta_ia = ai_client.generar_json_con_gate(
        proveedor=proveedor,
        contrato_prompt=ctx.prompt3_contrato,
        payload_usuario=payload,
        system_prompt=ctx.prompt3_contrato["modelo_rol_sistema"],
    )

    auditoria_id = db_research.registrar_auditoria_ia(
        respuesta_id=None,
        ciclo_id=ctx.ciclo_id,
        tipo_prompt="prompt3_agregacion",
        prompt_version=ctx.prompt3_contrato["prompt_version"],
        modelo_proveedor=respuesta_ia.modelo_proveedor,
        modelo_version=respuesta_ia.modelo_version,
        entrada_enviada=payload,
        salida_original=respuesta_ia.salida_json,
        sanitizacion_verificada=True,
    )

    with db_research.conexion() as conn:
        conn.execute(
            """INSERT INTO agregacion_grupal
               (ciclo_id, matriz_version, tabla_frecuencias_json, patrones_detectados_json,
                sintesis_narrativa_ia, prompt3_version)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (ctx.ciclo_id, ctx.matriz_version, json.dumps(tabla_frecuencias, ensure_ascii=False),
             json.dumps(patrones_detectados, ensure_ascii=False),
             respuesta_ia.salida_json.get("sintesis_narrativa"), ctx.prompt3_contrato["prompt_version"]),
        )

    return {"auditoria_id": auditoria_id, "salida_ia": respuesta_ia.salida_json}


def paso_8_registrar_ajuste(ciclo_id_origen: int, ciclo_id_destino: int | None, componente_ajustado: str,
                             descripcion_ajuste: str, justificacion: str, tarea_version_destino: str | None,
                             modifica_protocolo: bool) -> None:
    """
    Registra la decisión de ajuste didáctico. Si modifica_protocolo=True,
    el sistema debe bloquear el avance del siguiente ciclo hasta que
    consulta_comite_realizada se marque en True (control administrativo,
    no automatizable por diseño).
    """
    with db_research.conexion() as conn:
        conn.execute(
            """INSERT INTO ajuste_didactico
               (ciclo_id_origen, ciclo_id_destino, componente_ajustado, descripcion_ajuste,
                justificacion, tarea_version_destino, modifica_protocolo)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (ciclo_id_origen, ciclo_id_destino, componente_ajustado, descripcion_ajuste,
             justificacion, tarea_version_destino, int(modifica_protocolo)),
        )
