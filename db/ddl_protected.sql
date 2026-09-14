-- =====================================================================
-- ALMACÉN DE DATOS PROTEGIDOS (Bloque C.2)
-- Proyecto APOE-IA — Seguimiento formativo de la derivada
-- =====================================================================
-- REGLA DE DISEÑO NO NEGOCIABLE:
--   * Este esquema debe vivir en una instancia/archivo/motor DISTINTO
--     al de investigacion.ddl_research.sql (separación física o al
--     menos lógica con credenciales y rol de acceso distintos).
--   * NINGÚN módulo de llamada a la API de IA generativa (core/ai_client.py)
--     tiene, ni debe tener nunca, cadena de conexión a este esquema.
--   * La única forma de cruzar esta base con la de investigación es por
--     codigo_seudonimo, y solo la puede ejecutar el rol
--     "investigador_principal" con fines de reidentificación autorizada
--     (ej. atención de solicitud de retiro).
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS protegido;
SET search_path TO protegido;

-- ---------------------------------------------------------------------
-- TABLA MAESTRA DE CÓDIGOS (única tabla que une identidad <-> código)
-- ---------------------------------------------------------------------
CREATE TABLE tabla_maestra_codigos (
    codigo_seudonimo       VARCHAR(20) PRIMARY KEY,   -- debe coincidir 1:1 con investigacion.participantes_seudonimos
    nombre_completo        TEXT NOT NULL,
    documento_identidad    VARCHAR(30) NOT NULL UNIQUE,
    correo_institucional   VARCHAR(120),
    telefono               VARCHAR(30),
    mayor_de_edad          BOOLEAN NOT NULL,
    nombre_representante_legal TEXT,      -- solo si mayor_de_edad = FALSE
    fecha_asignacion_codigo TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    responsable_asignacion  VARCHAR(50) NOT NULL
);

-- ---------------------------------------------------------------------
-- CONSENTIMIENTOS INFORMADOS
-- ---------------------------------------------------------------------
CREATE TABLE consentimiento (
    id                      SERIAL PRIMARY KEY,
    codigo_seudonimo        VARCHAR(20) NOT NULL REFERENCES tabla_maestra_codigos(codigo_seudonimo),
    version_formato_consentimiento VARCHAR(20) NOT NULL,
    fecha_firma             DATE NOT NULL,
    acepta_participacion    BOOLEAN NOT NULL,
    acepta_procesamiento_ia BOOLEAN NOT NULL,   -- si es FALSE => opt_out_ia = TRUE en el otro almacén
    documento_firmado_ruta  TEXT NOT NULL,      -- ruta a almacenamiento cifrado, no a la base misma
    retirado                BOOLEAN NOT NULL DEFAULT FALSE,
    fecha_retiro            DATE,
    motivo_retiro           TEXT
);

-- ---------------------------------------------------------------------
-- INSTRUMENTOS DIAGNÓSTICOS PREVIOS (ej. INS-PRERR-A) — fuente contextual
-- ---------------------------------------------------------------------
CREATE TABLE diagnostico_previo (
    id                      SERIAL PRIMARY KEY,
    codigo_seudonimo        VARCHAR(20) NOT NULL REFERENCES tabla_maestra_codigos(codigo_seudonimo),
    instrumento             VARCHAR(50) NOT NULL,   -- ej. 'INS-PRERR-A'
    fecha_aplicacion        DATE NOT NULL,
    resultados_json         TEXT NOT NULL,
    observaciones           TEXT
);

-- ---------------------------------------------------------------------
-- RETENCIÓN Y BORRADO
-- ---------------------------------------------------------------------
CREATE TABLE politica_retencion (
    id                      SERIAL PRIMARY KEY,
    codigo_seudonimo        VARCHAR(20) NOT NULL REFERENCES tabla_maestra_codigos(codigo_seudonimo),
    fecha_cierre_academico  DATE NOT NULL,
    periodo_retencion_anios SMALLINT NOT NULL DEFAULT 5,
    fecha_limite_retencion  DATE GENERATED ALWAYS AS (fecha_cierre_academico + (periodo_retencion_anios || ' years')::interval) STORED,
    estado                  VARCHAR(20) NOT NULL DEFAULT 'vigente'
                             CHECK (estado IN ('vigente','anonimizado','eliminado')),
    fecha_ejecucion_accion  DATE,
    responsable_accion      VARCHAR(50)
);
-- Nota: la expresión GENERATED ALWAYS es sintaxis PostgreSQL >= 12.
-- En SQLite, calcular fecha_limite_retencion en la capa de aplicación
-- (core/db_protected.py) en lugar de como columna generada.

-- ---------------------------------------------------------------------
-- ACCESO Y ROLES (referencia administrativa; el motor de auth real
-- vive en la capa de aplicación, no solo en la base de datos)
-- ---------------------------------------------------------------------
CREATE TABLE usuario_rol (
    usuario                 VARCHAR(50) PRIMARY KEY,
    rol                     VARCHAR(30) NOT NULL CHECK (rol IN ('investigador_principal','director_revisor')),
    acceso_reidentificacion BOOLEAN NOT NULL DEFAULT FALSE,  -- TRUE solo para investigador_principal
    fecha_alta              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Regla de negocio (aplicar también en capa de aplicación, no confiar
-- solo en el CHECK): un 'director_revisor' nunca debe tener
-- acceso_reidentificacion = TRUE.
ALTER TABLE usuario_rol
    ADD CONSTRAINT chk_rol_reidentificacion
    CHECK ( (rol = 'director_revisor' AND acceso_reidentificacion = FALSE)
            OR (rol = 'investigador_principal') );
