import os
import logging
import psycopg2
from psycopg2.extras import RealDictCursor
from flask import Flask, request, jsonify, make_response
from flask_cors import CORS
from groq import Groq
import jwt
import datetime
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AliEstateSaaS")

app = Flask(__name__)

# Dynamic CORS handling for production and local environments
CORS(app, resources={r"/api/*": {
    "origins": ["http://localhost:5500", "http://127.0.0.1:5500", "*"],
    "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    "allow_headers": ["Content-Type", "Authorization"],
    "supports_credentials": True
}})

JWT_SECRET = os.environ.get("JWT_SECRET", "ali_estate_secure_secret_key_2026")
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://neondb_owner:npg_UoJ4kMmPaz8v@ep-late-pine-ath92cf5.c-9.us-east-1.aws.neon.tech/neondb?sslmode=require")

GROQ_MODEL = "llama-3.1-8b-instant"
raw_keys = os.environ.get("GROQ_API_KEYS", "")
GROQ_API_KEYS = [key.strip() for key in raw_keys.split(",")] if raw_keys else []

def get_db():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    # Central Users Table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            name TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    # Multi-tenant tables
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id SERIAL PRIMARY KEY,
            user_email TEXT NOT NULL,
            title TEXT NOT NULL,
            project_name TEXT,
            type TEXT,
            location TEXT,
            price TEXT,
            owner_name TEXT,
            owner_phone TEXT,
            owner_demand TEXT,
            description TEXT,
            status TEXT DEFAULT 'Available'
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS demands (
            id SERIAL PRIMARY KEY,
            user_email TEXT NOT NULL,
            client_name TEXT,
            client_phone TEXT,
            required_type TEXT,
            preferred_location TEXT,
            max_budget TEXT,
            client_demand_notes TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id SERIAL PRIMARY KEY,
            user_email TEXT NOT NULL,
            property_id INTEGER,
            trans_type TEXT,
            amount REAL,
            category TEXT,
            date TEXT
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()
    logger.info("Database system initialised successfully.")

init_db()

# Middleware handler to verify tokens
def get_auth_user():
    auth_header = request.headers.get('Authorization', None)
    if not auth_header:
        return None
    try:
        token = auth_header.split(" ")[1]
        payload = jwt.decode(token, JWT_SECRET, algorithms=["HS256"])
        return payload['email']
    except Exception:
        return None

# Preflight dynamic handler
@app.before_request
def handle_options_preflight():
    if request.method == 'OPTIONS':
        response = make_response()
        origin = request.headers.get('Origin')
        if origin in ["http://localhost:5500", "http://127.0.0.1:5500"]:
            response.headers['Access-Control-Allow-Origin'] = origin
        else:
            response.headers['Access-Control-Allow-Origin'] = "http://localhost:5500"
            
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        response.headers['Access-Control-Allow-Credentials'] = 'true'
        return response, 200

# --- SECURE LOCAL AUTHENTICATION API SYSTEM ---

@app.route('/api/auth/signup', methods=['POST'])
def auth_signup():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    name = data.get('name', '').strip() or 'User'
    
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
        
    email_regex = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
    if not re.match(email_regex, email):
        return jsonify({"error": "Invalid email format."}), 400
        
    if len(password) < 6:
        return jsonify({"error": "Password must be at least 6 characters long."}), 400
        
    conn = get_db()
    cursor = conn.cursor()
    try:
        cursor.execute("INSERT INTO users (email, password, name) VALUES (%s, %s, %s)", (email, password, name))
        conn.commit()
        token = jwt.encode({"email": email, "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)}, JWT_SECRET, algorithm="HS256")
        return jsonify({"token": token, "email": email, "name": name})
    except psycopg2.errors.UniqueViolation:
        return jsonify({"error": "An account with this email already exists."}), 400
    finally:
        cursor.close()
        conn.close()

@app.route('/api/auth/signin', methods=['POST'])
def auth_signin():
    data = request.json
    email = data.get('email', '').strip().lower()
    password = data.get('password', '')
    
    if not email or not password:
        return jsonify({"error": "Email and password are required."}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE email=%s AND password=%s", (email, password))
    user = cursor.fetchone()
    cursor.close()
    conn.close()
    
    if user:
        token = jwt.encode({"email": email, "exp": datetime.datetime.utcnow() + datetime.timedelta(days=7)}, JWT_SECRET, algorithm="HS256")
        return jsonify({"token": token, "email": email, "name": user['name']})
    else:
        return jsonify({"error": "Incorrect email or password."}), 401

# --- MULTI-TENANT PROPERTY & DATA SYSTEM ---

@app.route('/api/stats', methods=['GET'])
def get_stats():
    email = get_auth_user()
    if not email: return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_email=%s AND trans_type='Income'", (email,))
    inc = cursor.fetchone()
    income_val = inc['sum'] if inc and inc['sum'] is not None else 0
    
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE user_email=%s AND trans_type='Expense'", (email,))
    exp = cursor.fetchone()
    expense_val = exp['sum'] if exp and exp['sum'] is not None else 0
    
    cursor.close()
    conn.close()
    return jsonify({"balance": income_val - expense_val})

@app.route('/api/properties', methods=['GET', 'POST'])
def handle_properties():
    email = get_auth_user()
    if not email: return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        d = request.json
        if d.get('id'):
            cursor.execute(
                "UPDATE properties SET title=%s, project_name=%s, type=%s, location=%s, price=%s, owner_name=%s, owner_phone=%s, owner_demand=%s, description=%s, status=%s WHERE id=%s AND user_email=%s",
                (d['title'], d.get('project_name',''), d['type'], d['location'], d['price'], d.get('owner_name',''), d.get('owner_phone',''), d.get('owner_demand',''), d.get('description',''), d.get('status','Available'), int(d['id']), email)
            )
        else:
            cursor.execute(
                "INSERT INTO properties (user_email, title, project_name, type, location, price, owner_name, owner_phone, owner_demand, description, status) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (email, d['title'], d.get('project_name',''), d['type'], d['location'], d['price'], d.get('owner_name',''), d.get('owner_phone',''), d.get('owner_demand',''), d.get('description',''), d.get('status','Available'))
            )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success"})
    
    cursor.execute("SELECT * FROM properties WHERE user_email=%s ORDER BY id DESC", (email,))
    rows = [dict(r) for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(rows)

@app.route('/api/properties/<int:id>', methods=['PUT', 'DELETE'])
def update_delete_property(id):
    email = get_auth_user()
    if not email: return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'PUT':
        d = request.json
        cursor.execute(
            "UPDATE properties SET title=%s, project_name=%s, type=%s, location=%s, price=%s, owner_name=%s, owner_phone=%s, owner_demand=%s, description=%s, status=%s WHERE id=%s AND user_email=%s",
            (d['title'], d.get('project_name',''), d['type'], d['location'], d['price'], d.get('owner_name',''), d.get('owner_phone',''), d.get('owner_demand',''), d.get('description',''), d.get('status','Available'), id, email)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "updated"})
        
    cursor.execute("DELETE FROM properties WHERE id=%s AND user_email=%s", (id, email))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "deleted"})

@app.route('/api/demands', methods=['GET', 'POST'])
def handle_demands():
    email = get_auth_user()
    if not email: return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        d = request.json
        if d.get('id'):
            cursor.execute(
                "UPDATE demands SET client_name=%s, client_phone=%s, required_type=%s, preferred_location=%s, max_budget=%s, client_demand_notes=%s WHERE id=%s AND user_email=%s",
                (d['client_name'], d['client_phone'], d['required_type'], d['preferred_location'], d['max_budget'], d.get('client_demand_notes',''), int(d['id']), email)
            )
        else:
            cursor.execute(
                "INSERT INTO demands (user_email, client_name, client_phone, required_type, preferred_location, max_budget, client_demand_notes) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                (email, d['client_name'], d['client_phone'], d['required_type'], d['preferred_location'], d['max_budget'], d.get('client_demand_notes',''))
            )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success"})
    
    cursor.execute("SELECT * FROM demands WHERE user_email=%s ORDER BY id DESC", (email,))
    rows = [dict(r) for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(rows)

@app.route('/api/demands/<int:id>', methods=['PUT', 'DELETE'])
def update_delete_demand(id):
    email = get_auth_user()
    if not email: return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'PUT':
        d = request.json
        cursor.execute(
            "UPDATE demands SET client_name=%s, client_phone=%s, required_type=%s, preferred_location=%s, max_budget=%s, client_demand_notes=%s WHERE id=%s AND user_email=%s",
            (d['client_name'], d['client_phone'], d['required_type'], d['preferred_location'], d['max_budget'], d.get('client_demand_notes',''), id, email)
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "updated"})

    cursor.execute("DELETE FROM demands WHERE id=%s AND user_email=%s", (id, email))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "deleted"})

@app.route('/api/transactions', methods=['GET', 'POST'])
def handle_transactions():
    email = get_auth_user()
    if not email: return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        d = request.json
        cursor.execute(
            "INSERT INTO transactions (user_email, property_id, trans_type, amount, category, date) VALUES (%s,%s,%s,%s,%s,%s)",
            (email, d['property_id'], d['trans_type'], d['amount'], d['category'], d['date'])
        )
        conn.commit()
        cursor.close()
        conn.close()
        return jsonify({"status": "success"})
    
    cursor.execute("SELECT * FROM transactions WHERE user_email=%s ORDER BY id DESC", (email,))
    rows = [dict(r) for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    return jsonify(rows)

@app.route('/api/transactions/<int:id>', methods=['DELETE'])
def delete_transaction(id):
    email = get_auth_user()
    if not email: return jsonify({"error": "Unauthorized"}), 401
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE id=%s AND user_email=%s", (id, email))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({"status": "deleted"})

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    email = get_auth_user()
    if not email: return jsonify({"reply": "Session expired. Please sign in again."}), 401
    
    data = request.json
    user_message = data.get('message', '')
    if not user_message:
        return jsonify({"reply": "Hello! I am your estate workspace assistant. Ask me anything!"})
    
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM properties WHERE user_email=%s", (email,))
    props = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM demands WHERE user_email=%s", (email,))
    demands = [dict(r) for r in cursor.fetchall()]
    cursor.execute("SELECT * FROM transactions WHERE user_email=%s", (email,))
    txs = [dict(r) for r in cursor.fetchall()]
    cursor.close()
    conn.close()
    
    live_app_context = f"Properties: {str(props)} | Client Demands: {str(demands)} | Financial Logs: {str(txs)}"
    system_prompt = (
        f"You are the personalized estate assistant for workspace owner account: {email}. "
        f"Analyze their datasets politely. Never leak information outside this database sandbox.\n"
        f"CURRENT ACCOUNT CONTEXT: {live_app_context}"
    )
    
    last_error_msg = ""
    for api_key in GROQ_API_KEYS:
        try:
            client = Groq(api_key=api_key)
            chat_completion = client.chat.completions.create(
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_message}],
                model=GROQ_MODEL, temperature=0.7
            )
            return jsonify({"reply": chat_completion.choices[0].message.content})
        except Exception as e:
            last_error_msg = str(e)
            continue
            
    return jsonify({"reply": f"AI Engine delayed. Error log: {last_error_msg}"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
