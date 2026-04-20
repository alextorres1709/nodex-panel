# n8n — Automatización CRM NodexAI Panel

Workflow: [`company_email_workflow.json`](company_email_workflow.json)

Dos flujos paralelos dentro del mismo workflow:

1. **Outbox de emails (cada 5 min)** — envía los emails que encolas desde el panel.
2. **Recordatorios de seguimiento (cada hora)** — avisa por Slack si una empresa con estado "llamada_agendada" / "interesado" / "negociación" lleva >=3 días sin interacción.

---

## Flujo 1: enviar emails encolados

```
Cron 5 min
  → GET /api/companies/outbox          (Bearer <API_TOKEN>)
  → Split por email
  → Gmail OAuth2                        (o SMTP — intercambiable)
  → POST /api/companies/mark-sent/<id>  (Bearer)
```

**Qué hace el panel**:

1. En `/empresas/<id>` haces clic en **"Enviar email"**.
2. Eliges contacto + plantilla Apollo-style. El panel renderiza `{empresa}`, `{contacto}` y `{nombre_remitente}` en subject/body.
3. Se crea una `CompanyInteraction` con `type="email"`, `status="queued"`.
4. n8n la recoge, envía, y el panel la marca como `sent`.

El timeline en la ficha muestra el estado (**en cola / enviado / fallido**) con el cuerpo completo.

## Flujo 2: recordatorios de seguimiento

```
Cron 1 h
  → GET /api/companies/due-reminders   (Bearer)
  → Split por empresa
  → Slack channel
```

Devuelve empresas en pipeline activo (`llamada_agendada`, `interesado`, `negociacion`) sin ninguna interacción registrada en los últimos 3 días. Evita que se queden olvidadas.

---

## Variables de entorno necesarias en n8n

| Variable | Para qué | Ejemplo |
|---|---|---|
| `NODEX_PANEL_URL` | URL pública del panel Flask | `https://panel.nodexai.es` |
| `NODEX_PANEL_API_TOKEN` | `api_token` de un usuario del panel (ver `/configuracion`) | `abc123...` |
| `SLACK_SALES_CHANNEL` | Canal Slack (opcional, default `#sales`) | `#ventas` |

**Credenciales a reemplazar en el import**:
- `REPLACE_WITH_GMAIL_CREDENTIAL_ID` → credencial Gmail OAuth2 en n8n
- `REPLACE_WITH_SLACK_CREDENTIAL_ID` → credencial Slack en n8n

---

## Pasos para activar

1. **Crear/obtener el API token** de un usuario admin en el panel:
   - En el panel → Configuración → Regenerar API token (o usa el ya existente).
2. **Importar el workflow** en n8n (`company_email_workflow.json`).
3. **Asignar credenciales** (Gmail + Slack).
4. **Configurar variables de entorno** en n8n (tabla de arriba).
5. **Activar el workflow** (toggle "Active").

## Cómo verificar que funciona

1. En el panel, abre una empresa que tenga al menos un contacto con email.
2. Pulsa **"Enviar email"**, elige una plantilla, envía.
3. En la ficha, verás la interacción con badge **"En cola"**.
4. En ≤5 min el email llega al destinatario y el badge pasa a **"Enviado"** (confirmado por n8n llamando a `/mark-sent`).
5. Si ves el badge rojo **"Fallido"** o no cambia, mira las ejecuciones del workflow en n8n.

## Notas de diseño

- **Las plantillas viven en el panel**, no en n8n. Si editas `/plantillas-email`, el próximo email encolado usa la nueva versión automáticamente.
- **n8n no renderiza variables** — recibe el subject/body ya sustituidos. Esto evita inconsistencias entre lo que ves en el panel y lo que llega al buzón del cliente.
- **Endpoint idempotente**: `mark-sent` se puede llamar varias veces sin duplicar envíos (el panel solo actualiza `status` y `sent_at`).
- **Ventana de outbox**: solo se sirven emails encolados en los **últimos 10 minutos**. Un email que lleva encolado >10 min se considera perdido — crea uno nuevo.
