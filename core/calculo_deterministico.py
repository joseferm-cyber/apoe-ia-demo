"""
core/calculo_deterministico.py
================================
Cualquier verificación matemática (evaluar la derivada, comparar con la
respuesta del estudiante, generar la gráfica de apoyo) se hace aquí con
SymPy/NumPy/Matplotlib. La IA generativa (core/ai_client.py) NUNCA
calcula: solo recibe resultados ya verificados si el prompt los necesita
como contexto adicional.
"""

from __future__ import annotations
import io
import base64
from dataclasses import dataclass

import sympy as sp
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


@dataclass
class ResultadoDerivada:
    expresion_original: str
    derivada_simbolica: str
    valor_en_punto: float | None
    punto_evaluado: float | None


def calcular_derivada(expresion_str: str, variable: str = "x") -> ResultadoDerivada:
    """Calcula la derivada simbólica de una expresión. Ej: 'x**2 + 3*x'."""
    x = sp.symbols(variable)
    expr = sp.sympify(expresion_str)
    derivada = sp.diff(expr, x)
    return ResultadoDerivada(
        expresion_original=str(expr),
        derivada_simbolica=str(derivada),
        valor_en_punto=None,
        punto_evaluado=None,
    )


def evaluar_derivada_en_punto(expresion_str: str, punto: float, variable: str = "x") -> ResultadoDerivada:
    x = sp.symbols(variable)
    expr = sp.sympify(expresion_str)
    derivada = sp.diff(expr, x)
    valor = float(derivada.subs(x, punto))
    return ResultadoDerivada(
        expresion_original=str(expr),
        derivada_simbolica=str(derivada),
        valor_en_punto=valor,
        punto_evaluado=punto,
    )


def comparar_respuesta_estudiante(expresion_str: str, respuesta_estudiante_str: str, variable: str = "x") -> dict:
    """
    Compara simbólicamente (no por texto) la derivada correcta contra lo
    que escribió el estudiante, usando sp.simplify(a - b) == 0.
    Devuelve un resultado DETERMINISTA que puede pasarse como contexto
    de solo lectura al Prompt 1, si el diseño de la tarea lo requiere.
    """
    x = sp.symbols(variable)
    correcta = sp.diff(sp.sympify(expresion_str), x)
    try:
        propuesta = sp.sympify(respuesta_estudiante_str)
        equivalente = sp.simplify(correcta - propuesta) == 0
    except (sp.SympifyError, TypeError):
        equivalente = False
        propuesta = None

    return {
        "derivada_correcta": str(correcta),
        "respuesta_estudiante_parseada": str(propuesta) if propuesta is not None else None,
        "equivalente_simbolicamente": bool(equivalente),
    }


def generar_grafica_funcion_y_tangente(expresion_str: str, punto: float, variable: str = "x",
                                        rango: tuple[float, float] = (-5, 5)) -> str:
    """
    Genera una gráfica de la función y su recta tangente en un punto.
    Devuelve la imagen codificada en base64 (PNG) para insertarla en la
    actividad/retroalimentación sin depender de la IA generativa.
    """
    x = sp.symbols(variable)
    expr = sp.sympify(expresion_str)
    derivada = sp.diff(expr, x)

    f_num = sp.lambdify(x, expr, "numpy")
    fp_num = sp.lambdify(x, derivada, "numpy")

    xs = np.linspace(rango[0], rango[1], 400)
    ys = f_num(xs)

    pendiente = float(fp_num(punto))
    y0 = float(f_num(punto))
    tangente = pendiente * (xs - punto) + y0

    fig, ax = plt.subplots(figsize=(6, 4))
    ax.plot(xs, ys, label="f(x)")
    ax.plot(xs, tangente, "--", label=f"tangente en x={punto}")
    ax.scatter([punto], [y0], color="red", zorder=5)
    ax.axhline(0, color="gray", linewidth=0.5)
    ax.axvline(0, color="gray", linewidth=0.5)
    ax.legend()
    ax.set_title(f"f(x) = {expr}  |  f'({punto}) = {pendiente:.4f}")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("utf-8")
