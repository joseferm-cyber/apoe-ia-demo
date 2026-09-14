"""
core/agregacion.py
===================
Cálculo determinista de frecuencias y patrones a nivel de grupo. El
modelo generativo (Prompt 3) NUNCA calcula estos números: los recibe ya
calculados y solo los redacta en prosa (ver prompts/prompt3_*.json).
"""

from __future__ import annotations
from collections import Counter, defaultdict


def calcular_frecuencias_por_nivel(niveles_finales: list[str]) -> dict:
    """niveles_finales: lista de 'A'|'P'|'O'|'E'|'SEC', uno por estudiante."""
    total = len(niveles_finales)
    conteo = Counter(niveles_finales)
    return {
        "total_respuestas": total,
        "conteo_absoluto": dict(conteo),
        "porcentaje": {nivel: round(100 * c / total, 1) if total else 0.0 for nivel, c in conteo.items()},
    }


def calcular_frecuencias_por_indicador(indicadores_por_estudiante: list[list[dict]]) -> dict:
    """
    indicadores_por_estudiante: lista donde cada elemento es la lista de
    indicadores_identificados (dicts con codigo_indicador y presente) de
    un estudiante para el ciclo.
    """
    presentes = defaultdict(int)
    total_evaluados = defaultdict(int)

    for lista_ind in indicadores_por_estudiante:
        for ind in lista_ind:
            codigo = ind["codigo_indicador"]
            total_evaluados[codigo] += 1
            if ind.get("presente"):
                presentes[codigo] += 1

    resultado = {}
    for codigo, total in total_evaluados.items():
        resultado[codigo] = {
            "presentes": presentes.get(codigo, 0),
            "total_evaluados": total,
            "porcentaje": round(100 * presentes.get(codigo, 0) / total, 1) if total else 0.0,
        }
    return resultado


def detectar_movimiento_entre_ciclos(nivel_ciclo_anterior: dict[str, str], nivel_ciclo_actual: dict[str, str]) -> dict:
    """
    Ambos diccionarios: {codigo_seudonimo: nivel ('A'|'P'|'O'|'E'|'SEC')}.
    Orden de progresión asumido: SEC < A < P < O < E.
    Devuelve conteos agregados (nunca lista estudiante por estudiante en
    reportes grupales, para no permitir reidentificación por descarte).
    """
    orden = {"SEC": 0, "A": 1, "P": 2, "O": 3, "E": 4}
    avanza = se_mantiene = retrocede = sin_dato = 0

    for codigo, nivel_actual in nivel_ciclo_actual.items():
        nivel_previo = nivel_ciclo_anterior.get(codigo)
        if nivel_previo is None:
            sin_dato += 1
            continue
        if orden.get(nivel_actual, -1) > orden.get(nivel_previo, -1):
            avanza += 1
        elif orden.get(nivel_actual, -1) == orden.get(nivel_previo, -1):
            se_mantiene += 1
        else:
            retrocede += 1

    return {
        "avanza": avanza,
        "se_mantiene": se_mantiene,
        "retrocede": retrocede,
        "sin_dato_ciclo_anterior": sin_dato,
    }


def construir_patrones_detectados(frecuencias_nivel: dict, frecuencias_indicador: dict,
                                   movimiento: dict | None = None, umbral_patron_pct: float = 30.0) -> list[str]:
    """
    Genera hallazgos deterministas en lenguaje simple (no narrativo aún;
    la redacción final de estos hallazgos la hace Prompt 3, pero las
    cifras y la detección del patrón ya están fijadas aquí).
    """
    patrones = []

    for nivel, pct in frecuencias_nivel.get("porcentaje", {}).items():
        if pct >= umbral_patron_pct:
            patrones.append(f"nivel_{nivel}_concentra_{pct}pct_del_grupo")

    for codigo, datos in frecuencias_indicador.items():
        if datos["porcentaje"] <= 100 - umbral_patron_pct and datos["porcentaje"] < 40:
            patrones.append(f"indicador_{codigo}_bajo_dominio_{datos['porcentaje']}pct")

    if movimiento:
        if movimiento.get("retrocede", 0) > movimiento.get("avanza", 0):
            patrones.append("mas_estudiantes_retroceden_que_avanzan_respecto_ciclo_anterior")
        elif movimiento.get("avanza", 0) > 0:
            patrones.append(f"avance_neto_de_{movimiento['avanza']}_estudiantes_respecto_ciclo_anterior")

    return patrones
