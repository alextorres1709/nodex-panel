# Changelog

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
