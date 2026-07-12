import os
import sqlite3
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from groq import Groq

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("GroqRotator")

app = Flask(__name__)
CORS(app)

DATABASE = "estate_manager.db"

# Updated Model name according to latest Groq docs
GROQ_MODEL = "llama-3.1-8b-instant"

# Environment variable se string uthayein (e.g., "key1,key2,key3")
raw_keys = os.environ.get("GROQ_API_KEYS", "")

# Agar variable mil jaye toh comma se split karke list bana lein, warna khali list
if raw_keys:
    GROQ_API_KEYS = [key.strip() for key in raw_keys.split(",")]
else:
    # Backup ke liye agar Azure par variable set na ho toh khali list ya koi default key
    GROQ_API_KEYS = []

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            project_name TEXT,
            type TEXT,
            location TEXT,
            price TEXT,
            owner_name TEXT,
            owner_phone TEXT,
            owner_demand TEXT,
            description TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS demands (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            property_id INTEGER,
            trans_type TEXT,
            amount REAL,
            category TEXT,
            date TEXT
        )
    """)
    conn.commit()
    conn.close()
    logger.info("Database tables verified/created successfully.")

init_db()

def get_all_app_data_str():
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM properties")
        props = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT * FROM demands")
        demands = [dict(r) for r in cursor.fetchall()]
        cursor.execute("SELECT * FROM transactions")
        txs = [dict(r) for r in cursor.fetchall()]
        conn.close()
        return f"Properties: {str(props)} | Client Demands: {str(demands)} | Financial Ledger Logs: {str(txs)}"
    except Exception as e:
        logger.error(f"Database read error: {str(e)}")
        return "Properties: [] | Client Demands: [] | Financial Ledger Logs: []"

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    data = request.json
    user_message = data.get('message', '')
    if not user_message:
        return jsonify({"reply": "Hello! I am your AI Consultant. How can I assist you today?"})
    
    live_app_context = get_all_app_data_str()
    system_prompt = (
        "You are a professional real estate expert assistant for 'Ali Estate Manager Pro'. "
        "You must communicate strictly in professional, polite, and natural English. "
        "You have direct real-time access to the live application database supplied below. Analyze it thoroughly "
        "to answer user questions, cross-match active listings with buyer demands, analyze financial balances, "
        "or offer tactical estate business advice. Talk like a real human real estate expert, keeping answers structured.\n"
        f"LIVE APP DATA: {live_app_context}"
    )
    
    last_error_msg = ""
    for idx, api_key in enumerate(GROQ_API_KEYS):
        try:
            logger.info(f"Attempting Chat Completion using API Key Index: {idx}")
            client = Groq(api_key=api_key)
            chat_completion = client.chat.completions.create(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_message}
                ],
                model=GROQ_MODEL,
                temperature=0.7
            )
            return jsonify({"reply": chat_completion.choices[0].message.content})
        except Exception as e:
            logger.warning(f"Key Index {idx} failed. Error: {str(e)}")
            last_error_msg = str(e)
            continue
            
    return jsonify({"reply": f"All 3 Groq API keys failed. Last error: {last_error_msg}"})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE trans_type='Income'")
    income = cursor.fetchone()[0] or 0
    cursor.execute("SELECT SUM(amount) FROM transactions WHERE trans_type='Expense'")
    expense = cursor.fetchone()[0] or 0
    conn.close()
    return jsonify({"balance": income - expense})

@app.route('/api/properties', methods=['GET', 'POST'])
def handle_properties():
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        d = request.json
        cursor.execute(
            "INSERT INTO properties (title, project_name, type, location, price, owner_name, owner_phone, owner_demand, description) VALUES (?,?,?,?,?,?,?,?,?)",
            (d['title'], d.get('project_name',''), d['type'], d['location'], d['price'], d.get('owner_name',''), d.get('owner_phone',''), d.get('owner_demand',''), d.get('description',''))
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    
    cursor.execute("SELECT * FROM properties")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/properties/<int:id>', methods=['DELETE'])
def delete_property(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM properties WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})

@app.route('/api/demands', methods=['GET', 'POST'])
def handle_demands():
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        d = request.json
        cursor.execute(
            "INSERT INTO demands (client_name, client_phone, required_type, preferred_location, max_budget, client_demand_notes) VALUES (?,?,?,?,?,?)",
            (d['client_name'], d['client_phone'], d['required_type'], d['preferred_location'], d['max_budget'], d.get('client_demand_notes',''))
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    
    cursor.execute("SELECT * FROM demands")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/demands/<int:id>', methods=['DELETE'])
def delete_demand(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM demands WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})

@app.route('/api/transactions', methods=['GET', 'POST'])
def handle_transactions():
    conn = get_db()
    cursor = conn.cursor()
    if request.method == 'POST':
        d = request.json
        cursor.execute(
            "INSERT INTO transactions (property_id, trans_type, amount, category, date) VALUES (?,?,?,?,?)",
            (d['property_id'], d['trans_type'], d['amount'], d['category'], d['date'])
        )
        conn.commit()
        conn.close()
        return jsonify({"status": "success"})
    
    cursor.execute("SELECT * FROM transactions")
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route('/api/transactions/<int:id>', methods=['DELETE'])
def delete_transaction(id):
    conn = get_db()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE id=?", (id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "deleted"})
    
    app = app
if __name__ == '__main__':
    # Render khud port assign karta hai, agar na mile toh default 5000
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
