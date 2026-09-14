# Sistema de información — Proyecto APOE-IA

Seguimiento formativo de la comprensión conceptual de la derivada como razón de cambio,
con apoyo delimitado de IA generativa y revisión humana obligatoria. **No es una plataforma
de calificación ni de decisión académica automatizada.**

## Estructura del proyecto

```
apoe_ia_system/
├── db/
│   ├── ddl_research.sql          # Esquema de investigación (referencia PostgreSQL)
│   ├── ddl_research_sqlite.sql   # Mismo esquema, adaptado a SQLite (desarrollo local)
│   ├── ddl_protected.sql         # Almacén protegido (referencia PostgreSQL)
│   └── ddl_protected_sqlite.sql  # Almacén protegido, SQLite
├── matriz_apoe/
│   └── matriz_apoe_v1.json       # Catálogo versionado: 13 dimensiones, 5 niveles, indicadores
├── prompts/
│   ├── prompt1_analisis_individual_v1.json   # Contrato de entrada/salida — análisis individual
│   ├── prompt2_retroalimentacion_v1.json     # Contrato — retroalimentación individual
│   └── prompt3_agregacion_grupal_v1.json     # Contrato — síntesis narrativa grupal
├── tareas/
│   └── tarea_ciclo1_v1.json      # Ejemplo de tarea ancla versionada
├── core/
│   ├── sanitizacion.py           # Gate PROGRAMÁTICO de PII, obligatorio antes de cualquier llamada a IA
│   ├── ai_client.py              # Abstracción del proveedor de IA (intercambiable)
│   ├── calculo_deterministico.py # SymPy/NumPy/Matplotlib — la IA nunca calcula
│   ├── agregacion.py             # Frecuencias/patrones grupales deterministas
│   ├── db_research.py            # Conector EXCLUSIVO al almacén de investigación (seudonimizado)
│   ├── db_protected.py           # Conector EXCLUSIVO al almacén protegido (identidad) — sin import de ai_client
│   └── pipeline.py               # Orquesta el ciclo con puntos de control humano no evitables
├── app/
│   └── app_streamlit.py          # App orquestadora (captura, revisión, retro, agregación, ajuste, auditoría, bitácora)
└── docs/
    ├── ficha_control_proveedor_ia.md
    ├── procedimiento_incidentes_seguridad.md
    └── plan_retencion_borrado.md
```

## Puesta en marcha (desarrollo local, SQLite)

```bash
pip install -r requirements.txt

python - <<'PY'
from core import db_research, db_protected
db_research.inicializar_esquema("db/ddl_research_sqlite.sql")
db_protected.inicializar_esquema("db/ddl_protected_sqlite.sql")
PY

streamlit run app/app_streamlit.py
```

Antes de usar con datos reales de estudiantes:
1. Completar `docs/ficha_control_proveedor_ia.md` y registrar el proveedor definido en `core/ai_client.py`
   (implementar una subclase de `AIProvider`; hasta entonces el sistema bloquea explícitamente con
   `ProveedorNoConfigurado`, en vez de simular respuestas).
2. Completar `matriz_apoe/matriz_apoe_v1.json` con el banco definitivo de indicadores validado por expertos
   (V de Aiken, pertinencia/claridad/suficiencia).
3. Cargar en el almacén protegido la tabla maestra de códigos y los consentimientos reales, en una instancia
   físicamente separada (host o archivo distinto) del almacén de investigación.

## Cómo el diseño cumple cada criterio de aceptación

| Criterio | Dónde se implementa |
|---|---|
| Ninguna llamada a IA sin sanitización verificada | `core/sanitizacion.py::exigir_sanitizacion_o_bloquear` + `core/ai_client.py::generar_json_con_gate` (doble barrera: texto y estructura) + constraint `chk_sanitizacion_obligatoria` en `auditoria_ia` |
| Ninguna retroalimentación sin revisión humana registrada | `core/pipeline.py::_verificar_revision_previa_aceptada` (bloquea Prompt 2) y `paso_6_finalizar_entrega` (bloquea también sobre el texto de Prompt 2) |
| Trazabilidad completa reconstruible por código+ciclo | `core/db_research.py::obtener_trazabilidad_completa`, vista "Panel de auditoría IA" en la app |
| Separación física/lógica de almacenes, sin ruta de código hacia IA | `core/db_protected.py` no importa `core/ai_client.py`; `core/db_research.py` es el único conectado al pipeline de IA |
| Opt-out de IA enrutado a revisión manual | `core/pipeline.py::paso_1_captura` consulta `db_protected.obtener_opt_out_ia` y fija `canal_procesamiento` |
| Matriz, prompts y tareas versionados y referenciados | `matriz_apoe/*.json`, `prompts/*.json`, `tareas/*.json`; cada fila de `ciclo` fija `matriz_version_usada`, `prompt1_version`, `prompt2_version`, `prompt3_version` |

## Limitaciones y pendientes explícitos

- El proveedor de IA generativa está pendiente de definir (ver `docs/ficha_control_proveedor_ia.md`);
  el sistema opera con un stub que bloquea (`ProveedorNoConfigurado`) hasta que se implemente un proveedor real.
- La matriz APOE incluida (`matriz_apoe_v1.json`) trae solo 3 indicadores de ejemplo; debe completarse con
  el banco definitivo validado por el comité antes de uso en campo.
- Los DDL de referencia (`ddl_research.sql`, `ddl_protected.sql`) usan sintaxis PostgreSQL; las versiones
  `_sqlite.sql` son las que efectivamente ejecuta `core/db_research.py` y `core/db_protected.py` en este
  esqueleto de desarrollo.
- Autenticación real de usuarios (más allá del selector de rol en la barra lateral de Streamlit) debe
  integrarse antes de producción (ej. SSO institucional), junto con cifrado en reposo del archivo/instancia
  del almacén protegido.
