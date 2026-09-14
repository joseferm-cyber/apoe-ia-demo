# Ficha de control del proveedor de IA generativa — Proyecto APOE-IA

> Completar y mantener actualizada esta ficha ANTES de activar `core/ai_client.py::obtener_proveedor_activo()`
> con un proveedor real. Mientras no esté completa, el sistema debe operar con `ProveedorNoConfigurado`
> (que bloquea explícitamente cualquier llamada).

| Campo | Valor |
|---|---|
| Proveedor | _(pendiente de definir — la propuesta indica que el proveedor está por definir)_ |
| Modelo y versión exacta | |
| Fecha de inicio de uso | |
| Modalidad de acceso | API directa / API vía intermediario / despliegue propio (self-hosted) |
| Política de retención de datos del proveedor | ¿Cuánto tiempo conserva el proveedor las entradas/salidas? |
| ¿Usa los datos enviados para entrenar sus modelos? | Sí / No — adjuntar cláusula contractual o de términos de servicio |
| Ubicación/régimen de procesamiento de datos | País/región donde se procesan los datos; marco legal aplicable |
| Responsable de la cuenta / contrato | Nombre, rol, correo institucional |
| Mecanismo de sanitización previa verificado | Referencia a `core/sanitizacion.py` — confirmar que el gate se ejecuta siempre antes de cualquier llamada |
| Fecha de última revisión de esta ficha | |
| Aprobación del comité de bioética para este proveedor específico | Sí / No / En trámite |

## Procedimiento de cambio de proveedor

1. Completar esta ficha para el nuevo proveedor.
2. Verificar que cumple los mismos requisitos de minimización (sección 3 del prompt de especificación): solo recibe contexto/tarea, respuesta seudonimizada e indicadores/reglas de formato de salida.
3. Implementar una nueva subclase de `AIProvider` en `core/ai_client.py` (ej. `ProveedorX`).
4. Actualizar `obtener_proveedor_activo()` para apuntar a la nueva clase.
5. Ejecutar un ciclo de prueba completo con datos ficticios antes de usar con datos reales de estudiantes.
6. Registrar el cambio en la bitácora administrativa del proyecto (no en `bitacora_ciclo`, que es específica de ciclos de seguimiento).
