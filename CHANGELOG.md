# Changelog

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
