# Pay2Win B2B · equipo de agentes para comercio delegado

Módulo **independiente** (no modifica el flujo B2C existente). El comprador
solo delega un monto de dinero en un **QR firmado**; un agente supervisor
planifica y reparte el trabajo entre subagentes especializados que compran,
calculan aduanas, cotizan logística, validan compliance, asignan presupuesto y
pagan.

```
QR mandate (JWT firmado: objetivo + presupuesto + tope por ítem + subagentes)
  -> supervisor
     -> procurement   (Channel3: productos + stock, o catálogo local)
     -> customs       (HS codes, aranceles, impuestos, permisos)
     -> logistics     (transporte consolidado, costo, ETA, DDP)
     -> compliance    (sanciones, KYC, mercancía restringida)
     -> treasury      (asignación, fees, saldo, calendario de pagos)
     -> payments      (orden PayPal sandbox / simulación)
  -> INTERRUPT (aprobación humana en PayPal)
  -> capture -> notify
```

## Soluciones B2B incluidas

- **Delegación por presupuesto**: el usuario fija el monto total y el tope por
  ítem; el equipo nunca puede excederlos (guardrail en procurement y treasury).
- **Compra por chat**: `/api/b2b/chat` interpreta lenguaje natural (Groq) y
  prepara el mandato/QR.
- **Stock real con Channel3**: búsqueda en modo `agentic` + disponibilidad de
  ofertas; si no hay `CHANNEL3_API_KEY` usa un catálogo mayorista local.
- **Landed cost**: aranceles, impuestos de importación, corretaje y flete en un
  solo total antes de pagar.
- **Logística consolidada**: elige courier/air/ocean y aplica descuento por
  consolidar varios proveedores.
- **Compliance**: screening de sanciones por proveedor/país y permisos para
  mercancía restringida (p. ej. baterías de litio).
- **Tesorería**: calendario de pagos (Pay Later en 4 cuotas o anticipo/saldo) y
  saldo restante del presupuesto.
- **Pago PayPal con aprobación humana**: misma lógica de interrupt + capture del
  flujo original; simulación automática si faltan credenciales. La captura usa
  la API REST directamente, así PayPal genera sus **Sandbox email
  notifications** (visibles en Developer Dashboard → Notifications).
- **Auditoría completa**: cada subagente deja un rastro consultable en el
  dashboard.
- **Dashboard AG Grid**: control de pagos, KPIs, filtros, export CSV y detalle
  del equipo por delegación.

## Estructura

```
b2b/
  api.py               FastAPI (puerto 8001)
  team.py              supervisor LangGraph + interrupt/capture
  mandate.py           QR/JWT firmado (misma raíz de confianza que app/qr.py)
  channel3.py          proveedor Channel3 + catálogo local de respaldo
  ledger.py            ledger en memoria para el dashboard
  webhooks.py          verificación de firma y eventos PayPal
  subagents/
    procurement.py     compra + stock
    customs.py         aduanas
    logistics.py       logística
    compliance.py      sanciones/permisos
    treasury.py        presupuesto/pagos
    payments.py        PayPal sandbox / simulación
  dashboard/           React + AG Grid (v36, AllCommunityModule)
  static/index.html    UI de respaldo sin build
  demo.py              demo CLI
```

## Ejecutar

```powershell
# Desde la raíz del repo (reutiliza el venv y el .env existentes)
.\venv\Scripts\Activate.ps1
pip install -r b2b\requirements.txt

python -m b2b.demo
uvicorn b2b.api:api --reload --port 8001
```

- UI de respaldo / dashboard construido: http://localhost:8001/
- Swagger: http://localhost:8001/docs

Dashboard React (AG Grid):

```powershell
cd b2b\dashboard
npm install
npm run dev      # http://localhost:5174 (proxy /api -> :8001)
npm run build    # genera dist/, servido por b2b/api.py
```

## Variables de entorno

Se reutilizan `QR_SECRET`, `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`,
`GROQ_MODEL` y `GROQ_API_KEY` del `.env` raíz. Opcionales:

```ini
CHANNEL3_API_KEY=          # si falta, catálogo local de respaldo
CHANNEL3_MODE=agentic      # default | agentic | keyword
B2B_CURRENCY=USD
B2B_MAX_DELEGATION=250000
B2B_MANDATE_TTL=900
B2B_PAYMENT_FEE_RATE=0.029
B2B_BROKERAGE_FEE=45
B2B_VAT_RATE=0.16
PAYPAL_API_BASE=https://api-m.sandbox.paypal.com
PAYPAL_WEBHOOK_ID=         # si falta, los eventos se aceptan sin verificar (demo)
B2B_NOTIFY_WEBHOOK_URL=    # opcional: Slack-compatible incoming webhook
```

`paypal` aparece como `simulated` en `/api/b2b/health` cuando no hay
credenciales; el flujo completo sigue funcionando en modo demo.

### Notificaciones PayPal (webhooks)

1. Expón la API con una URL pública (ngrok, Cloudflare Tunnel, etc.).
2. En PayPal Developer Dashboard → tu app → **Webhooks**, añade:
   `https://<host-publico>/api/b2b/paypal/webhook`
3. Suscríbete a `CHECKOUT.ORDER.APPROVED`,
   `PAYMENT.CAPTURE.COMPLETED` y `PAYMENT.CAPTURE.DENIED`.
4. Copia el **Webhook ID** a `PAYPAL_WEBHOOK_ID` y reinicia la API.

Con el ID configurado, cada evento se valida contra
`/v1/notifications/verify-webhook-signature` y se rechaza con `400` si la firma
no es válida. Los eventos aparecen en el detalle de la delegación y en
`GET /api/b2b/paypal/events`. Si defines `B2B_NOTIFY_WEBHOOK_URL`, también se
reenvía un mensaje corto (formato Slack) a ese webhook.

### Sandbox email notifications

PayPal Sandbox no envía emails reales: los guarda en **Developer Dashboard →
Notifications** (`https://developer.paypal.com/dashboard/notifications`).
Para que aparezca una notificación de pago hacen falta dos cosas:

1. La orden debe ser real (`payment_mode = paypal_sandbox`, no `simulated`).
2. La orden debe estar **capturada**. Crear la orden no genera notificación.

El dashboard B2B incluye el link **Sandbox email notifications** en el detalle.
Además, `POST /api/b2b/approve/{tid}` comprueba el estado real de la orden
antes de reanudar el grafo: si todavía está `CREATED`/`PAYER_ACTION_REQUIRED`
devuelve `409` pidiendo aprobar primero en PayPal, y solo captura cuando está
`APPROVED`. La captura se hace con `POST /v2/checkout/orders/{id}/capture`
para que PayPal emita la notificación de forma fiable.

## API

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/api/b2b/health` | estado de Channel3, PayPal, Groq y subagentes |
| GET | `/api/b2b/catalog` | snapshot del catálogo mayorista local |
| GET | `/api/b2b/qr` | crea mandato + QR (`objective`, `budget`, `per_item_cap`, `financing`, `scope`) |
| POST | `/api/b2b/chat` | compra por chat → mandato/QR |
| POST | `/api/b2b/start` | ejecuta el equipo hasta la aprobación |
| POST | `/api/b2b/approve/{tid}` | reanuda con `{ "approved": true }` y captura |
| GET | `/api/b2b/orders` | ledger para AG Grid |
| GET | `/api/b2b/orders/{tid}` | detalle de una delegación |
| POST | `/api/b2b/paypal/webhook` | recibe y verifica eventos de PayPal |
| GET | `/api/b2b/paypal/events` | últimos eventos PayPal recibidos |
| GET | `/api/b2b/paypal/order/{id}` | estado real de una orden PayPal |

### Ejemplo rápido

```bash
curl "http://localhost:8001/api/b2b/qr?objective=Compra%2020%20laptops&budget=50000&per_item_cap=1500"
# copia el token y ejecuta:
curl -X POST http://localhost:8001/api/b2b/start -H "Content-Type: application/json" \
  -d '{"token":"<TOKEN>"}'
curl -X POST http://localhost:8001/api/b2b/approve/<THREAD_ID> \
  -H "Content-Type: application/json" -d '{"approved":true}'
```

## Añadir otro subagente

1. Crea `b2b/subagents/mi_agente.py` con `def run(state: dict) -> dict`.
2. Regístralo en `b2b/subagents/__init__.py` (`REGISTRY`).
3. Añade el nombre a `ALL_SUBAGENTS` en `b2b/config.py` y al pipeline en
   `b2b/team.py`. El supervisor lo despachará automáticamente.
