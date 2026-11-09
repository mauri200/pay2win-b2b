# Pay2Win paycon

Comercio agéntico con **un solo QR**: el QR es una orden de compra firmada (intención + preferencia
Pay Later + tope de gasto). Un agente LangGraph cotiza, valida elegibilidad, crea la orden con el
**PayPal Agent Toolkit** y se **pausa** para que el comprador apruebe en PayPal (Pay Later). Luego captura.

## Instalación (Windows PowerShell)
    python -m venv venv
    .\venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    copy .env.example .env      # completa PAYPAL_CLIENT_ID/SECRET (sandbox) y GROQ_API_KEY

## Ejecutar
    python list_tools.py        # verifica los nombres reales de las tools del toolkit
    python demo.py              # flujo completo en sandbox
    uvicorn api:api --reload    # opcional: API

## Flujo
leer_qr -> cotizar (tope) -> paylater -> crear_orden (toolkit) -> [INTERRUPT aprobación] -> capturar -> notificar
