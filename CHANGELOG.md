# Changelog

## v4.5.3 — 2026-04-14
*Implementado por Alex*
- **Fix Google Calendar OAuth — redirect URI dinámico**: la app empaquetada (DMG) usa un puerto aleatorio en cada arranque, pero el `redirect_uri` estaba hardcodeado a `localhost:5001`. Google rechazaba el callback con `redirect_uri_mismatch`. Ahora `gcal.py` deriva el `redirect_uri` dinámicamente del request de Flask actual (`request.host_url + /calendario/gcal/callback`), funcionando en cualquier puerto. El callback también pasa el URI explícitamente a `exchange_code()` para que ambos extremos del flujo OAuth usen el mismo valor.
- **Acción requerida**: en Google Cloud Console → APIs → Credentials → tu OAuth Client ID → añade `http://127.0.0.1` a "Authorized redirect URIs" (Google permite cualquier puerto con esta base). También mantén `http://localhost:5001/calendario/gcal/callback` si usas el servidor dev.

## v4.5.2 — 2026-04-14
*Implementado por Alex*
- **Fix Google Calendar — error 500 al entrar en el calendario**: dos causas raíz resueltas:
  1. La tabla `google_oauth_tokens` no existía en la base de datos local (SQLite). `db.create_all()` la crea automáticamente en el arranque.
  2. `services/gcal.py` usaba la sintaxis de union types `dict | None` y `str | None` (PEP 604), que requiere Python 3.10+. El sistema corre Python 3.9 (LibreSSL), por lo que el módulo fallaba al importarse con `TypeError: unsupported operand type(s) for |`. Corregido usando `Optional[dict]` y `Optional[str]` de `typing`.

## v4.5.1 — 2026-04-09
*Implementado por Alex*
- **Sync indicator arreglado**: el badge del header ya no se ve cortado (`min-width:88px`, `white-space:nowrap`) ni se queda en amarillo casi todo el rato. La lógica nueva muestra verde mientras el último sync exitoso sea de los últimos 15 s, aunque haya otro ciclo en curso — antes el polling cogía `is_syncing=True` constantemente porque el sync corre cada 3 s y el sondeo era cada 5 s.
- **Fix 2FA invisible en webapp (HOSTED_MODE)**: la migración Postgres usaba `BOOLEAN DEFAULT 0` y PostgreSQL rechaza `0` como literal booleano, así que `users.totp_enabled` nunca se creaba en Railway y el bloque `{% if current_user.totp_enabled %}` no aparecía. Cambiado a `BOOLEAN DEFAULT FALSE` (compatible con SQLite y PG).
- **Documentos · Banner Drive descartable**: el aviso "Google Drive conectado" en `/documentos` ahora tiene una X que lo oculta (persistente vía `localStorage`).
- **Recursos conectados a Google Drive**: `/recursos` ahora sube/descarga/borra a través de Google Drive igual que `/documentos`, pero apuntando a una **carpeta separada** (`1nIZD4DtlscGvXL2Rd0got0e3YyD8oyUl`) para no mezclar logos/brand kit con contratos. Modelo `Resource` extendido con `drive_file_id`, fallback local intacto, banner de estado descartable y endpoint de preview añadido.
- **Dashboard repensado**: nuevas tarjetas accionables.
  - Bloque "Tareas atrasadas" con top 5 (proyecto, fecha de vencimiento, días tarde y CTA "Ver").
  - Bloque "Cobros pendientes" con top 5 facturas impagadas/vencidas, total acumulado y enlace.
  - Gráfica de línea "Ingresos vs Gastos (últimos 6 meses)" — se calculaba en backend pero nunca se renderizaba.
  - Bloque "Mis OKRs activos" con barra de progreso por objetivo asignado al usuario.
- **Asistente IA conversacional expuesto**: el endpoint `POST /api/ai/ask` (creado en v4.5.0 pero sin UI) ahora tiene un chat real en `/asistente` con burbujas, botones de pregunta rápida y respuestas tipo lenguaje natural sobre el contexto del panel (tareas atrasadas, proyectos, facturas, leads, resumen).

## v4.5.0 — 2026-04-09
*Implementado por Alex*
- **Comentarios y menciones en tareas**: tabla `task_comments` nueva, sección de comentarios en el modal de tarea con `@usuario` parseado por regex, notificación automática al mencionado.
- **Adjuntos por tarea e idea**: `documents.task_id` y `documents.idea_id` añadidos. El modal de tarea/idea muestra los archivos vinculados, sube vía XHR y los lista al instante. Endpoints `/api/attachments/task/<id>` y `/api/attachments/idea/<id>`.
- **Plantillas de proyecto**: nueva página `/proyectos/plantillas` con CRUD. Cada plantilla tiene su lista de tareas (`Title|priority|days`) y un botón "Usar plantilla" que clona el proyecto + tareas con offsets de deadline.
- **Snapshots de OKR**: cada vez que se actualiza el progreso de un objetivo se guarda una fila en `objective_snapshots`. El modal de edición muestra una gráfica de línea (Chart.js) con la evolución temporal del progreso. Endpoint `/api/objetivos/<oid>/snapshots`.
- **Tareas recurrentes**: al completar una tarea con `recurrence` distinto de `ninguna` (diaria/semanal/mensual/anual) se clona automáticamente la siguiente instancia con el offset correspondiente.
- **Botones de duplicar**: tareas y proyectos tienen botón "⧉ Duplicar" en kanban, lista y card grid.
- **Exportación CSV**: nuevos endpoints `/api/export/{tasks,projects,clients,invoices,time_entries}.csv` con BOM UTF-8 para Excel.
- **PDF de facturas con reportlab**: `download_pdf()` ahora genera un PDF real con cabecera, tabla de líneas, totales (subtotal/IVA/TOTAL) y notas. Fallback HTML si reportlab no está instalado.
- **Asistente IA con contexto del panel**: nuevas funciones `_build_panel_context()` + `_local_answer()` y endpoint `POST /api/ai/ask` que responde a preguntas en lenguaje natural usando los datos en vivo (proyectos activos, tareas atrasadas, facturas pendientes, leads, resumen mensual). Ya expuesto en la UI en v4.5.1.
- **2FA TOTP**: integración completa con `pyotp` — endpoints `/2fa/setup`, `/2fa/verify`, `/2fa/disable`. Configuración con QR (api.qrserver.com) en `/configuracion`. Login muestra campo de código si el usuario tiene 2FA activo.
- **Webhooks placeholder**: sección "Webhooks (PRÓXIMAMENTE)" en `/automatizaciones` para preparar la API.
- **Frontend polish**: API global `window.toast()` y `window.nxConfirm()` para confirmaciones consistentes; doble-submit protection global; modal de preview inline en documentos para el WebView.
- **Backend**: Flask-Compress (gzip activo, nivel 6, mín 500 B) y logging estructurado (`%(asctime)s [%(levelname)s] %(name)s: %(message)s`).
- **Sync extendido**: cuatro tablas nuevas (`task_comments`, `objective_snapshots`, `project_templates`, `project_template_tasks`) ahora se sincronizan con Railway.
- **Sidebar**: nuevo enlace "Asistente IA" bajo la sección Inteligencia.
- **Dependencias**: añadidos `flask-compress`, `pyotp`, `qrcode`, `reportlab` a `requirements.txt`.

## v4.4.7
*Implementado por Alex*
- **Rendimiento: editar/borrar ya no se cuelga esperando al sync.** En v4.4.6 envolvi los deletes en `sync_locked()` para fixear el race condition, pero el background pull thread mantenia ese mismo lock durante 1-3s en cada ciclo mientras leia el remoto. Cualquier delete que cayera durante un pull esperaba todo ese tiempo. Mismo problema para los `push_change_now` de tasks reminders.
- **Fix sync:** `_pull_from_remote()` ahora hace el fetch remoto (la parte lenta) SIN tocar el lock, y solo lo agarra para el merge local en SQLite (<100 ms). Tiempo lock-held reducido de 1-3s a <200ms — los deletes ya no bloquean nunca con el pull.
- **Fix push:** `push_to_remote()` ahora usa `INSERT ... ON CONFLICT DO UPDATE` en un solo statement para PostgreSQL (antes hacia SELECT + INSERT/UPDATE, 2 round-trips). Lectura local fuera del lock. Aproximadamente 40% mas rapido por push.
- **Fix /tareas:** Las stats de KPIs se calculaban cargando `Task.query.all()` entero despues de ya haber hecho la query filtrada (doble fetch). Ahora usa `GROUP BY status` y `COUNT()` — una sola query agregada en lugar de dos full-table scans.
- **Fix /timetracking:** Las stats de usuario y equipo cargaban 4+ queries con `.all()` y sumaban en Python. Ahora usa `SUM()` y `GROUP BY` — 2 queries agregadas en vez de 2×N (una por usuario). Para 5 usuarios es ~8x menos round-trips.
- **Fix dashboard:** El chart de 6 meses hacia 12 queries separadas (una por mes, una por tipo). Ahora son 2 queries con `GROUP BY extract(year/month)`. Semana personal y monthly_income tambien migradas a `SUM()` SQL.

## v4.4.6
*Implementado por Alex*
- **Fix critico race condition al borrar:** Algunos elementos volvian a aparecer despues de borrarlos (tareas, time tracking, objetivos, proyectos, empresas, clientes, ideas, recursos, herramientas, automatizaciones, facturas, credenciales, pagos, ingresos, eventos de calendario, usuarios). Causa: el delete handler hacia commit local y luego encolaba un push asincrono — pero el thread de sync pull tenia su propia ventana de 1-3s donde leia el remoto (que aun tenia la fila) y la re-insertaba en local antes de que el push llegara al remoto. Resultado: la fila desaparecia un instante y volvia a aparecer despues del siguiente pull cycle.
- **Fix:** Cada delete ahora se envuelve en `sync_locked()` y usa `push_change_now()` (sincrono) en lugar de `push_change()`. El lock impide que el background pull arranque a la vez que el delete, garantizando que el remoto se actualice antes de cualquier merge. Mismo patron que ya estabamos usando para borrar documentos en v4.4.4.
- **Fix bonus mobile API:** Los endpoints DELETE de `routes/api.py` (proyectos, tareas, clientes, time entries) no llamaban a `push_change` en absoluto — los borrados desde el APK Android nunca llegaban al remoto, asi que volvian a aparecer en cuanto el panel mac hacia un pull. Ahora todos pushean sincronamente con el lock.

## v4.4.5
*Implementado por Alex*
- **Fix critico de Google Drive**: Los archivos no se subian a Drive — los metadatos llegaban a Railway pero los bytes nunca salian del Mac. Causa: los Service Accounts de Google tienen cero cuota de almacenamiento en Drive, asi que cada upload fallaba con `storageQuotaExceeded` y el codigo hacia fallback silencioso a disco local. Google One (incluso el plan de 5TB) solo da cuota a la cuenta personal, no al Service Account.
- **Migracion a OAuth del usuario**: `services/gdrive.py` reescrito para usar el flujo "Installed App" — cada socio autoriza una vez en el navegador y el refresh token se guarda en `~/Library/Application Support/NodexAI/gdrive_token.json`. Los archivos se suben a la cuenta personal del usuario (con su cuota real) y se comparte la carpeta con el socio para acceso mutuo. Ya no depende de Service Accounts.
- **UI**: Nuevo banner en `/documentos` — muestra "Conectar con Google Drive" cuando no hay token, o "Drive conectado · Desconectar" cuando si lo hay. El boton abre el navegador del sistema, levanta un webserver local temporal en un puerto libre y captura el redirect automaticamente.
- **Fallback local**: Si el usuario no autoriza, los archivos siguen guardandose en `uploads/` como antes — nada se rompe. `init_gdrive()` es non-fatal.
- **Build**: `google-auth-oauthlib` anadido a requirements.txt y al spec de PyInstaller (hidden imports + `collect_all`) para que el flow funcione dentro del DMG.

## v4.4.4
*Implementado por Alex*
- **Fix critico de UI bloqueada**: el panel macOS se congelaba al crear/editar/borrar cualquier registro (time tracking, tareas, etc) y un triple-click acababa creando 3 filas duplicadas. Causa: `push_change()` corria sincrono dentro del request handler y competia por el `RLock` del sync con el thread de pull (que lo retiene 1-3s cada 3s). Cuando coincidian, el redirect tardaba 2-5s, el WebView se quedaba mudo y el usuario clicaba otra vez.
- **Fix**: `push_change()` ahora encola en una FIFO procesada por un worker thread dedicado (`sync-push`). Los handlers retornan instantaneamente. Para casos donde el push DEBE completarse antes del response (delete de documentos, marcado de notificaciones), se usa `push_change_now()` dentro de `sync_locked()`. El thread de pull sigue flusheando la cola antes de cada pull, asi que ningun cambio local se pierde.
- **Fix**: doble-submit protection global en `base.html` — cualquier `<form>` deshabilita su boton submit en cuanto se envia (con spinner inline) y se restaura via bfcache al volver atras. Backup defensivo aunque el bloqueo del WebView ya no deberia pasar.

## v4.4.3
*Implementado por Alex*
- **Fix**: Toasts/flash messages seguian apareciendo en la app Android — el filtro server-side por User-Agent no cubria `login.html` ni paginas con UA WebView modificada. Ahora `MainActivity` inyecta CSS+JS en cada `onPageStarted` y `onPageFinished` con un MutationObserver que oculta y elimina cualquier `.flash-message` aunque se inserte mas tarde.
- **Fix**: Notificaciones push Android no funcionaban en release builds — faltaban reglas ProGuard para `firebase_admin` (R8 minificaba las clases del FCM SDK). Ahora `proguard-rules.pro` mantiene `com.google.firebase.**` y los servicios de mensajeria.
- **Fix**: Canal de notificaciones FCM podia no existir si el usuario aun no habia abierto `MainActivity` — nueva clase `NodexApp : Application` que crea el canal en el `onCreate` del proceso, antes que cualquier Activity o Service.
- **Build**: `app/build.gradle.kts` ahora firma el release con el debug keystore (`signingConfigs.release`) para que `assembleRelease` produzca un APK instalable directamente, sin pasos manuales de `apksigner`.
- **Android**: `versionCode` 1 → 2, `versionName` 1.0.0 → 1.0.1.

## v4.4.2
*Implementado por Alex*
- **Fix**: Google Drive seguia sin subir archivos desde el DMG — `googleapiclient` necesita 594 ficheros JSON de discovery cache que PyInstaller no incluia. Ahora se usa `collect_all` para empaquetar datos, hidden imports y binarios de googleapiclient, google.auth, google.oauth2, firebase_admin y google.api_core.
- **Fix**: Mismas notificaciones de tareas saltaban cada ~10 segundos en macOS — `last_notified_at` se actualizaba localmente pero el sync pull lo sobreescribia con el valor de remote (Task no tiene `updated_at`, asi que el merge siempre considera remote como autoritativo). Ahora se hace push inmediato dentro del lock del sync.

## v4.4.1
*Implementado por Alex*
- **Fix**: Google Drive no subia archivos desde el DMG — faltaban `services.gdrive` y `googleapiclient` en el spec de PyInstaller
- **Fix**: Documentos eliminados volvian a aparecer — race condition entre delete local y sync pull, ahora se sostiene el lock del sync durante delete + push
- **Fix**: Delete de documentos tardaba mucho — limpieza de Drive y filesystem movida a background thread
- **Fix**: Modal de subir archivo no se cerraba y permitia subir el mismo archivo varias veces — boton se deshabilita al enviar, modal se cierra y muestra overlay de carga
- **Fix**: Notificaciones push FCM no llegaban cuando la app Android estaba en background — canal de notificaciones se crea ahora en `MainActivity.onCreate` antes que cualquier notificacion, icono `ic_notification` invalido eliminado
- **Fix**: Toasts/flash messages aparecian en el WebView de Android — ahora se ocultan segun User-Agent

## v4.4.0
*Implementado por Alex*
- **Google Drive compartido**: Documentos almacenados en Google Drive (1TB) via service account — upload, download y delete con fallback local. Ambos socios acceden a los mismos archivos
- **Objetivos**: Nueva seccion de objetivos a largo plazo asignables a usuarios — CRUD completo con progreso, prioridad, fecha limite y notas
- **Time Tracking editable**: Editar descripcion y proyecto en registros de tiempo existentes (timer y manuales)
- **Push notifications**: Notificaciones FCM nativas en Android al asignar tareas y objetivos
- **Fix**: SSE sync ya no cierra modales abiertos — reload diferido hasta cerrar el modal
- **Fix**: Barra gris de titlebar en macOS eliminada definitivamente

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
