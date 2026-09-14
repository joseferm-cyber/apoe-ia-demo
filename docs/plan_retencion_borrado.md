# Plan de retención y borrado — Proyecto APOE-IA

## Períodos por defecto

- **Retención estándar**: 5 años desde la fecha de cierre académico del curso, salvo que el comité de
  bioética determine un período distinto (`protegido.politica_retencion.periodo_retencion_anios`).
- **Ventana de retiro del participante**: mientras sea técnicamente posible reidentificar el registro
  (es decir, mientras `tabla_maestra_codigos` conserve la fila correspondiente), el participante puede
  solicitar su retiro. Una vez anonimizado el código de forma irreversible, el retiro selectivo deja de
  ser técnicamente posible y debe informársele esto al participante en el proceso de consentimiento.

## Acciones al vencer el plazo

1. Verificar `politica_retencion.fecha_limite_retencion` (calculada en `core/db_protected.py` a partir de
   `fecha_cierre_academico + periodo_retencion_anios`).
2. **Anonimización definitiva** (opción por defecto): eliminar la fila de `tabla_maestra_codigos` y de
   `consentimiento` asociada al código, dejando intacta la base de investigación (que ya es seudonimizada
   y no permite, por sí sola, reidentificar a nadie).
3. **Eliminación segura** (si el protocolo o el comité lo exige): eliminar también los registros
   correspondientes en la base de investigación (`respuesta_cruda`, `indicador_identificado`,
   `nivel_derivado`, `auditoria_ia`) para ese `codigo_seudonimo`, documentando la acción.
4. Actualizar `politica_retencion.estado` a `'anonimizado'` o `'eliminado'`, con `fecha_ejecucion_accion`
   y `responsable_accion`.

## Retiro anticipado de un participante

1. Registrar la solicitud en `consentimiento.retirado = TRUE`, `fecha_retiro`, `motivo_retiro`.
2. Marcar `investigacion.participantes_seudonimos.estado_participacion = 'retirado'`.
3. Decidir, según lo pactado en el consentimiento, si los datos ya recolectados se conservan
   agregados/anonimizados o se eliminan; documentar la decisión.
4. Nunca se debe eliminar únicamente la fila de `tabla_maestra_codigos` sin dejar constancia en
   `politica_retencion`, para mantener trazabilidad de que la anonimización fue intencional y autorizada.

## Verificación periódica

Ejecutar trimestralmente una consulta sobre `politica_retencion` para identificar registros cuya
`fecha_limite_retencion` ya se cumplió y no han sido procesados, y escalar al investigador principal.
