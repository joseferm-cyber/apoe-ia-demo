# Procedimiento de incidentes de seguridad — Proyecto APOE-IA

## Qué se considera un incidente

- Acceso no autorizado a `apoe_protegido.db` (o a la instancia protegida en producción).
- Pérdida, filtración o exposición de identidad de participantes (nombre, documento, correo, teléfono).
- Envío accidental de PII al proveedor de IA generativa (falla del gate de `core/sanitizacion.py`).
- Exportación de datos por un canal no autenticado (ej. enlace público).
- Cualquier acceso de un rol `director_revisor` a datos de identidad o a la tabla maestra de códigos.

## Pasos obligatorios

1. **Detección y contención inmediata**: suspender el conjunto de datos afectado.
   Marcar `incidente_seguridad.conjunto_datos_suspendido = TRUE` y, si aplica, revocar credenciales o pausar la app orquestadora.
2. **Registro**: crear una fila en `incidente_seguridad` (tabla en `db/ddl_research_sqlite.sql` / `ddl_research.sql`) con:
   tipo, descripción, alcance afectado (qué ciclos/códigos/tablas), responsable del reporte, fecha de detección.
3. **Evaluación de alcance**: determinar si el incidente involucró:
   - solo datos seudonimizados (menor severidad, pero igual se documenta), o
   - datos del almacén protegido / posibilidad real de reidentificación (severidad alta).
4. **Notificación**: informar al investigador principal y, si el alcance lo amerita, al comité de bioética y a la institución,
   siguiendo los plazos que exige la Ley 1581 de 2012 (Colombia) para incidentes de datos personales.
5. **Corrección**: aplicar la corrección técnica (ej. patch al gate de sanitización, rotación de credenciales,
   revisión de permisos de base de datos).
6. **Cierre**: actualizar `incidente_seguridad.estado = 'cerrado'`, `fecha_cierre`, y documentar `acciones_tomadas`.
7. **Aprendizaje**: si el incidente reveló una brecha estructural (ej. el gate de PII no cubría cierto patrón),
   actualizar `core/sanitizacion.py` y registrar el cambio de versión correspondiente.

## Responsables

- **Investigador principal**: única persona con acceso de reidentificación (`usuario_rol.acceso_reidentificacion = TRUE`).
  Responsable de decidir si se activa notificación externa.
- **Director/revisor**: reporta cualquier anomalía observada, pero no tiene acceso a identidad ni a la tabla maestra.

## Simulacro recomendado

Ejecutar al menos una vez por ciclo académico un simulacro de fuga (ej. intento deliberado de enviar un texto con nombre
propio al pipeline de IA) para verificar que `core.sanitizacion.exigir_sanitizacion_o_bloquear()` efectivamente bloquea
el envío antes de llegar a `core/ai_client.py`.
