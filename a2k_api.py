#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════╗
║              A2K API — Autonomous Engine v4.0               ║
║              by Hermes + DeepSeek — Modo Dios               ║
╚══════════════════════════════════════════════════════════════╝

Un solo archivo. Cero dependencias externas de configuración.
Funciona en: Railway, Render, Fly.io, VPS, tu PC.
Solo necesita la API Key de DeepSeek.

Endpoints:
  POST /api/faq           → Consulta FAQ con DeepSeek
  POST /api/product       → Registrar nuevo producto
  POST /api/order         → Confirmar pedido + WhatsApp
  POST /api/ship          → Actualizar envío + WhatsApp
  POST /api/review        → Solicitar calificación + WhatsApp
  POST /api/cart          → Recuperar carrito abandonado + WhatsApp
  POST /api/whatsapp      → Enviar mensaje WhatsApp directo
  POST /webhook/smartpay  → Webhook SmartPay / Apolo Pay
  GET  /api/logs          → Ver historial de eventos
  GET  /api/status        → Health check del sistema
  GET  /                  → Landing page mínima de la API
"""

import os, sys, json, time, hashlib, hmac
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import urllib.request

# ═══════════════════════════════════════════════
# 🎯 CONFIG (solo la API Key es obligatoria)
# ═══════════════════════════════════════════════

DEEPSEEK_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
if not DEEPSEEK_API_KEY:
    print("❌ ERROR: Debes definir DEEPSEEK_API_KEY")
    print("   export DEEPSEEK_API_KEY='sk-tu-key-aqui'")
    print("   O pasarla como variable en Railway/Render")
    sys.exit(1)

DEEPSEEK_API_URL = "https://api.deepseek.com/v1/chat/completions"
WHATSAPP_API_URL = os.environ.get("WHATSAPP_API_URL", "http://localhost:3099/send-text")
ADMIN_PHONE = os.environ.get("ADMIN_PHONE", "")
SMARTPAY_WEBHOOK_SECRET = os.environ.get("SMARTPAY_WEBHOOK_SECRET", "")
PORT = int(os.environ.get("PORT", 8000))
LOG_MAX = 500

# ─── Log en memoria (no necesita archivos) ───
_logs = []

def log_event(etype, data, status="ok"):
    _logs.append({
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "event": etype, "status": status, "data": data
    })
    global LOG_MAX
    if len(_logs) > LOG_MAX:
        _logs[:] = _logs[-LOG_MAX:]

# ─── DeepSeek FAQ ───

def deepseek_ask(system_prompt, user_msg, max_tokens=50):
    """Consulta a DeepSeek y devuelve texto plano."""
    data = json.dumps({
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_msg[:500]}
        ],
        "temperature": 0.1,
        "max_tokens": max_tokens
    }).encode()
    req = urllib.request.Request(
        DEEPSEEK_API_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {DEEPSEEK_API_KEY}",
            "Content-Type": "application/json"
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            return result["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"ERROR: {e}"

FAQ_SYSTEM = (
    "Eres un asistente de e-commerce para A2K Digital Studio. "
    "Responde preguntas sobre productos, precios, stock, envíos, pagos y garantía. "
    "Sé amable, usa emojis sutiles, sé conciso. "
    "Si no sabes algo, di que un asesor humano responderá."
)

# ─── WhatsApp ───

def send_whatsapp(phone, message):
    phone = phone.replace("+", "").strip()
    if not phone:
        return False
    data = json.dumps({"phone": phone, "message": message}).encode()
    try:
        req = urllib.request.Request(
            WHATSAPP_API_URL,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=8) as resp:
            return resp.status == 200
    except:
        return False

# ─── Respuestas predefinidas para cada categoría ───

CATEGORY_RESPONSES = {
    "stock": "🔍 ¡Sí! Ese producto está disponible en nuestro inventario. ¿Quieres que te ayude con el pedido? 📦",
    "precio": "💰 El precio lo encuentras actualizado en nuestra tienda online. ¿Te paso el enlace?",
    "envio": "🚚 Envíos: Ocumare 24-48h · Venezuela 2-5 días · Desde $3 · GRATIS >$50",
    "pago": "💳 Métodos: Transferencia · Pago Móvil · PayPal · PagueloFacil · Efectivo",
    "garantia": "🛡️ Garantía: 30 días · Cambio por defecto · Soporte WhatsApp",
    "horario": "⏰ Horarios: Lun-Vie 9AM-6PM · Sáb 9AM-1PM · Tienda online 24/7",
}

# ═══════════════════════════════════════════════
# 🧠 HANDLER HTTP
# ═══════════════════════════════════════════════

class A2KHandler(BaseHTTPRequestHandler):

    def _json(self, data, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def _html(self, html, status=200):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(html.encode())

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > 0:
            body = self.rfile.read(length)
            try:
                return json.loads(body)
            except:
                return {}
        return {}

    def do_OPTIONS(self):
        self._json({})

    def do_GET(self):
        path = urlparse(self.path).path

        if path == "/api/status" or path == "/health":
            return self._json({
                "status": "ok",
                "server": "A2K API v4",
                "deepseek": bool(DEEPSEEK_API_KEY),
                "uptime": str(datetime.utcnow() - _start_time).split(".")[0],
                "time": datetime.utcnow().isoformat() + "Z"
            })

        elif path == "/api/logs":
            limit = min(int(parse_qs(urlparse(self.path).query).get("limit", [20])[0]), 100)
            return self._json(_logs[-limit:])

        else:
            # Landing page mínima
            self._html(f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>A2K API</title>
<style>body{{background:#0a0a0a;color:#e0e0e0;font-family:monospace;padding:40px;max-width:600px;margin:auto;text-align:center}}
h1{{color:#00B4FF;font-size:2.5em}}h2{{color:#C0C0C0}}.ok{{color:#00ff88}}.endpoint{{background:#1a1a1a;padding:8px 16px;border-radius:8px;margin:8px;font-size:0.85em}}
a{{color:#00B4FF}}</style></head><body>
<h1>⚡ A2K API</h1>
<h2>Autonomous Engine v4 · Modo Dios 🔥</h2>
<p class="ok">✅ DeepSeek activo · {len(_logs)} eventos registrados</p>
<p>Uptime: {str(datetime.utcnow() - _start_time).split('.')[0]}</p>
<hr style="border-color:#333;margin:30px 0">
<div class="endpoint">POST /api/faq → Consulta FAQ con DeepSeek</div>
<div class="endpoint">POST /api/product → Registrar producto</div>
<div class="endpoint">POST /api/order → Confirmar pedido</div>
<div class="endpoint">POST /api/ship → Actualizar envío</div>
<div class="endpoint">POST /api/review → Solicitar reseña</div>
<div class="endpoint">POST /api/cart → Recuperar carrito</div>
<div class="endpoint">POST /api/whatsapp → Enviar WhatsApp</div>
<div class="endpoint">GET /api/logs → Ver eventos</div>
<div class="endpoint">GET /api/status → Health check</div>
<hr style="border-color:#333;margin:30px 0">
<p><small>A2K Digital Studio 2026 · <a href="https://a2k-landing-2026.vercel.app">Landing Page</a></small></p>
</body></html>""")

    def do_POST(self):
        path = urlparse(self.path).path
        data = self._read_body()
        log_event("request", {"path": path, "body": {k:v for k,v in data.items() if k != "message" or len(str(v)) < 50}})

        # ─── FAQ ───
        if path == "/api/faq":
            msg = data.get("message", "")
            if not msg:
                return self._json({"error": "message requerido"}, 400)

            # Clasificar con DeepSeek
            category = deepseek_ask(
                "Clasifica esta consulta de e-commerce. Responde SOLO con una palabra: "
                "stock | precio | envio | pago | garantia | horario | otro",
                msg, max_tokens=10
            ).lower().strip()

            category = category if category in CATEGORY_RESPONSES else "otro"

            # Si es stock/precio, preguntar a DeepSeek por más detalle
            if category in ("stock", "precio") and data.get("producto"):
                respuesta = deepseek_ask(
                    FAQ_SYSTEM,
                    f"Cliente pregunta: {msg}. Producto: {data['producto']}",
                    max_tokens=150
                )
            else:
                respuesta = CATEGORY_RESPONSES.get(category,
                    "😊 ¡Gracias! Un asesor te responderá pronto.")

            log_event("faq", {"categoria": category, "mensaje": msg[:60]})
            return self._json({"status": "ok", "category": category, "response": respuesta})

        # ─── PRODUCTO NUEVO ───
        elif path == "/api/product":
            prod = data.get("product", data)
            nombre = prod.get("nombre", prod.get("producto", "desconocido"))
            precio = prod.get("precio", "?")
            log_event("product", {"nombre": nombre, "precio": precio})
            return self._json({"status": "ok", "message": f"Producto registrado: {nombre}"})

        # ─── CONFIRMAR PEDIDO ───
        elif path == "/api/order":
            o = data.get("order", data)
            phone = o.get("phone", "")
            name = o.get("customer_name", o.get("nombre", "Cliente"))
            order_id = o.get("id", o.get("pedido", "?"))
            items = o.get("items", o.get("producto", ""))
            total = float(o.get("total", 0))
            msg = (f"✅ *¡Gracias por tu compra, {name}!* 🎉\n📌 Pedido: #{order_id}\n"
                   f"📦 {items}\n💰 Total: ${total:.2f}\n⏳ Te enviaremos la guía en 24-48h.\n🚀 A2K Digital Studio")
            ok = send_whatsapp(phone, msg)
            log_event("order", {"id": order_id, "whatsapp": ok})
            return self._json({"status": "ok" if ok else "error", "action": "confirmacion"})

        # ─── ACTUALIZAR ENVÍO ───
        elif path == "/api/ship":
            o = data.get("order", data)
            phone = o.get("phone", "")
            order_id = o.get("id", o.get("pedido", "?"))
            guia = o.get("tracking_code", o.get("guia", ""))
            courier = o.get("courier", "MRW")
            track_url = {"MRW": f"https://www.mrw.com.ve/tracking/{guia}"}.get(courier.upper(),
                         f"https://www.{courier}.com/tracking/{guia}")
            msg = (f"📦 *¡Tu pedido ya viaja!* 🚚\n📌 #{order_id}\n🔖 Guía: {guia}\n🔗 {track_url}\n💬 ¿Dudas? Escríbenos.")
            ok = send_whatsapp(phone, msg)
            log_event("ship", {"id": order_id, "guia": guia, "whatsapp": ok})
            return self._json({"status": "ok" if ok else "error", "action": "guia_enviada"})

        # ─── SOLICITAR RESEÑA ───
        elif path == "/api/review":
            o = data.get("order", data)
            phone = o.get("phone", "")
            name = o.get("customer_name", o.get("nombre", "Cliente"))
            prod = o.get("product_name", o.get("producto", "tu producto"))
            msg = (f"⭐ *¿Cómo fue tu experiencia, {name}?*\nRecibiste *{prod}* ✅\n"
                   f"Califícanos ⭐\n🎁 *BONO:* Usa *A2K10* para 10% OFF 🎉")
            ok = send_whatsapp(phone, msg)
            log_event("review", {"whatsapp": ok})
            return self._json({"status": "ok" if ok else "error", "action": "resena_solicitada"})

        # ─── CARRITO ABANDONADO ───
        elif path == "/api/cart":
            c = data.get("cart", data)
            phone = c.get("phone", "")
            name = c.get("customer_name", "Cliente")
            prod = c.get("product_name", c.get("producto", "un producto"))
            url = c.get("cart_url", "")
            msg = (f"👋 *¡Hola {name}!*\nVimos que dejaste *{prod}* en tu carrito 🤔\n"
                   f"🔥 *10% OFF* con *A2K10* 🎉\n👉 {url}\n¿Te ayudamos? 😊")
            ok = send_whatsapp(phone, msg)
            log_event("cart", {"whatsapp": ok})
            return self._json({"status": "ok" if ok else "error", "action": "recordatorio"})

        # ─── WHATSAPP DIRECTO ───
        elif path == "/api/whatsapp":
            phone = data.get("to", data.get("phone", ""))
            msg = data.get("message", "")
            ok = send_whatsapp(phone, msg)
            log_event("whatsapp", {"to": phone, "ok": ok})
            return self._json({"status": "ok" if ok else "error", "action": "enviado", "to": phone.replace("+", "")})

        # ─── WEBHOOK SMARTPAY / APOLO PAY ───
        elif path == "/webhook/smartpay":
            # Verificar firma con secreto whsec_
            if SMARTPAY_WEBHOOK_SECRET:
                firma = self.headers.get("X-Signature", self.headers.get("X-Webhook-Signature", ""))
                clave = SMARTPAY_WEBHOOK_SECRET.replace("whsec_", "")
                raw   = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                firma_ok = hmac.compare_digest(
                    hmac.new(clave.encode(), raw, hashlib.sha256).hexdigest(),
                    firma
                ) if firma else True
                if not firma_ok:
                    log_event("smartpay_webhook", {"error": "firma invalida"}, "error")
                    return self._json({"status": "error", "msg": "firma invalida"}, 401)
                try:
                    data = json.loads(raw)
                except Exception:
                    data = {}
            pago_id = data.get("transaction_id", data.get("id", data.get("reference", data.get("referencia", "?"))))
            monto   = data.get("amount", data.get("monto", data.get("total", "?")))
            estado  = str(data.get("status", data.get("estado", "aprobado"))).lower()
            cliente = data.get("customer_name", data.get("nombre", data.get("payer", data.get("pagador", "Cliente"))))
            log_event("smartpay_webhook", {"id": pago_id, "monto": monto, "estado": estado, "cliente": cliente})
            if ADMIN_PHONE and estado in ("approved", "aprobado", "success", "exitoso", "completed", "pagado"):
                msg_admin = (
                    f"💰 *PAGO RECIBIDO — SmartPay* ✅\n"
                    f"👤 Cliente: {cliente}\n"
                    f"💵 Monto: ${monto}\n"
                    f"🔖 Ref: {pago_id}\n"
                    f"⏰ {datetime.utcnow().strftime('%d/%m/%Y %H:%M')} UTC"
                )
                send_whatsapp(ADMIN_PHONE, msg_admin)
            return self._json({"status": "ok", "received": True})

        else:
            return self._json({"error": "endpoint no encontrado"}, 404)

    def log_message(self, format, *args):
        pass  # Silencioso


# ═══════════════════════════════════════════════
# 🚀 INICIO
# ═══════════════════════════════════════════════

_start_time = datetime.utcnow()

if __name__ == "__main__":
    print(f"""
╔═══════════════════════════════════════════════════╗
║   🚀 A2K API v4 — Autonomous Engine              ║
║   Modo Dios Activado 🔥                          ║
╠═══════════════════════════════════════════════════╣
║   DeepSeek:    {'✅' if DEEPSEEK_API_KEY else '❌'}                     ║
║   Puerto:      {PORT}                             ║
║   WhatsApp:    {WHATSAPP_API_URL}    ║
╠═══════════════════════════════════════════════════╣
║   Endpoints:                                     ║
║   POST /api/faq      → FAQ con DeepSeek          ║
║   POST /api/product  → Nuevo producto            ║
║   POST /api/order    → Confirmar pedido          ║
║   POST /api/ship     → Actualizar envío          ║
║   POST /api/review   → Solicitar reseña          ║
║   POST /api/cart     → Carrito abandonado        ║
║   POST /api/whatsapp → WhatsApp directo          ║
║   GET  /api/logs     → Historial de eventos      ║
║   GET  /api/status   → Health check              ║
╚═══════════════════════════════════════════════════╝
""")

    server = HTTPServer(("0.0.0.0", PORT), A2KHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n👋 Servidor detenido.")
        server.server_close()
