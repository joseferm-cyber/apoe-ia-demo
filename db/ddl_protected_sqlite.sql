-- Versión SQLite del esquema protegido. Debe residir en un ARCHIVO
-- DISTINTO (apoe_protegido.db) del de investigación (apoe_investigacion.db),
-- nunca en el mismo archivo/proceso de conexión.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS tabla_maestra_codigos (
    codigo_seudonimo       TEXT PRIMARY KEY,
    nombre_completo        TEXT NOT NULL,
    documento_identidad    TEXT NOT NULL UNIQUE,
    correo_institucional   TEXT,
    telefono               TEXT,
    mayor_de_edad          INTEGER NOT NULL,
    nombre_representante_legal TEXT,
    fecha_asignacion_codigo TEXT NOT NULL DEFAULT (datetime('now')),
    responsable_asignacion  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS consentimiento (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_seudonimo        TEXT NOT NULL REFERENCES tabla_maestra_codigos(codigo_seudonimo),
    version_formato_consentimiento TEXT NOT NULL,
    fecha_firma             TEXT NOT NULL,
    acepta_participacion    INTEGER NOT NULL,
    acepta_procesamiento_ia INTEGER NOT NULL,
    documento_firmado_ruta  TEXT NOT NULL,
    retirado                INTEGER NOT NULL DEFAULT 0,
    fecha_retiro            TEXT,
    motivo_retiro           TEXT
);

CREATE TABLE IF NOT EXISTS diagnostico_previo (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_seudonimo        TEXT NOT NULL REFERENCES tabla_maestra_codigos(codigo_seudonimo),
    instrumento             TEXT NOT NULL,
    fecha_aplicacion        TEXT NOT NULL,
    resultados_json         TEXT NOT NULL,
    observaciones           TEXT
);

CREATE TABLE IF NOT EXISTS politica_retencion (
    id                      INTEGER PRIMARY KEY AUTOINCREMENT,
    codigo_seudonimo        TEXT NOT NULL REFERENCES tabla_maestra_codigos(codigo_seudonimo),
    fecha_cierre_academico  TEXT NOT NULL,
    periodo_retencion_anios INTEGER NOT NULL DEFAULT 5,
    fecha_limite_retencion  TEXT,  -- calculada en capa de aplicación (ver core/db_protected.py)
    estado                  TEXT NOT NULL DEFAULT 'vigente' CHECK (estado IN ('vigente','anonimizado','eliminado')),
    fecha_ejecucion_accion  TEXT,
    responsable_accion      TEXT
);

CREATE TABLE IF NOT EXISTS usuario_rol (
    usuario                 TEXT PRIMARY KEY,
    rol                     TEXT NOT NULL CHECK (rol IN ('investigador_principal','director_revisor')),
    acceso_reidentificacion INTEGER NOT NULL DEFAULT 0,
    fecha_alta              TEXT NOT NULL DEFAULT (datetime('now')),
    CHECK ( (rol = 'director_revisor' AND acceso_reidentificacion = 0) OR (rol = 'investigador_principal') )
);
