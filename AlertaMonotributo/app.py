import os
import sqlite3
import json
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, request, redirect, render_template_string, jsonify, session
import requests

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'cambia-esto-por-algo-secreto')

MERCADOPAGO_ACCESS_TOKEN = os.environ.get('MERCADOPAGO_ACCESS_TOKEN', '')
BASE_URL = os.environ.get('BASE_URL', 'http://localhost:5000')

DB_PATH = 'alertamonotributo.db'

# ============================================================
# CATEGORÍAS MONOTRIBUTO ARCA 2026 (Febrero - Julio 2026)
# ============================================================
CATEGORIAS = {
    'A': {'tope': 10277988.13, 'cuota_servicios': 42386.74, 'cuota_bienes': 42386.74},
    'B': {'tope': 15058447.71, 'cuota_servicios': 48250.78, 'cuota_bienes': 48250.78},
    'C': {'tope': 21113696.52, 'cuota_servicios': 56501.85, 'cuota_bienes': 55227.06},
    'D': {'tope': 26212853.42, 'cuota_servicios': 72414.10, 'cuota_bienes': 70661.26},
    'E': {'tope': 30833964.37, 'cuota_servicios': 92568.35, 'cuota_bienes': 92658.35},
    'F': {'tope': 38642048.36, 'cuota_servicios': 111198.27, 'cuota_bienes': 111198.27},
    'G': {'tope': 46211109.37, 'cuota_servicios': 135198.34, 'cuota_bienes': 135198.34},
    'H': {'tope': 70113407.33, 'cuota_servicios': 272063.40, 'cuota_bienes': 272063.40},
    'I': {'tope': 78479211.62, 'cuota_servicios': 460512.05, 'cuota_bienes': 460512.05},
    'J': {'tope': 89872640.30, 'cuota_servicios': 497059.41, 'cuota_bienes': 497059.41},
    'K': {'tope': 108357084.05, 'cuota_servicios': 600879.51, 'cuota_bienes': 600879.51},
}

# ============================================================
# BASE DE DATOS
# ============================================================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        email TEXT UNIQUE NOT NULL,
        pro INTEGER DEFAULT 0,
        fecha_vencimiento TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )''')
    conn.commit()
    conn.close()

init_db()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

# ============================================================
# DECORADOR requires_pro
# ============================================================
def requires_pro(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        email = session.get('email')
        if not email:
            return redirect('/pagar-pro')
        conn = get_db()
        user = conn.execute('SELECT * FROM usuarios WHERE email = ?', (email,)).fetchone()
        conn.close()
        if not user or not user['pro']:
            return redirect('/pagar-pro')
        if user['fecha_vencimiento']:
            venc = datetime.fromisoformat(user['fecha_vencimiento'])
            if venc < datetime.now():
                return redirect('/pagar-pro')
        return f(*args, **kwargs)
    return decorated

# ============================================================
# LÓGICA DEL SEMÁFORO
# ============================================================
def calcular_semaforo(categoria_actual, facturacion_12m):
    cat = CATEGORIAS.get(categoria_actual.upper())
    if not cat:
        return None
    tope = cat['tope']
    porcentaje = (facturacion_12m / tope) * 100
    falta = tope - facturacion_12m

    if porcentaje < 70:
        color = 'verde'
        mensaje = '✅ Estás en ZONA VERDE. Tranquilo, tenés margen.'
        detalle = f'Usaste el {porcentaje:.1f}% de tu tope. Te faltan ${falta:,.2f} para llegar al límite.'
    elif porcentaje < 90:
        color = 'amarillo'
        mensaje = '⚠️ ZONA AMARILLA. Atención, te estás acercando al límite.'
        detalle = f'Usaste el {porcentaje:.1f}% de tu tope. Te faltan ${falta:,.2f}. Cuidado con las próximas facturas.'
    else:
        color = 'rojo'
        mensaje = '🚨 ZONA ROJA. ¡PELIGRO! Podés ser recategorizado de oficio o excluido.'
        detalle = f'Usaste el {porcentaje:.1f}% de tu tope. Solo te faltan ${falta:,.2f} para pasarte.'

    siguiente_cat = None
    for letra in ['A','B','C','D','E','F','G','H','I','J','K']:
        if CATEGORIAS[letra]['tope'] > tope:
            siguiente_cat = letra
            break

    extra = ''
    if siguiente_cat:
        cuota_actual = cat['cuota_servicios']
        cuota_siguiente = CATEGORIAS[siguiente_cat]['cuota_servicios']
        diferencia = cuota_siguiente - cuota_actual
        extra = f'Si te recategorizan a {siguiente_cat}, tu cuota pasaría de ${cuota_actual:,.2f} a ${cuota_siguiente:,.2f} (${diferencia:,.2f} más por mes).'

    return {
        'color': color,
        'porcentaje': round(porcentaje, 2),
        'falta': round(falta, 2),
        'mensaje': mensaje,
        'detalle': detalle,
        'extra': extra,
        'tope': tope,
        'categoria': categoria_actual.upper()
    }

# ============================================================
# PLANTILLA HTML PRINCIPAL
# ============================================================
PLANTILLA_PRINCIPAL = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="description" content="Calculadora Alerta Monotributo 2026. Controlá cuánto te falta para la recategorización de oficio de ARCA. Semáforo fiscal gratis.">
    <meta name="keywords" content="control gastos monotributo, alerta recategorización, cuánto me falta para recategorización, monotributo 2026, ARCA, AFIP">
    <title>Alerta Monotributo 2026 - Calculadora Semáforo Fiscal ARCA</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; min-height: 100vh; padding: 20px; }
        .container { max-width: 700px; margin: 0 auto; }
        h1 { font-size: 1.6rem; text-align: center; margin-bottom: 10px; color: #38bdf8; line-height: 1.3; }
        .subtitle { text-align: center; color: #94a3b8; margin-bottom: 30px; font-size: 0.95rem; }
        .card { background: #1e293b; border-radius: 16px; padding: 25px; margin-bottom: 20px; border: 1px solid #334155; }
        label { display: block; margin-bottom: 6px; font-weight: 600; color: #cbd5e1; font-size: 0.9rem; }
        select, input[type="number"], input[type="email"] { width: 100%; padding: 14px; border-radius: 10px; border: 1px solid #475569; background: #0f172a; color: #e2e8f0; font-size: 1rem; margin-bottom: 18px; }
        select:focus, input:focus { outline: none; border-color: #38bdf8; }
        button { width: 100%; padding: 16px; border-radius: 12px; border: none; background: #38bdf8; color: #0f172a; font-size: 1.1rem; font-weight: 700; cursor: pointer; transition: background 0.2s; }
        button:hover { background: #7dd3fc; }
        .semaforo { text-align: center; padding: 30px 20px; border-radius: 16px; margin-top: 20px; }
        .semaforo.verde { background: #052e16; border: 2px solid #22c55e; }
        .semaforo.amarillo { background: #422006; border: 2px solid #eab308; }
        .semaforo.rojo { background: #450a0a; border: 2px solid #ef4444; }
        .semaforo .emoji { font-size: 5rem; margin-bottom: 10px; }
        .semaforo .porcentaje { font-size: 3rem; font-weight: 800; margin-bottom: 10px; }
        .semaforo.verde .porcentaje { color: #22c55e; }
        .semaforo.amarillo .porcentaje { color: #eab308; }
        .semaforo.rojo .porcentaje { color: #ef4444; }
        .semaforo .mensaje { font-size: 1.2rem; font-weight: 700; margin-bottom: 8px; }
        .semaforo .detalle { font-size: 0.95rem; color: #94a3b8; line-height: 1.5; }
        .pro-box { background: linear-gradient(135deg, #1e3a5f, #2d1b69); border: 2px solid #a78bfa; border-radius: 16px; padding: 25px; text-align: center; margin-top: 20px; }
        .pro-box h2 { color: #a78bfa; margin-bottom: 10px; }
        .pro-box p { color: #c4b5fd; margin-bottom: 15px; font-size: 0.95rem; }
        .pro-box .precio { font-size: 2rem; font-weight: 800; color: #fff; margin-bottom: 15px; }
        .pro-box button { background: #a78bfa; color: #1e1b4b; }
        .pro-box button:hover { background: #c4b5fd; }
        footer { text-align: center; padding: 30px 10px; color: #64748b; font-size: 0.8rem; }
        footer a { color: #38bdf8; text-decoration: none; margin: 0 8px; }
        .explicacion { background: #1e293b; border-radius: 16px; padding: 25px; margin-top: 20px; border: 1px solid #334155; }
        .explicacion h2 { color: #38bdf8; margin-bottom: 12px; font-size: 1.2rem; }
        .explicacion p { color: #94a3b8; line-height: 1.7; margin-bottom: 10px; font-size: 0.9rem; }
        .explicacion ul { color: #94a3b8; line-height: 1.7; padding-left: 20px; font-size: 0.9rem; }
        .error { color: #ef4444; text-align: center; margin-top: 15px; }
        @media (max-width: 500px) {
            h1 { font-size: 1.3rem; }
            .semaforo .emoji { font-size: 3.5rem; }
            .semaforo .porcentaje { font-size: 2.2rem; }
            .card { padding: 18px; }
        }
    </style>
</head>
<body>
<div class="container">
    <h1>Calculadora Alerta Monotributo 2026 - Evitá la recategorización de oficio de ARCA</h1>
    <p class="subtitle">Ingresá tu categoría actual y cuánto facturaste en los últimos 12 meses. Te decimos si estás en zona verde, amarilla o roja.</p>

    <div class="card">
        <form method="POST" action="/">
            <label for="categoria">Tu categoría actual de Monotributo:</label>
            <select name="categoria" id="categoria" required>
                <option value="">-- Elegí tu categoría --</option>
                {% for letra in categorias %}
                <option value="{{ letra }}" {% if categoria_actual == letra %}selected{% endif %}>Categoría {{ letra }} - Tope: ${{ "{:,.2f}".format(categorias[letra]['tope']) }}</option>
                {% endfor %}
            </select>

            <label for="facturacion">¿Cuánto facturaste en los últimos 12 meses? ($):</label>
            <input type="number" name="facturacion" id="facturacion" step="0.01" min="0" placeholder="Ej: 8500000" value="{{ facturacion or '' }}" required>

            <button type="submit">🔍 Calcular mi semáforo fiscal</button>
        </form>

        {% if resultado %}
        <div class="semaforo {{ resultado.color }}">
            <div class="emoji">
                {% if resultado.color == 'verde' %}🟢{% elif resultado.color == 'amarillo' %}🟡{% else %}🔴{% endif %}
            </div>
            <div class="porcentaje">{{ resultado.porcentaje }}%</div>
            <div class="mensaje">{{ resultado.mensaje }}</div>
            <div class="detalle">{{ resultado.detalle }}</div>
            {% if resultado.extra %}
            <div class="detalle" style="margin-top: 12px; padding-top: 12px; border-top: 1px solid rgba(255,255,255,0.1);">{{ resultado.extra }}</div>
            {% endif %}
        </div>
        {% endif %}

        {% if error %}
        <p class="error">{{ error }}</p>
        {% endif %}
    </div>

    <div class="pro-box">
        <h2>⭐ Versión Pro</h2>
        <p>Alertas automáticas, seguimiento mensual, historial de facturación y más.</p>
        <div class="precio">$7.500 <span style="font-size: 1rem; font-weight: 400;">ARS/mes</span></div>
        <form method="GET" action="/pagar-pro">
            <button type="submit">Suscribirme a Pro</button>
        </form>
    </div>

    <div class="explicacion">
        <h2>¿Cómo funciona el semáforo fiscal del Monotributo?</h2>
        <p>El Monotributo en Argentina tiene categorías (de la A a la K) con topes de facturación anual. Si tus ingresos brutos de los últimos 12 meses superan el tope de tu categoría, ARCA (ex AFIP) puede <strong>recategorizarte de oficio</strong> o incluso <strong>excluirte del régimen</strong>, obligándote a pasar al Régimen General.</p>
        <p>Este semáforo te ayuda a anticiparte:</p>
        <ul>
            <li><strong>🟢 Verde (menos del 70%):</strong> Estás tranquilo. Tenés margen para seguir facturando.</li>
            <li><strong>🟡 Amarillo (70% a 90%):</strong> Atención. Te estás acercando al límite. Empezá a planificar.</li>
            <li><strong>🔴 Rojo (más del 90%):</strong> Peligro. Podés ser recategorizado de oficio. Consultá con tu contador urgente.</li>
        </ul>
        <p>Los topes que usamos son los vigentes de <strong>ARCA para Febrero-Julio 2026</strong>. Recordá que se actualizan semestralmente.</p>
        <p><strong>Disclaimer:</strong> Esta herramienta es informativa y no reemplaza el asesoramiento de un contador público. Verificá siempre los valores oficiales en la página de ARCA.</p>
    </div>

    <footer>
        <a href="/aviso-legal">Aviso Legal</a> |
        <a href="/privacidad">Política de Privacidad</a> |
        <a href="/terminos">Términos y Condiciones</a>
        <p style="margin-top: 15px;">© 2026 AlertaMonotributo. Herramienta gratuita para monotributistas argentinos.</p>
    </footer>
</div>
</body>
</html>
'''

# ============================================================
# PLANTILLAS LEGALES
# ============================================================
PLANTILLA_LEGAL = '''
<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ titulo }} - AlertaMonotributo</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; max-width: 800px; margin: 0 auto; padding: 30px 20px; line-height: 1.7; }
        h1 { color: #38bdf8; margin-bottom: 20px; }
        h2 { color: #7dd3fc; margin-top: 25px; margin-bottom: 10px; }
        p { margin-bottom: 15px; color: #cbd5e1; }
        a { color: #38bdf8; }
        .volver { display: inline-block; margin-top: 30px; padding: 12px 24px; background: #38bdf8; color: #0f172a; border-radius: 10px; text-decoration: none; font-weight: 700; }
    </style>
</head>
<body>
    <h1>{{ titulo }}</h1>
    {{ contenido | safe }}
    <a href="/" class="volver">← Volver al inicio</a>
</body>
</html>
'''

# ============================================================
# RUTAS
# ============================================================
@app.before_request
def redirigir_https():
    if not request.is_secure and os.environ.get('RENDER'):
        url = request.url.replace('http://', 'https://', 1)
        return redirect(url, code=301)

@app.route('/', methods=['GET', 'POST'])
def index():
    resultado = None
    error = None
    categoria_actual = ''
    facturacion = ''

    if request.method == 'POST':
        categoria_actual = request.form.get('categoria', '').strip().upper()
        facturacion_str = request.form.get('facturacion', '').strip()

        if not categoria_actual or categoria_actual not in CATEGORIAS:
            error = 'Por favor, elegí una categoría válida.'
        elif not facturacion_str:
            error = 'Por favor, ingresá tu facturación.'
        else:
            try:
                facturacion = float(facturacion_str)
                if facturacion < 0:
                    error = 'La facturación no puede ser negativa.'
                else:
                    resultado = calcular_semaforo(categoria_actual, facturacion)
            except ValueError:
                error = 'Ingresá un número válido en la facturación.'

    return render_template_string(
        PLANTILLA_PRINCIPAL,
        categorias=CATEGORIAS,
        resultado=resultado,
        error=error,
        categoria_actual=categoria_actual,
        facturacion=facturacion
    )

@app.route('/pagar-pro')
def pagar_pro():
    return render_template_string('''
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Suscribite a Pro - AlertaMonotributo</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; max-width: 500px; margin: 0 auto; padding: 40px 20px; }
            h1 { color: #a78bfa; text-align: center; margin-bottom: 10px; }
            p { text-align: center; color: #94a3b8; margin-bottom: 30px; }
            label { display: block; margin-bottom: 6px; font-weight: 600; color: #cbd5e1; }
            input { width: 100%; padding: 14px; border-radius: 10px; border: 1px solid #475569; background: #1e293b; color: #e2e8f0; font-size: 1rem; margin-bottom: 20px; }
            button { width: 100%; padding: 16px; border-radius: 12px; border: none; background: #a78bfa; color: #1e1b4b; font-size: 1.1rem; font-weight: 700; cursor: pointer; }
            .legal { font-size: 0.75rem; color: #64748b; margin-top: 20px; text-align: center; }
            .legal a { color: #38bdf8; }
        </style>
    </head>
    <body>
        <h1>⭐ AlertaMonotributo Pro</h1>
        <p>Suscripción mensual de $7.500 ARS. Cancelás cuando quieras.</p>
        <form method="POST" action="/pagar-pro">
            <label for="email">Tu email:</label>
            <input type="email" name="email" id="email" placeholder="tu@email.com" required>
            <button type="submit">Ir a Mercado Pago →</button>
        </form>
        <div class="legal">
            Al suscribirte aceptás los <a href="/terminos">Términos y Condiciones</a> y la <a href="/privacidad">Política de Privacidad</a>.
        </div>
    </body>
    </html>
    ''')

@app.route('/pagar-pro', methods=['POST'])
def procesar_pago():
    email = request.form.get('email', '').strip()
    if not email or '@' not in email:
        return redirect('/pagar-pro')

    session['email'] = email

    conn = get_db()
    user = conn.execute('SELECT * FROM usuarios WHERE email = ?', (email,)).fetchone()
    if not user:
        conn.execute('INSERT INTO usuarios (email) VALUES (?)', (email,))
        conn.commit()
    conn.close()

    if MERCADOPAGO_ACCESS_TOKEN:
        try:
            headers = {
                'Authorization': f'Bearer {MERCADOPAGO_ACCESS_TOKEN}',
                'Content-Type': 'application/json'
            }
            data = {
                'reason': 'AlertaMonotributo Pro - Suscripción mensual',
                'auto_recurring': {
                    'frequency': 1,
                    'frequency_type': 'months',
                    'transaction_amount': 7500.00,
                    'currency_id': 'ARS'
                },
                'back_url': f'{BASE_URL}/pago-exitoso',
                'payer_email': email,
                'status': 'pending'
            }
            resp = requests.post(
                'https://api.mercadopago.com/preapproval',
                headers=headers,
                json=data
            )
            if resp.status_code in [200, 201]:
                init_point = resp.json().get('init_point')
                if init_point:
                    return redirect(init_point)
        except Exception as e:
            print(f'Error Mercado Pago: {e}')

    return render_template_string('''
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Pro - AlertaMonotributo</title>
    <style>body{font-family:sans-serif;background:#0f172a;color:#e2e8f0;text-align:center;padding:60px 20px;} a{color:#38bdf8;}</style></head>
    <body>
        <h1>⭐ Pro</h1>
        <p>La pasarela de pago no está configurada aún.</p>
        <p>Volvé pronto o contactanos.</p>
        <a href="/">← Volver al inicio</a>
    </body></html>
    ''')

@app.route('/pago-exitoso')
def pago_exitoso():
    return render_template_string('''
    <!DOCTYPE html>
    <html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Pago exitoso - AlertaMonotributo</title>
    <style>body{font-family:sans-serif;background:#0f172a;color:#e2e8f0;text-align:center;padding:60px 20px;} h1{color:#22c55e;} a{color:#38bdf8;}</style></head>
    <body>
        <h1>✅ ¡Suscripción exitosa!</h1>
        <p>Gracias por suscribirte a AlertaMonotributo Pro.</p>
        <p>En breve vas a recibir un email con los detalles.</p>
        <a href="/">← Volver al inicio</a>
    </body></html>
    ''')

@app.route('/webhook-mercadopago', methods=['POST'])
def webhook_mercadopago():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'status': 'ok'}), 200

        topic = data.get('type') or data.get('topic', '')
        resource_id = data.get('data', {}).get('id') or data.get('id')

        if topic == 'subscription_authorized_payment' and resource_id:
            headers = {'Authorization': f'Bearer {MERCADOPAGO_ACCESS_TOKEN}'}
            resp = requests.get(
                f'https://api.mercadopago.com/authorized_payments/{resource_id}',
                headers=headers
            )
            if resp.status_code == 200:
                pago = resp.json()
                email = pago.get('payer_email') or pago.get('preapproval', {}).get('payer_email')
                if email:
                    conn = get_db()
                    vencimiento = (datetime.now() + timedelta(days=30)).isoformat()
                    conn.execute(
                        'UPDATE usuarios SET pro = 1, fecha_vencimiento = ? WHERE email = ?',
                        (vencimiento, email)
                    )
                    if conn.total_changes == 0:
                        conn.execute(
                            'INSERT INTO usuarios (email, pro, fecha_vencimiento) VALUES (?, 1, ?)',
                            (email, vencimiento)
                        )
                    conn.commit()
                    conn.close()

        return jsonify({'status': 'ok'}), 200
    except Exception as e:
        print(f'Error webhook: {e}')
        return jsonify({'status': 'error'}), 500

@app.route('/aviso-legal')
def aviso_legal():
    contenido = '''
    <h2>1. Identificación del titular</h2>
    <p>AlertaMonotributo es una herramienta informativa de acceso gratuito operada por un desarrollador independiente. El sitio se encuentra alojado en servidores de Render.com.</p>
    <h2>2. Objeto</h2>
    <p>El presente Aviso Legal regula el acceso y uso del sitio web AlertaMonotributo. El uso del sitio implica la aceptación plena de las condiciones aquí expuestas.</p>
    <h2>3. Naturaleza informativa</h2>
    <p>AlertaMonotributo es una herramienta de carácter exclusivamente informativo y orientativo. <strong>No constituye asesoramiento fiscal, contable ni legal.</strong> Los resultados arrojados por el semáforo se basan en los topes oficiales de ARCA vigentes al momento de la consulta, pero pueden variar. El usuario debe verificar siempre la información en fuentes oficiales y consultar a un contador público matriculado.</p>
    <h2>4. Responsabilidad</h2>
    <p>El titular del sitio no se responsabiliza por decisiones tomadas en base a la información proporcionada por la herramienta. El uso de los datos arrojados es responsabilidad exclusiva del usuario.</p>
    <h2>5. Propiedad intelectual</h2>
    <p>El código, diseño y contenidos del sitio son propiedad de sus respectivos autores. Queda prohibida su reproducción total o parcial sin autorización.</p>
    <h2>6. Legislación aplicable</h2>
    <p>Este Aviso Legal se rige por las leyes de la República Argentina, en particular la Ley 25.326 de Protección de Datos Personales y la Ley 24.240 de Defensa del Consumidor.</p>
    '''
    return render_template_string(PLANTILLA_LEGAL, titulo='Aviso Legal', contenido=contenido)

@app.route('/privacidad')
def privacidad():
    contenido = '''
    <h2>1. Responsable del tratamiento</h2>
    <p>El responsable del tratamiento de los datos personales recolectados a través de AlertaMonotributo es el titular del sitio, con domicilio en la República Argentina.</p>
    <h2>2. Datos que recolectamos</h2>
    <p>Recolectamos únicamente los siguientes datos personales:</p>
    <ul>
        <li><strong>Email:</strong> cuando el usuario se registra para la versión Pro.</li>
        <li><strong>Datos de facturación:</strong> de forma anónima y temporal para el cálculo del semáforo. No se almacenan asociados a identidad personal.</li>
    </ul>
    <h2>3. Finalidad del tratamiento</h2>
    <p>Los datos recolectados se utilizan exclusivamente para:</p>
    <ul>
        <li>Gestionar la suscripción Pro y el acceso al servicio.</li>
        <li>Enviar notificaciones relacionadas con el servicio.</li>
        <li>Mejorar la herramienta de forma agregada y anónima.</li>
    </ul>
    <h2>4. Consentimiento</h2>
    <p>De conformidad con el artículo 5 de la Ley 25.326, al marcar el checkbox de consentimiento en el formulario de suscripción Pro, el usuario presta su consentimiento libre, expreso e informado para el tratamiento de sus datos personales con las finalidades aquí descriptas.</p>
    <h2>5. Derechos del titular</h2>
    <p>El usuario puede ejercer sus derechos de <strong>acceso, rectificación, actualización y supresión</strong> de datos personales enviando un correo electrónico al responsable del sitio. La respuesta se dará dentro de los 10 días corridos conforme al artículo 14 de la Ley 25.326.</p>
    <p>El titular de los datos puede también presentar denuncias ante la Dirección Nacional de Protección de Datos Personales (organismo de control de la Ley 25.326).</p>
    <h2>6. Seguridad</h2>
    <p>Implementamos medidas técnicas y organizativas razonables para proteger los datos personales contra acceso no autorizado, alteración o destrucción. El sitio fuerza conexión HTTPS en producción.</p>
    <h2>7. Conservación</h2>
    <p>Los datos se conservan mientras el usuario mantenga su suscripción activa. Una vez cancelada, los datos se eliminan dentro de los 30 días posteriores.</p>
    <h2>8. Transferencia de datos</h2>
    <p>Los datos de pago son procesados directamente por Mercado Pago, que cuenta con sus propias políticas de privacidad. No transferimos datos personales a terceros con fines comerciales.</p>
    '''
    return render_template_string(PLANTILLA_LEGAL, titulo='Política de Privacidad', contenido=contenido)

@app.route('/terminos')
def terminos():
    contenido = '''
    <h2>1. Aceptación</h2>
    <p>Al acceder y utilizar AlertaMonotributo, el usuario acepta los presentes Términos y Condiciones en su totalidad.</p>
    <h2>2. Descripción del servicio</h2>
    <p>AlertaMonotributo ofrece una herramienta gratuita de cálculo orientativo del porcentaje de facturación respecto a los topes de categoría del Monotributo argentino. La versión Pro ofrece funcionalidades adicionales mediante suscripción mensual.</p>
    <h2>3. Precio de la suscripción Pro</h2>
    <p>La suscripción Pro tiene un costo de <strong>$7.500 ARS por mes</strong>, con renovación automática. El cobro se realiza a través de Mercado Pago.</p>
    <h2>4. Cancelación</h2>
    <p>El usuario puede cancelar su suscripción en cualquier momento desde su cuenta de Mercado Pago. La cancelación detiene los cobros futuros, pero no genera reembolso de períodos ya abonados.</p>
    <h2>5. Uso permitido</h2>
    <p>El usuario se compromete a utilizar la herramienta de forma lícita y conforme a su finalidad. Queda prohibido el uso automatizado masivo, el scraping o la reventa del servicio.</p>
    <h2>6. Limitación de responsabilidad</h2>
    <p>AlertaMonotributo no garantiza la exactitud absoluta de los cálculos. Los topes y cuotas pueden variar por decisiones de ARCA. El usuario utiliza la herramienta bajo su propio riesgo y debe validar la información con un profesional matriculado.</p>
    <h2>7. Modificaciones</h2>
    <p>Nos reservamos el derecho de modificar estos términos en cualquier momento. Los cambios serán notificados a través del sitio web.</p>
    <h2>8. Jurisdicción</h2>
    <p>Cualquier controversia derivada del uso del sitio se someterá a la jurisdicción de los tribunales ordinarios de la Ciudad Autónoma de Buenos Aires, República Argentina.</p>
    '''
    return render_template_string(PLANTILLA_LEGAL, titulo='Términos y Condiciones', contenido=contenido)

# ============================================================
# INICIO
# ============================================================
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)