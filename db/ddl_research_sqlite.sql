-- Versión SQLite del esquema de investigación, funcionalmente equivalente
-- a db/ddl_research.sql (referencia PostgreSQL). Usar esta para desarrollo
-- local con core/db_research.py. Diferencias: SERIAL -> INTEGER PRIMARY KEY
-- AUTOINCREMENT; sin CHECK complejos de fecha calculada; JSON como TEXT.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS participantes_seudonimos (
    codigo_seudonimo       TEXT PRIMARY KEY,
    grupo_curso            TEXT NOT NULL,
    opt_out_ia             INTEGER NOT NULL DEFAULT 0,
    estado_participacion   TEXT NOT NULL DEFAULT 'activo'
                            CHECK (estado_participacion IN ('activo','retirado','anonimizado')),
    fecha_alta             TEXT NOT NULL DEFAULT (datetime('now')),
    fecha_retiro           TEXT,
    observaciones          TEXT
);

CREATE TABLE IF NOT EXISTS matriz_apoe_version (
    matriz_version         TEXT PRIMARY KEY,
    fecha_publicacion      TEXT NOT NULL DEFAULT (datetime('now')),
    fuente_archivo         TEXT NOT NULL,
    hash_contenido         TEXT NOT NULL,
    v_aiken_resumen        TEXT,
    vigente                INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE IF NOT EXISTS matriz_apoe_dimension (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    matriz_version         TEXT NOT NULL REFERENCES matriz_apoe_version(matriz_version),
    codigo_dimension       TEXT NOT NULL,
    nombre_dimension       TEXT NOT NULL,
    UNIQUE (matriz_version, codigo_dimension)
);

CREATE TABLE IF NOT EXISTS matriz_apoe_nivel (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    matriz_version         TEXT NOT NULL REFERENCES matriz_apoe_version(matriz_version),
    codigo_nivel           TEXT NOT NULL,
    nombre_nivel           TEXT NOT NULL,
    descripcion            TEXT NOT NULL,
    UNIQUE (matriz_version, codigo_nivel)
);

CREATE TABLE IF NOT EXISTS matriz_apoe_indicador (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    matriz_version         TEXT NOT NULL,
    codigo_dimension       TEXT NOT NULL,
    codigo_nivel           TEXT NOT NULL,
    codigo_indicador       TEXT NOT NULL,
    descripcion_indicador  TEXT NOT NULL,
    criterio_interpretacion TEXT NOT NULL,
    pertinencia_1_4        INTEGER,
    claridad_1_4           INTEGER,
    suficiencia_1_4        INTEGER,
    v_aiken                REAL,
    comentario_experto     TEXT,
    UNIQUE (matriz_version, codigo_indicador)
);

CREATE TABLE IF NOT EXISTS tarea (
    tarea_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    tarea_codigo           TEXT NOT NULL,
    tarea_version          TEXT NOT NULL,
    ciclo_id               INTEGER NOT NULL,
    enunciado              TEXT NOT NULL,
    tipo_respuesta_esperada TEXT NOT NULL CHECK (tipo_respuesta_esperada IN ('texto','procedimiento','codigo','imagen')),
    fuente_archivo         TEXT,
    UNIQUE (tarea_codigo, tarea_version)
);

CREATE TABLE IF NOT EXISTS tarea_indicador_observable (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    tarea_id               INTEGER NOT NULL REFERENCES tarea(tarea_id),
    matriz_version         TEXT NOT NULL,
    codigo_indicador       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ciclo (
    ciclo_id               INTEGER PRIMARY KEY AUTOINCREMENT,
    numero_ciclo           INTEGER NOT NULL UNIQUE,
    fecha_inicio           TEXT NOT NULL,
    fecha_cierre           TEXT,
    matriz_version_usada   TEXT NOT NULL REFERENCES matriz_apoe_version(matriz_version),
    tarea_id_usada         INTEGER NOT NULL REFERENCES tarea(tarea_id),
    prompt1_version        TEXT NOT NULL,
    prompt2_version        TEXT NOT NULL,
    prompt3_version        TEXT NOT NULL,
    estado                 TEXT NOT NULL DEFAULT 'en_curso' CHECK (estado IN ('en_curso','cerrado'))
);

CREATE TABLE IF NOT EXISTS respuesta_cruda (
    respuesta_id           INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_seudonimo       TEXT NOT NULL,
    ciclo_id               INTEGER NOT NULL,
    tarea_id               INTEGER NOT NULL,
    contenido_original     TEXT NOT NULL,
    procedimiento          TEXT,
    tiempo_segundos        INTEGER,
    numero_intento         INTEGER NOT NULL DEFAULT 1,
    ayuda_utilizada        TEXT,
    canal_procesamiento    TEXT NOT NULL DEFAULT 'ia' CHECK (canal_procesamiento IN ('ia','manual_opt_out')),
    fecha_hora             TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE (codigo_seudonimo, ciclo_id, tarea_id, numero_intento)
);

CREATE TABLE IF NOT EXISTS indicador_identificado (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    respuesta_id           INTEGER NOT NULL REFERENCES respuesta_cruda(respuesta_id),
    matriz_version         TEXT NOT NULL,
    codigo_indicador       TEXT NOT NULL,
    presente               INTEGER NOT NULL,
    evidencia_textual      TEXT,
    origen                 TEXT NOT NULL DEFAULT 'ia_prompt1' CHECK (origen IN ('ia_prompt1','manual'))
);

CREATE TABLE IF NOT EXISTS nivel_derivado (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    respuesta_id           INTEGER NOT NULL UNIQUE REFERENCES respuesta_cruda(respuesta_id),
    nivel_sugerido_ia      TEXT,
    nivel_final_revisado   TEXT NOT NULL CHECK (nivel_final_revisado IN ('A','P','O','E','SEC')),
    dificultad_percibida   TEXT,
    texto_retroalimentacion TEXT,
    movimiento_respecto_ciclo_anterior TEXT,
    fecha_hora             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS agregacion_grupal (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    ciclo_id               INTEGER NOT NULL,
    matriz_version         TEXT NOT NULL,
    tabla_frecuencias_json TEXT NOT NULL,
    patrones_detectados_json TEXT,
    sintesis_narrativa_ia  TEXT,
    prompt3_version        TEXT NOT NULL,
    fecha_hora             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ajuste_didactico (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    ciclo_id_origen        INTEGER NOT NULL,
    ciclo_id_destino       INTEGER,
    componente_ajustado    TEXT NOT NULL CHECK (componente_ajustado IN ('enfasis','representacion','dificultad','orientacion','otro')),
    descripcion_ajuste     TEXT NOT NULL,
    justificacion          TEXT NOT NULL,
    tarea_version_destino  TEXT,
    modifica_protocolo     INTEGER NOT NULL DEFAULT 0,
    consulta_comite_realizada INTEGER NOT NULL DEFAULT 0,
    fecha_hora             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS auditoria_ia (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    respuesta_id           INTEGER REFERENCES respuesta_cruda(respuesta_id),
    ciclo_id               INTEGER NOT NULL,
    tipo_prompt            TEXT NOT NULL CHECK (tipo_prompt IN ('prompt1_analisis','prompt2_retro','prompt3_agregacion')),
    prompt_version         TEXT NOT NULL,
    modelo_proveedor       TEXT NOT NULL,
    modelo_version         TEXT NOT NULL,
    entrada_enviada_json   TEXT NOT NULL,
    salida_original_json   TEXT NOT NULL,
    revision_humana_estado TEXT NOT NULL DEFAULT 'pendiente' CHECK (revision_humana_estado IN ('pendiente','aceptada','corregida','invalidada')),
    revision_humana_observacion TEXT,
    revisor_usuario        TEXT,
    texto_mostrado_final   TEXT,
    sanitizacion_verificada INTEGER NOT NULL CHECK (sanitizacion_verificada = 1),
    incidencia             TEXT,
    fecha_hora             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS bitacora_ciclo (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    ciclo_id               INTEGER NOT NULL,
    incidencias_tecnicas   TEXT,
    dudas_recurrentes      TEXT,
    sintesis_evidencias    TEXT,
    revision_componente_generativo TEXT,
    decision_entre_ciclos  TEXT,
    autor_usuario          TEXT NOT NULL,
    fecha_hora             TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS incidente_seguridad (
    id                     INTEGER PRIMARY KEY AUTOINCREMENT,
    fecha_deteccion        TEXT NOT NULL DEFAULT (datetime('now')),
    tipo_incidente         TEXT NOT NULL,
    descripcion            TEXT NOT NULL,
    alcance_afectado       TEXT NOT NULL,
    conjunto_datos_suspendido INTEGER NOT NULL DEFAULT 0,
    acciones_tomadas       TEXT,
    responsable_reporte    TEXT NOT NULL,
    estado                 TEXT NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto','en_investigacion','cerrado')),
    fecha_cierre           TEXT
);

CREATE INDEX IF NOT EXISTS idx_respuesta_cruda_codigo_ciclo ON respuesta_cruda(codigo_seudonimo, ciclo_id);
CREATE INDEX IF NOT EXISTS idx_indicador_respuesta ON indicador_identificado(respuesta_id);
CREATE INDEX IF NOT EXISTS idx_auditoria_ciclo_tipo ON auditoria_ia(ciclo_id, tipo_prompt);
CREATE INDEX IF NOT EXISTS idx_nivel_derivado_respuesta ON nivel_derivado(respuesta_id);
