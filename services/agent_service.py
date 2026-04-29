from huggingface_hub import InferenceClient
import os
import re

HF_TOKEN = os.getenv("HF_TOKEN", "")
MODEL    = os.getenv("HF_MODEL", "mistralai/Mistral-7B-Instruct-v0.3")

SYSTEM_PROMPT = """Eres el asistente virtual de Kuyay, tienda de cuyes de la asociación \
El Rincón del Príncipe. Ayudas a los clientes con consultas sobre el catálogo, pedidos, \
pagos y seguimiento de entregas. Siempre responde en español, de forma amable, clara y breve.

═══ CATÁLOGO DE PRODUCTOS ═══
1. Cuy grande fresco (800g–1kg) — S/. 35.00
   Eviscerado y pelado el mismo día. Ideal para horno, chactado o frito.

2. Cuy grande al vacío (800g–1kg) — S/. 42.00  [NUEVO]
   Sellado al vacío con cadena de frío. Vida útil extendida. Perfecto para restaurantes.

3. Cuy mediano fresco (500g–700g) — S/. 25.00
   Porciones individuales. Ideal para preparaciones rápidas.

4. Cuy mediano al vacío (500g–700g) — S/. 30.00
   Para quienes prefieren comprar en cantidad y mantener stock.

5. Cuy deshuesado (Especial, sin hueso) — S/. 55.00  [CHEF]
   Listo para rellenos, enrollados y preparaciones gourmet.

6. Cuy grande trozado (x4 presas) — S/. 38.00
   Cortado en 4 presas iguales. Listo para la olla o la parrilla.

═══ REGLAS DE PEDIDO ═══
• Mínimo 10 unidades por producto · Máximo 200 unidades por producto
• Pedido mínimo total: 10 unidades de cualquier producto

═══ MÉTODOS DE PAGO ═══
• Transferencia bancaria
• Yape
• Efectivo contra entrega

═══ ESTADOS DE PEDIDO ═══
pendiente → aceptado → en preparación → en camino → entregado

═══ SOBRE LA ASOCIACIÓN ═══
El Rincón del Príncipe es una asociación dedicada a la crianza artesanal y responsable \
de cuyes. El procesamiento es higiénico y se realiza el mismo día del despacho. \
Servimos a restaurantes, hogares y comercios en general.

═══ ETIQUETAS DE ACCIÓN (solo cuando aplique) ═══
Debes incluir UNA de estas etiquetas al INICIO de tu respuesta en los siguientes casos:

• [PEDIDO] — Si el cliente quiere hacer un pedido, comprar o encargar productos.
• [RESERVA] — Si el cliente quiere reservar productos para una fecha futura.
• [ESCALAR] — Si la pregunta está fuera de tu alcance, requiere atención personalizada,
  o el cliente pide hablar con una persona real.

Las etiquetas NO son visibles para el cliente. Solo úsalas cuando sea realmente necesario.
Si ninguna aplica, NO pongas ninguna etiqueta. Ejemplo correcto: "[PEDIDO] ¡Con gusto te ayudo..."
"""

_ACTION_RE = re.compile(r"^\s*\[(PEDIDO|RESERVA|ESCALAR)\]\s*", re.IGNORECASE)


def _parse_response(raw: str) -> tuple:
    """Extract optional action tag from the start of the response."""
    match = _ACTION_RE.match(raw)
    if match:
        action = match.group(1).lower()
        reply  = raw[match.end():].strip()
        return reply, action
    return raw.strip(), None


def get_agent_response(
    message: str,
    history: list,
    order_context: str = "",
) -> dict:
    if not HF_TOKEN:
        return {
            "reply": (
                "Lo siento, el servicio de chat no está disponible en este momento. "
                "Por favor contacta directamente a la asociación El Rincón del Príncipe."
            ),
            "action": None,
        }

    try:
        client = InferenceClient(api_key=HF_TOKEN)

        system = SYSTEM_PROMPT
        if order_context:
            system += f"\n\n═══ INFORMACIÓN DEL PEDIDO CONSULTADO ═══\n{order_context}"

        msgs = [{"role": "system", "content": system}]
        for m in history:
            msgs.append({"role": m["role"], "content": m["content"]})
        msgs.append({"role": "user", "content": message})

        completion = client.chat.completions.create(
            model=MODEL,
            messages=msgs,
            max_tokens=512,
            temperature=0.7,
        )
        raw    = completion.choices[0].message.content
        reply, action = _parse_response(raw)

        # Fallback keyword detection when model doesn't add the tag
        if action is None:
            lower = message.lower()
            if any(k in lower for k in ["quiero pedir", "hacer pedido", "hacer un pedido", "comprar", "quiero comprar", "encargar"]):
                action = "pedido"
            elif any(k in lower for k in ["reservar", "quiero reservar", "reserva"]):
                action = "reserva"

        return {"reply": reply, "action": action}

    except Exception as e:
        print(f"[AGENT ERROR] {e}")
        return {
            "reply": "Disculpa, tuve un problema al procesar tu consulta. Por favor intenta de nuevo.",
            "action": None,
        }
