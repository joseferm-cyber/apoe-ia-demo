-- =====================================================================
-- BASE DE DATOS DE INVESTIGACIÓN (Bloque C.1)
-- Proyecto APOE-IA — Seguimiento formativo de la derivada
-- =====================================================================
-- REGLA DE DISEÑO NO NEGOCIABLE:
--   Esta base NUNCA contiene nombre, documento, correo, teléfono ni
--   ninguna otra columna que permita reidentificar a un estudiante.
--   La única llave de vinculación es "codigo_seudonimo" (ej. MI1A-001).
--   La tabla que traduce codigo_seudonimo <-> identidad vive
--   EXCLUSIVAMENTE en ddl_protected.sql, en otro archivo/instancia/
--   esquema con control de acceso distinto.
--
-- Motor de referencia: PostgreSQL (compatible con SQLite salvo tipos
-- JSONB/TIMESTAMP WITH TIME ZONE, anotados donde aplica).
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS investigacion;
SET search_path TO investigacion;

-- ---------------------------------------------------------------------
-- 0. PARTICIPANTES (vista puramente seudonimizada, espejo de estado)
-- ---------------------------------------------------------------------
-- No es la fuente de verdad de identidad ni de consentimiento (eso vive
-- en el almacén protegido). Aquí solo se refleja el estado operativo
-- necesario para enrutar el pipeline (opt-out de IA, activo/retirado).
CREATE TABLE participantes_seudonimos (
    codigo_seudonimo       VARCHAR(20) PRIMARY KEY,        -- ej. MI1A-001
    grupo_curso            VARCHAR(50) NOT NULL,
    opt_out_ia             BOOLEAN NOT NULL DEFAULT FALSE, -- TRUE = solo revisión docente manual
    estado_participacion   VARCHAR(20) NOT NULL DEFAULT 'activo'
                            CHECK (estado_participacion IN ('activo','retirado','anonimizado')),
    fecha_alta             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fecha_retiro           TIMESTAMP NULL,
    observaciones          TEXT
);

-- ---------------------------------------------------------------------
-- 1. CATÁLOGO VERSIONADO: MATRIZ APOE
-- ---------------------------------------------------------------------
CREATE TABLE matriz_apoe_version (
    matriz_version         VARCHAR(20) PRIMARY KEY,        -- ej. 'v1', 'v2'
    fecha_publicacion      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    fuente_archivo         TEXT NOT NULL,                  -- ruta/commit git del JSON versionado
    hash_contenido         VARCHAR(64) NOT NULL,           -- sha256 del JSON, para integridad
    v_aiken_resumen        TEXT,                           -- resumen de validación de expertos
    vigente                BOOLEAN NOT NULL DEFAULT TRUE
);

CREATE TABLE matriz_apoe_dimension (
    id                     SERIAL PRIMARY KEY,
    matriz_version         VARCHAR(20) NOT NULL REFERENCES matriz_apoe_version(matriz_version),
    codigo_dimension       VARCHAR(5)  NOT NULL,           -- D1..D13
    nombre_dimension       TEXT NOT NULL,
    UNIQUE (matriz_version, codigo_dimension)
);

CREATE TABLE matriz_apoe_nivel (
    id                     SERIAL PRIMARY KEY,
    matriz_version         VARCHAR(20) NOT NULL REFERENCES matriz_apoe_version(matriz_version),
    codigo_nivel           VARCHAR(5)  NOT NULL,           -- A, P, O, E, SEC
    nombre_nivel           TEXT NOT NULL,
    descripcion            TEXT NOT NULL,
    UNIQUE (matriz_version, codigo_nivel)
);

CREATE TABLE matriz_apoe_indicador (
    id                     SERIAL PRIMARY KEY,
    matriz_version         VARCHAR(20) NOT NULL REFERENCES matriz_apoe_version(matriz_version),
    codigo_dimension       VARCHAR(5) NOT NULL,
    codigo_nivel           VARCHAR(5) NOT NULL,
    codigo_indicador        VARCHAR(20) NOT NULL,          -- ej. D1-O-01
    descripcion_indicador  TEXT NOT NULL,
    criterio_interpretacion TEXT NOT NULL,
    pertinencia_1_4        SMALLINT CHECK (pertinencia_1_4 BETWEEN 1 AND 4),
    claridad_1_4           SMALLINT CHECK (claridad_1_4 BETWEEN 1 AND 4),
    suficiencia_1_4        SMALLINT CHECK (suficiencia_1_4 BETWEEN 1 AND 4),
    v_aiken                NUMERIC(4,3),
    comentario_experto     TEXT,
    UNIQUE (matriz_version, codigo_indicador)
);

-- ---------------------------------------------------------------------
-- 2. BANCO DE TAREAS / ACTIVIDAD COMÚN (versionado)
-- ---------------------------------------------------------------------
CREATE TABLE tarea (
    tarea_id               SERIAL PRIMARY KEY,
    tarea_codigo           VARCHAR(30) NOT NULL,           -- ej. TAREA-CICLO1
    tarea_version          VARCHAR(20) NOT NULL,
    ciclo_id               INTEGER NOT NULL,
    enunciado              TEXT NOT NULL,
    tipo_respuesta_esperada VARCHAR(20) NOT NULL CHECK (tipo_respuesta_esperada IN ('texto','procedimiento','codigo','imagen')),
    fuente_archivo         TEXT,                            -- ruta/commit git
    UNIQUE (tarea_codigo, tarea_version)
);

CREATE TABLE tarea_indicador_observable (
    id                     SERIAL PRIMARY KEY,
    tarea_id               INTEGER NOT NULL REFERENCES tarea(tarea_id),
    matriz_version         VARCHAR(20) NOT NULL,
    codigo_indicador       VARCHAR(20) NOT NULL            -- referencia lógica a matriz_apoe_indicador
);

-- ---------------------------------------------------------------------
-- 3. CICLOS DE SEGUIMIENTO FORMATIVO
-- ---------------------------------------------------------------------
CREATE TABLE ciclo (
    ciclo_id               SERIAL PRIMARY KEY,
    numero_ciclo           SMALLINT NOT NULL UNIQUE,        -- 1, 2, 3...
    fecha_inicio           DATE NOT NULL,
    fecha_cierre           DATE,
    matriz_version_usada   VARCHAR(20) NOT NULL REFERENCES matriz_apoe_version(matriz_version),
    tarea_id_usada         INTEGER NOT NULL REFERENCES tarea(tarea_id),
    prompt1_version        VARCHAR(20) NOT NULL,
    prompt2_version        VARCHAR(20) NOT NULL,
    prompt3_version        VARCHAR(20) NOT NULL,
    estado                 VARCHAR(20) NOT NULL DEFAULT 'en_curso'
                            CHECK (estado IN ('en_curso','cerrado'))
);

-- ---------------------------------------------------------------------
-- CAPA 1 · RESPUESTAS CRUDAS (seudonimizadas)
-- ---------------------------------------------------------------------
CREATE TABLE respuesta_cruda (
    respuesta_id           SERIAL PRIMARY KEY,
    codigo_seudonimo       VARCHAR(20) NOT NULL REFERENCES participantes_seudonimos(codigo_seudonimo),
    ciclo_id               INTEGER NOT NULL REFERENCES ciclo(ciclo_id),
    tarea_id               INTEGER NOT NULL REFERENCES tarea(tarea_id),
    contenido_original     TEXT NOT NULL,          -- ya pasado por sanitización de PII antes de guardar aquí
    procedimiento          TEXT,
    tiempo_segundos        INTEGER,
    numero_intento         SMALLINT NOT NULL DEFAULT 1,
    ayuda_utilizada        TEXT,
    canal_procesamiento    VARCHAR(20) NOT NULL DEFAULT 'ia'
                            CHECK (canal_procesamiento IN ('ia','manual_opt_out')),
    fecha_hora             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (codigo_seudonimo, ciclo_id, tarea_id, numero_intento)
);

-- ---------------------------------------------------------------------
-- CAPA 2 · INDICADORES IDENTIFICADOS (salida de Prompt 1, PRE-revisión)
-- ---------------------------------------------------------------------
CREATE TABLE indicador_identificado (
    id                     SERIAL PRIMARY KEY,
    respuesta_id           INTEGER NOT NULL REFERENCES respuesta_cruda(respuesta_id),
    matriz_version         VARCHAR(20) NOT NULL,
    codigo_indicador       VARCHAR(20) NOT NULL,
    presente               BOOLEAN NOT NULL,
    evidencia_textual      TEXT,                    -- fragmento citado de la respuesta seudonimizada
    origen                 VARCHAR(20) NOT NULL DEFAULT 'ia_prompt1'
                            CHECK (origen IN ('ia_prompt1','manual'))
);

-- ---------------------------------------------------------------------
-- CAPA 3 · NIVEL DERIVADO (POST revisión humana obligatoria)
-- ---------------------------------------------------------------------
CREATE TABLE nivel_derivado (
    id                     SERIAL PRIMARY KEY,
    respuesta_id           INTEGER NOT NULL UNIQUE REFERENCES respuesta_cruda(respuesta_id),
    nivel_sugerido_ia      VARCHAR(5),              -- A/P/O/E/SEC propuesto por Prompt 1 (puede ser NULL si opt-out)
    nivel_final_revisado   VARCHAR(5) NOT NULL CHECK (nivel_final_revisado IN ('A','P','O','E','SEC')),
    dificultad_percibida   VARCHAR(20),
    texto_retroalimentacion TEXT,                   -- salida final de Prompt 2, tal como se mostró
    movimiento_respecto_ciclo_anterior VARCHAR(20), -- 'avanza','se_mantiene','retrocede','sin_dato'
    fecha_hora             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- NIVEL GRUPAL · agregación determinista + síntesis narrativa (Prompt 3)
-- ---------------------------------------------------------------------
CREATE TABLE agregacion_grupal (
    id                     SERIAL PRIMARY KEY,
    ciclo_id               INTEGER NOT NULL REFERENCES ciclo(ciclo_id),
    matriz_version         VARCHAR(20) NOT NULL,
    tabla_frecuencias_json TEXT NOT NULL,           -- JSON calculado deterministamente (no por IA)
    patrones_detectados_json TEXT,                  -- salida estructurada, cálculo determinista
    sintesis_narrativa_ia  TEXT,                    -- SOLO redacción de Prompt 3 sobre datos ya calculados
    prompt3_version        VARCHAR(20) NOT NULL,
    fecha_hora             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE ajuste_didactico (
    id                     SERIAL PRIMARY KEY,
    ciclo_id_origen        INTEGER NOT NULL REFERENCES ciclo(ciclo_id),
    ciclo_id_destino       INTEGER REFERENCES ciclo(ciclo_id),
    componente_ajustado    VARCHAR(30) NOT NULL CHECK (componente_ajustado IN
                            ('enfasis','representacion','dificultad','orientacion','otro')),
    descripcion_ajuste     TEXT NOT NULL,
    justificacion          TEXT NOT NULL,
    tarea_version_destino  VARCHAR(20),
    modifica_protocolo     BOOLEAN NOT NULL DEFAULT FALSE, -- bandera de consulta obligatoria a comité
    consulta_comite_realizada BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_hora             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- AUDITORÍA IA — obligatoria por cada interacción con el modelo generativo
-- ---------------------------------------------------------------------
CREATE TABLE auditoria_ia (
    id                     SERIAL PRIMARY KEY,
    respuesta_id           INTEGER REFERENCES respuesta_cruda(respuesta_id), -- NULL si es Prompt 3 (grupal)
    ciclo_id               INTEGER NOT NULL REFERENCES ciclo(ciclo_id),
    tipo_prompt            VARCHAR(20) NOT NULL CHECK (tipo_prompt IN ('prompt1_analisis','prompt2_retro','prompt3_agregacion')),
    prompt_version         VARCHAR(20) NOT NULL,
    modelo_proveedor       VARCHAR(50) NOT NULL,
    modelo_version         VARCHAR(50) NOT NULL,
    entrada_enviada_json   TEXT NOT NULL,           -- lo que realmente salió hacia el proveedor (ya sanitizado)
    salida_original_json   TEXT NOT NULL,           -- respuesta cruda del modelo, sin editar
    revision_humana_estado VARCHAR(20) NOT NULL DEFAULT 'pendiente'
                            CHECK (revision_humana_estado IN ('pendiente','aceptada','corregida','invalidada')),
    revision_humana_observacion TEXT,
    revisor_usuario        VARCHAR(50),             -- referencia a usuario de app, no a identidad de estudiante
    texto_mostrado_final   TEXT,                    -- lo que efectivamente llegó al estudiante (si aplica)
    sanitizacion_verificada BOOLEAN NOT NULL,        -- resultado del gate programático (ver core/sanitizacion.py)
    incidencia             TEXT,
    fecha_hora             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- No se permite auditoría IA sin verificación de sanitización exitosa.
ALTER TABLE auditoria_ia
    ADD CONSTRAINT chk_sanitizacion_obligatoria
    CHECK (sanitizacion_verificada = TRUE);

-- ---------------------------------------------------------------------
-- BITÁCORA DE IMPLEMENTACIÓN POR CICLO
-- ---------------------------------------------------------------------
CREATE TABLE bitacora_ciclo (
    id                     SERIAL PRIMARY KEY,
    ciclo_id               INTEGER NOT NULL REFERENCES ciclo(ciclo_id),
    incidencias_tecnicas   TEXT,
    dudas_recurrentes      TEXT,
    sintesis_evidencias    TEXT,
    revision_componente_generativo TEXT,   -- resumen de aceptadas/corregidas/invalidadas y errores
    decision_entre_ciclos  TEXT,
    autor_usuario          VARCHAR(50) NOT NULL,
    fecha_hora             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ---------------------------------------------------------------------
-- REGISTRO DE INCIDENTES DE SEGURIDAD
-- ---------------------------------------------------------------------
CREATE TABLE incidente_seguridad (
    id                     SERIAL PRIMARY KEY,
    fecha_deteccion        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    tipo_incidente         VARCHAR(50) NOT NULL, -- 'acceso_no_autorizado','perdida_datos','fuga_pii','otro'
    descripcion            TEXT NOT NULL,
    alcance_afectado       TEXT NOT NULL,        -- qué tablas/ciclos/codigos se vieron afectados
    conjunto_datos_suspendido BOOLEAN NOT NULL DEFAULT FALSE,
    acciones_tomadas       TEXT,
    responsable_reporte    VARCHAR(50) NOT NULL,
    estado                 VARCHAR(20) NOT NULL DEFAULT 'abierto' CHECK (estado IN ('abierto','en_investigacion','cerrado')),
    fecha_cierre           TIMESTAMP
);

-- ---------------------------------------------------------------------
-- ÍNDICES DE APOYO A TRAZABILIDAD Y AUDITORÍA
-- ---------------------------------------------------------------------
CREATE INDEX idx_respuesta_cruda_codigo_ciclo ON respuesta_cruda(codigo_seudonimo, ciclo_id);
CREATE INDEX idx_indicador_respuesta ON indicador_identificado(respuesta_id);
CREATE INDEX idx_auditoria_ciclo_tipo ON auditoria_ia(ciclo_id, tipo_prompt);
CREATE INDEX idx_nivel_derivado_respuesta ON nivel_derivado(respuesta_id);
