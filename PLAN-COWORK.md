# Plan: Seccion Cowork — NodexAI Panel

## Objetivo
Añadir una seccion de coworking dentro del panel que permita colaboracion en tiempo real entre los miembros del equipo: videollamadas, proyectos compartidos, chat y documentos.

---

## Modulos

### 1. Videollamadas
- **Tecnologia**: WebRTC via Jitsi Meet (self-hosted o embebido)
- **Implementacion**:
  - Iframe de Jitsi Meet embebido en el panel (sin necesidad de servidor propio de video)
  - Crear sala con nombre unico por proyecto o ad-hoc
  - Boton "Iniciar llamada" que genera sala y comparte link automaticamente
  - Historial de llamadas (fecha, duracion, participantes)
- **Alternativa avanzada**: Daily.co API (videollamadas embebidas, free tier 10k min/mes)

### 2. Proyectos compartidos (Workspace)
- **Vista de proyecto mejorada**:
  - Panel Kanban con columnas (Por hacer, En progreso, Revision, Completado)
  - Drag & drop de tareas entre columnas
  - Asignacion de tareas a miembros en tiempo real
  - Comentarios en tareas
  - Archivos adjuntos por tarea (subida a almacenamiento local o S3)
- **Tecnologia**:
  - Backend: Flask + SQLAlchemy (ya existente)
  - Frontend: Vanilla JS con drag & drop nativo (HTML5 API)
  - Tiempo real: Server-Sent Events (SSE) para notificaciones push sin WebSockets

### 3. Chat en tiempo real
- **Funcionalidades**:
  - Chat general del equipo
  - Chat por proyecto
  - Mensajes directos entre usuarios
  - Notificaciones de mencion (@usuario)
  - Enviar archivos/imagenes
- **Tecnologia**:
  - Server-Sent Events (SSE) para recibir mensajes en tiempo real
  - POST requests para enviar mensajes
  - Almacenamiento en PostgreSQL (tabla `messages`)
- **Modelo de datos**:
  ```
  Message: id, sender_id, channel (general/project_id/dm), content,
           file_url, created_at
  ```

### 4. Documentos compartidos
- **Funcionalidades**:
  - Crear notas/documentos por proyecto
  - Editor de texto enriquecido (Markdown)
  - Historial de versiones
- **Tecnologia**: Editor Markdown simple (textarea + preview)
- **Modelo de datos**:
  ```
  Document: id, title, content, project_id, created_by, updated_at
  ```

---

## Fases de implementacion

### Fase 1 — Base (1-2 semanas)
- [ ] Modelo `Message` + ruta `/cowork`
- [ ] Chat general del equipo con SSE
- [ ] Vista basica de cowork con sidebar de canales

### Fase 2 — Videollamadas (3-5 dias)
- [ ] Integracion Jitsi Meet embebido
- [ ] Crear/unirse a salas por proyecto
- [ ] Historial de llamadas

### Fase 3 — Workspace mejorado (1-2 semanas)
- [ ] Vista Kanban de tareas por proyecto
- [ ] Drag & drop entre columnas
- [ ] Comentarios en tareas
- [ ] Notificaciones SSE de cambios

### Fase 4 — Documentos (1 semana)
- [ ] Modelo `Document`
- [ ] Editor Markdown con preview
- [ ] Documentos vinculados a proyectos

---

## Estructura de archivos nuevos

```
routes/cowork.py          — Blueprint con rutas de cowork
templates/cowork.html     — Vista principal con chat + sidebar
templates/cowork_call.html — Vista de videollamada embebida
models.py                 — Añadir Message, Document
static/js/cowork.js       — Chat SSE, drag & drop kanban
```

---

## Sidebar del panel

Añadir en la seccion "Trabajo":
```
Cowork  (icono: monitor con personas)
```

---

## Dependencias adicionales
- Ninguna libreria nueva necesaria para chat SSE
- Jitsi Meet se carga via iframe (CDN externo)
- Opcional: `python-markdown` para renderizar documentos

---

## Notas
- SSE es preferible a WebSockets para este caso: mas simple, funciona con Flask sin extensiones, compatible con el DMG (pywebview)
- Jitsi Meet es gratuito y se puede embeber sin registro
- El chat reemplazaria la necesidad de Discord para comunicacion interna
- Todo se almacena en la misma base de datos PostgreSQL (compartida) o SQLite (DMG local)
