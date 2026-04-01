# Changelog

## v4.3.0
- **Calendario interactivo**: Rediseño completo estilo Google Calendar — toolbar con navegacion por flechas, boton "Hoy", dia actual con circulo verde, eventos con dots de color por tipo
- **Reuniones y eventos**: Nuevo modelo `CalendarEvent` con tipos reunion/evento/recordatorio, CRUD completo via AJAX, modal con chips de tipo, hora, ubicacion y color
- **Popover de dia**: Click en "+N mas" muestra popover con todos los eventos del dia
- **Loading screen**: Nueva pantalla de carga con logo NodexAI, texto animado y barra de progreso verde
- **Presencia en tiempo real**: Ver quien esta online y rastreando tiempo (`services/presence.py`)
- **SSE bus**: Notificaciones en tiempo real via Server-Sent Events (`services/sse.py`)
- **Notificaciones nativas macOS**: Alertas del sistema para tareas asignadas (`services/native_notify.py`)
- **Sync mejorado**: Intervalo reducido a 3s, auto-reload del navegador al detectar cambios
- **Dashboard**: Nuevos KPIs (clientes totales, facturas pendientes, balance), asignaciones M2M
- **Fix**: Railway deploy — archivos faltantes (config HOSTED_MODE, SSE, notificaciones nativas)
- **Fix**: Sync proteccion de timestamp — no borra datos locales al reiniciar

## v4.2.0
- **Fix**: Crash al iniciar — columnas `reminder_minutes` y `last_notified_at` faltantes en migracion

## v4.1.0
- Release intermedia con correcciones de estabilidad

## v4.0.0
- **UI**: Titlebar transparente con padding para semaforo de macOS + window collection behavior
- **Fix**: Proceso se mantiene activo para deteccion de actividad de Discord

## v3.7.0
- **UI**: Header reducido de 64px a 48px y sidebar-brand alineado con los botones de semaforo de macOS (rojo/amarillo/verde) para un diseño mas compacto
- **Fix**: Discord ya no pierde el estado de actividad cada ~30s. Se ha desactivado macOS App Nap mediante `NSProcessInfo.beginActivityWithOptions` para que el proceso no entre en suspension cuando la ventana pierde el foco

## v3.5.1
- **Fix**: El botón "Editar" en empresas dejaba de funcionar tras guardar cambios. Causa: los valores con saltos de línea o comillas (problema, solución, notas) rompían los argumentos inline de JavaScript. Solución: datos de empresa embebidos como atributo `data-company` con JSON seguro en vez de strings inline en `onclick`.

## v3.5.0
- **Sync Contactos ↔ Clientes**: Se ha añadido un botón de "Promover a Cliente" en la vista de detalle de cada Empresa (`/empresas/<id>`) para agregar automáticamente prospectos a la cartera de Clientes con su rol, datos y asociación de empresa, activando `push_change` en la red.
- **Asociación de Empresas a Proyectos**: Integración nativa habilitada; los Proyectos ahora muestran en su tabla y modal la empresa prospectada de origen.

## v3.4.1
- **Fix**: Error 500 en `/tareas` debido a fechas malformadas provenientes de la sincronización remota. Se ha añadido programación defensiva (`safe_due_date`) para manejar la conversión de tipos en el modelo, backend y frontend.

## v3.4.0
- **Fix definitivo: perdida de datos al reiniciar** — sync reescrito con estrategia MERGE (UPSERT) en vez de DELETE ALL + INSERT destructivo. Los datos locales no pusheados ya no se pierden. Se flushea la cola de pushes antes de cada pull y al cerrar la app (atexit handler). Deteccion inteligente de eliminaciones remotas.
- **Seccion de tareas rediseñada**: KPIs de estadisticas (total, pendientes, en progreso, completadas, vencidas), buscador local instantaneo, cards kanban con borde de prioridad (rojo/naranja/verde), subtareas inline con checkboxes, quick-add al pie de columnas kanban, boton completar directo, iconos SVG en badges
- **Vista lista mejorada**: barra de prioridad vertical, acciones hover, tags semanticos con iconos (proyecto, fecha, tiempo, recurrencia), indicadores overdue/hoy, progreso subtareas inline
- Responsive: stats 2-col en mobile, acciones siempre visibles en pantallas pequeñas

## v3.3.0
- **Fix critico: persistencia de datos** — todos los datos (time tracking, pagos, ingresos, proyectos, credenciales, facturas, clientes, herramientas, documentos, recursos, automatizaciones, ideas) ahora se sincronizan al remoto inmediatamente al crear/editar/eliminar. Antes se perdian al reiniciar porque el sync sobreescribia los cambios locales no empujados.
- Proyectos vinculados a empresas: nuevo campo `company_id` en proyectos, selector de empresa al crear/editar proyecto, link directo desde tarjeta de proyecto a la empresa
- Empresa detail: nueva seccion "Proyectos vinculados" con tabla de progreso, estado y presupuesto
- KPI de proyectos en vista de empresa (reemplaza el KPI de ideas)
- Sync mejorado: fix del error DATETIME en PostgreSQL al crear tablas remotas, añadidas tablas documents/resources/automations al sync
- push_change añadido a 14 route files (payments, incomes, projects, companies, credentials, invoices, clients, tools, documents, resources, automations, ideas, timetracking)

## v3.2.0
- Nueva seccion Empresas: pipeline de prospectos (escrito, responden, no responden, en negociacion, cerrado, perdido)
- Detalle de empresa con contactos y tareas sincronizadas
- Tareas creadas desde empresas aparecen tambien en /tareas
- Contactos por empresa (nombre, rol, telefono, email)
- KPIs de estado por empresa en vista de lista
- Sidebar: Empresas añadido antes de Proyectos

## v3.1.0
- Nueva pagina de detalle de proyecto con tareas, time tracking, documentos, facturas e ingresos
- Proyectos: nombre clickable para acceder al detalle
- KPIs en detalle de proyecto: tareas, horas, presupuesto, facturado/ingresado
- Gestion de contactos por proyecto (nombre, rol, telefono, email)
- Crear tareas directamente desde el detalle del proyecto
- Seccion de propuestas (documentos con categoria "propuesta")
- Seccion de ideas con votos, categorias y estados
- Modelo ProjectContact para contactos asociados a proyectos

## v3.0.0
- Todos los emojis reemplazados por iconos SVG en todo el panel
- Eliminados atajos de teclado (solo queda Cmd+K y ESC)
- Eliminado grafico de Ingresos vs Gastos del dashboard
- Añadida explicacion al heatmap de actividad de 12 semanas
- Eliminadas plantillas de tareas (Web, Landing, Bot)
- Corregido estado vacio del kanban cuando no hay tareas
- Nueva vista de equipo en Time Tracking (horas semana/mes por usuario)
- Columna de usuario añadida a la tabla de registros de tiempo
- Opcion "General" en selector de proyecto del Time Tracking
- Cowork/Mensajes eliminado de la navegacion
- Tareas: tarjetas kanban y vista lista mas grandes y legibles
- Proyectos: vista de tarjetas centradas en grid responsive (antes tabla)
- Nueva pagina de detalle de proyecto con tareas, time tracking, documentos, facturas e ingresos

## v2.3.0
- Release intermedia

## v2.2.0
- Release intermedia

## v2.0.8
- Fix: limpieza de cache de build para solucionar bug de empaquetado Jinja

## v2.0.7
- Hotfix: error de sintaxis en template base.html en boton de sync

## v2.0.6
- Fix: error 500 de autenticacion en API
- Boton de sync movido al header global

## v2.0.5
- Boton de sincronizacion manual para tareas
- Threading lock para pull_now

## v2.0.4
- Fix: sincronizacion de tareas (push_change para tareas y subtareas)

## v2.0.3
- Fix: logica del updater con cp e install script
- Polling JS para banner de actualizacion

## v2.0.2
- Fix: bug de sincronizacion de mensajes
- Cowork movido arriba en el menu lateral

## v2.0.1
- Boton de auto-instalacion de updates
- Sincronizacion de versiones
- Fix SSE y formato de fechas

## v1.1.6
- Fix: mensajes de cowork
- Seccion de Recursos añadida
- Mejoras en el updater

## v1.1.5
- Fix: persistencia del timer entre paginas via localStorage
- Indicador flotante global del timer

## v1.4.0
- Release intermedia

## v1.3.4
- Release intermedia

## v1.3.3
- Release intermedia

## v1.3.2
- Release intermedia

## v1.3.1
- Release intermedia

## v1.3.0
- SQLite local + sincronizacion en background con Railway PostgreSQL
- Navegacion 50-100x mas rapida

## v1.2.0
- Cache en memoria con TTL
- Tuning de connection pool
- Lookups de usuario cacheados

## v1.1.0
- Navegacion SPA con prefetch de todas las paginas
- Queries paralelas con ThreadPoolExecutor
- Fix de latencia en archivos estaticos

## v1.0.0
- Panel inicial: dashboard, tareas, clientes, documentos, time tracking
- Chat SSE + videollamadas (cowork)
- Seccion de ingresos
- Auto-update
- Tema dual (claro/oscuro)
- Vault de credenciales encriptado
