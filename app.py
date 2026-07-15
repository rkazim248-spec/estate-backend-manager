import os
import base64
from flask import Flask, render_template, request, jsonify, session, redirect, url_style
from flask_bcrypt import Bcrypt
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = "ali_estate_secure_super_secret_key_2026"
bcrypt = Bcrypt(app)

# --- GOOGLE SHEETS CONFIGURATION ---
# Target Google Sheet ID directly linked
GOOGLE_SHEET_ID = "YOUR_GOOGLE_SHEET_ID_HERE" 

def get_sheets_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    # Looks for credentials.json in the same folder
    if os.path.exists("credentials.json"):
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        return gspread.authorize(creds)
    return None

def sync_to_google_sheet(user_id, data_type, action, payload):
    """Real-time Google Sheet synchronization wrapper"""
    try:
        client = get_sheets_client()
        if not client:
            return
        
        sheet = client.open_by_key(GOOGLE_SHEET_ID)
        # Select or automatically create worksheet for the specific data scope
        try:
            worksheet = sheet.worksheet(data_type)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet.add_worksheet(title=data_type, rows="100", cols="20")
            # Headers setup if new
            if data_type == "properties":
                worksheet.append_row(["ID", "User ID", "Title", "Project", "Type", "Price", "Location", "Owner Name", "Owner Phone", "Status", "Owner Demand", "Description"])
            elif data_type == "demands":
                worksheet.append_row(["ID", "User ID", "Client Name", "Client Phone", "Required Type", "Preferred Location", "Max Budget", "Status", "Notes"])
            elif data_type == "transactions":
                worksheet.append_row(["ID", "User ID", "Property ID", "Type", "Amount", "Category", "Date"])

        if action == "insert":
            row_data = [payload.get("id"), user_id] + list(payload.values())[1:]
            worksheet.append_row(list(map(str, row_data)))
        elif action == "update":
            cell = worksheet.find(str(payload.get("id")))
            if cell:
                row_num = cell.row
                row_data = [payload.get("id"), user_id] + list(payload.values())[1:]
                for col_idx, val in enumerate(row_data, start=1):
                    worksheet.update_cell(row_num, col_idx, str(val))
        elif action == "delete":
            cell = worksheet.find(str(payload.get("id")))
            if cell:
                worksheet.delete_rows(cell.row)
    except Exception as e:
        print(f"Google Sheet Sync Error: {e}")

# --- IN-MEMORY DATABASE FALLBACK FOR USER STORAGE ---
# Real-world apps use SQLAlchemy/MongoDB, this mimics isolated user datasets
USERS_DB = {}
PROPERTIES_DB = {}
DEMANDS_DB = {}
TRANSACTIONS_DB = {}

@app.route('/')
def index():
    if "user_id" in session:
        return render_template('index.html', user_id=session["user_id"])
    return render_template('index.html', user_id=None)

# --- AUTHENTICATION ENDPOINTS ---
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    
    if not email or not password:
        return jsonify({"message": "Missing arguments"}), 400
    if email in USERS_DB:
        return jsonify({"message": "User already exists"}), 400
        
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    user_id = base64.b64encode(email.encode()).decode()
    USERS_DB[email] = {"user_id": user_id, "password": hashed_pw}
    
    # Initialize structural arrays
    PROPERTIES_DB[user_id] = []
    DEMANDS_DB[user_id] = []
    TRANSACTIONS_DB[user_id] = []
    
    session["user_id"] = user_id
    return jsonify({"user_id": user_id})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    
    user = USERS_DB.get(email)
    if user and bcrypt.check_password_hash(user["password"], password):
        session["user_id"] = user["user_id"]
        return jsonify({"user_id": user["user_id"]})
        
    return jsonify({"message": "Invalid credential structures"}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop("user_id", None)
    return jsonify({"success": True})

# --- DATA ROUTING INTERFACES ---
@app.route('/api/properties', methods=['GET', 'POST'])
def handle_properties():
    user_id = request.args.get("user_id") or session.get("user_id")
    if not user_id: return jsonify([]), 401
    
    if user_id not in PROPERTIES_DB: PROPERTIES_DB[user_id] = []

    if request.method == 'POST':
        data = request.json
        if data.get("id"): # Edit action branch
            p_id = int(data.get("id"))
            for p in PROPERTIES_DB[user_id]:
                if p["id"] == p_id:
                    p.update(data)
                    sync_to_google_sheet(user_id, "properties", "update", p)
                    return jsonify(p)
        else: # New addition branch
            data["id"] = int(os.urandom(2).hex(), 16)
            PROPERTIES_DB[user_id].append(data)
            sync_to_google_sheet(user_id, "properties", "insert", data)
            return jsonify(data)
            
    return jsonify(PROPERTIES_DB[user_id])

@app.route('/api/properties/<int:pid>', methods=['DELETE'])
def delete_property(pid):
    user_id = request.args.get("user_id")
    if not user_id or user_id not in PROPERTIES_DB: return jsonify({"success": False}), 401
    
    target = next((p for p in PROPERTIES_DB[user_id] if p["id"] == pid), None)
    if target:
        PROPERTIES_DB[user_id] = [p for p in PROPERTIES_DB[user_id] if p["id"] != pid]
        sync_to_google_sheet(user_id, "properties", "delete", target)
    return jsonify({"success": True})

@app.route('/api/demands', methods=['GET', 'POST'])
def handle_demands():
    user_id = request.args.get("user_id") or session.get("user_id")
    if not user_id: return jsonify([]), 401
    
    if user_id not in DEMANDS_DB: DEMANDS_DB[user_id] = []

    if request.method == 'POST':
        data = request.json
        if data.get("id"):
            d_id = int(data.get("id"))
            for d in DEMANDS_DB[user_id]:
                if d["id"] == d_id:
                    d.update(data)
                    sync_to_google_sheet(user_id, "demands", "update", d)
                    return jsonify(d)
        else:
            data["id"] = int(os.urandom(2).hex(), 16)
            DEMANDS_DB[user_id].append(data)
            sync_to_google_sheet(user_id, "demands", "insert", data)
            return jsonify(data)
            
    return jsonify(DEMANDS_DB[user_id])

@app.route('/api/demands/<int:did>', methods=['DELETE'])
def delete_demand(did):
    user_id = request.args.get("user_id")
    if not user_id or user_id not in DEMANDS_DB: return jsonify({"success": False}), 401
    
    target = next((d for d in DEMANDS_DB[user_id] if d["id"] == did), None)
    if target:
        DEMANDS_DB[user_id] = [d for d in DEMANDS_DB[user_id] if d["id"] != did]
        sync_to_google_sheet(user_id, "demands", "delete", target)
    return jsonify({"success": True})

@app.route('/api/transactions', methods=['GET', 'POST'])
def handle_transactions():
    user_id = request.args.get("user_id") or session.get("user_id")
    if not user_id: return jsonify([]), 401
    
    if user_id not in TRANSACTIONS_DB: TRANSACTIONS_DB[user_id] = []

    if request.method == 'POST':
        data = request.json
        data["id"] = int(os.urandom(2).hex(), 16)
        TRANSACTIONS_DB[user_id].append(data)
        sync_to_google_sheet(user_id, "transactions", "insert", data)
        return jsonify(data)
        
    return jsonify(TRANSACTIONS_DB[user_id])

@app.route('/api/transactions/<int:tid>', methods=['DELETE'])
def delete_transaction(tid):
    user_id = request.args.get("user_id")
    if not user_id or user_id not in TRANSACTIONS_DB: return jsonify({"success": False}), 401
    
    target = next((t for t in TRANSACTIONS_DB[user_id] if t["id"] == tid), None)
    if target:
        TRANSACTIONS_DB[user_id] = [t for t in TRANSACTIONS_DB[user_id] if t["id"] != tid]
        sync_to_google_sheet(user_id, "transactions", "delete", target)
    return jsonify({"success": True})

@app.route('/api/stats', methods=['GET'])
def get_stats():
    user_id = request.args.get("user_id")
    if not user_id: return jsonify({"balance": 0, "income": 0, "expense": 0})
    
    txs = TRANSACTIONS_DB.get(user_id, [])
    income = sum(t["amount"] for t in txs if t["trans_type"] == "Income")
    expense = sum(t["amount"] for t in txs if t["trans_type"] == "Expense")
    return jsonify({
        "balance": income - expense,
        "income": income,
        "expense": expense
    })

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    data = request.json
    msg = data.get("message", "").lower()
    user_id = data.get("user_id")
    
    props = PROPERTIES_DB.get(user_id, [])
    txs = TRANSACTIONS_DB.get(user_id, [])
    
    # Advanced inline rule-based analysis context engine matching real-time listings
    if "listing" in msg or "property" in msg:
        reply = f"You currently manage {len(props)} listings in your workspace. "
        available = len([p for p in props if p.get("status") == "Available"])
        reply += f"Currently, {available} properties are Available and {len(props)-available} have been marked as Sold."
    elif "ledger" in msg or "financial" in msg or "money" in msg:
        income = sum(t["amount"] for t in txs if t["trans_type"] == "Income")
        expense = sum(t["amount"] for t in txs if t["trans_type"] == "Expense")
        reply = f"Financial Analysis Engine report: Total recorded Income is Rs. {income:,}, total operational Expenses are Rs. {expense:,}, yielding a net safe balance of Rs. {income-expense:,}."
    else:
        reply = "I am processing your workspace matrix. I can analyze financial ledger shifts, compute active-to-sold ratios, evaluate budgets, or track records inside your Google Sheets dynamically."
        
    return jsonify({"reply": reply})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
