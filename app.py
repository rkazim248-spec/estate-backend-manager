import os
import base64
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_bcrypt import Bcrypt
from flask_sqlalchemy import SQLAlchemy  # Database handling ke liye
import gspread
from google.oauth2.service_account import Credentials

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ali_estate_secure_super_secret_key_2026")
bcrypt = Bcrypt(app)

# --- NEON.COM POSTGRESQL CONFIGURATION ---
# Neon ki Connection String (Vercel ke Environment Variables me DATABASE_URL ke naam se save karein)
# Local testing ke liye default string niche di gayi hai
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    'postgresql://neondb_owner:your_password@ep-some-endpoint.eastus2.azure.neon.tech/neondb?sslmode=require'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- DATABASE MODELS ---
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String(100), primary_key=True)  # Base64 Email
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Property(db.Model):
    __tablename__ = 'properties'
    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(200))
    project_name = db.Column(db.String(200))  # UI key matches project_name
    type = db.Column(db.String(50))
    price = db.Column(db.Float)
    location = db.Column(db.String(200))
    owner_name = db.Column(db.String(100))
    owner_phone = db.Column(db.String(50))
    status = db.Column(db.String(50))
    owner_demand = db.Column(db.String(100))
    description = db.Column(db.Text)

class Demand(db.Model):
    __tablename__ = 'demands'
    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)
    client_name = db.Column(db.String(100))
    client_phone = db.Column(db.String(50))
    required_type = db.Column(db.String(100))
    preferred_location = db.Column(db.String(200))
    max_budget = db.Column(db.Float)
    status = db.Column(db.String(50))
    notes = db.Column(db.Text)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)
    property_id = db.Column(db.String(100))
    trans_type = db.Column(db.String(50))  # Income or Expense
    amount = db.Column(db.Float)
    category = db.Column(db.String(100))
    date = db.Column(db.String(50))

# Tables create karne ke liye command (Ya direct Neon console se tables bana sakte hain)
with app.app_context():
    db.create_all()


# --- GOOGLE SHEETS CONFIGURATION ---
GOOGLE_SHEET_ID = os.environ.get("GOOGLE_SHEET_ID", "YOUR_GOOGLE_SHEET_ID_HERE")

def get_sheets_client():
    scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
    # Vercel par files store nahi hotin, isliye credentials ko Base64 env variable me rakhna behtar hai
    creds_raw = os.environ.get("GOOGLE_CREDENTIALS_BASE64")
    if creds_raw:
        import json
        creds_info = json.loads(base64.b64decode(creds_raw).decode())
        creds = Credentials.from_service_account_info(creds_info, scopes=scopes)
        return gspread.authorize(creds)
    elif os.path.exists("credentials.json"):
        creds = Credentials.from_service_account_file("credentials.json", scopes=scopes)
        return gspread.authorize(creds)
    return None

def sync_to_google_sheet(user_id, data_type, action, payload):
    try:
        if GOOGLE_SHEET_ID == "YOUR_GOOGLE_SHEET_ID_HERE":
            return
        client = get_sheets_client()
        if not client:
            return
        
        sheet = client.open_by_key(GOOGLE_SHEET_ID)
        try:
            worksheet = sheet.worksheet(data_type)
        except gspread.exceptions.WorksheetNotFound:
            worksheet = sheet.add_worksheet(title=data_type, rows="100", cols="20")
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
        
    existing_user = User.query.filter_by(email=email).first()
    if existing_user:
        return jsonify({"message": "User already exists"}), 400
        
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    user_id = base64.b64encode(email.encode()).decode()
    
    new_user = User(id=user_id, email=email, password=hashed_pw)
    db.session.add(new_user)
    db.session.commit()  # <-- Saved permanently to Neon
    
    session["user_id"] = user_id
    return jsonify({"user_id": user_id})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json
    email = data.get("email")
    password = data.get("password")
    
    user = User.query.filter_by(email=email).first()
    if user and bcrypt.check_password_hash(user.password, password):
        session["user_id"] = user.id
        return jsonify({"user_id": user.id})
        
    return jsonify({"message": "Invalid credential structures"}), 401

@app.route('/api/auth/logout', methods=['POST'])
def logout():
    session.pop("user_id", None)
    return jsonify({"success": True})


# --- DATA ROUTING INTERFACES (PROPERTIES) ---
@app.route('/api/properties', methods=['GET', 'POST'])
def handle_properties():
    user_id = request.args.get("user_id") or session.get("user_id")
    if not user_id: return jsonify([]), 401
    
    if request.method == 'POST':
        data = request.json
        if data.get("id"):  # Edit Property
            p_id = int(data.get("id"))
            prop = Property.query.filter_by(id=p_id, user_id=user_id).first()
            if prop:
                prop.title = data.get("title")
                prop.project_name = data.get("project_name")
                prop.type = data.get("type")
                prop.price = data.get("price")
                prop.location = data.get("location")
                prop.owner_name = data.get("owner_name")
                prop.owner_phone = data.get("owner_phone")
                prop.status = data.get("status")
                prop.owner_demand = data.get("owner_demand")
                prop.description = data.get("description")
                db.session.commit()
                
                sync_to_google_sheet(user_id, "properties", "update", data)
                return jsonify(data)
        else:  # New Property
            import random
            new_id = random.randint(100000, 999999)
            new_prop = Property(
                id=new_id,
                user_id=user_id,
                title=data.get("title"),
                project_name=data.get("project_name"),
                type=data.get("type"),
                price=data.get("price"),
                location=data.get("location"),
                owner_name=data.get("owner_name"),
                owner_phone=data.get("owner_phone"),
                status=data.get("status", "Available"),
                owner_demand=data.get("owner_demand"),
                description=data.get("description")
            )
            db.session.add(new_prop)
            db.session.commit()
            
            data["id"] = new_id
            sync_to_google_sheet(user_id, "properties", "insert", data)
            return jsonify(data)
            
    # GET Request: Neon database se filter karke return karein
    properties = Property.query.filter_by(user_id=user_id).all()
    output = []
    for p in properties:
        output.append({
            "id": p.id, "title": p.title, "project_name": p.project_name, "type": p.type,
            "price": p.price, "location": p.location, "owner_name": p.owner_name,
            "owner_phone": p.owner_phone, "status": p.status, "owner_demand": p.owner_demand,
            "description": p.description
        })
    return jsonify(output)

@app.route('/api/properties/<int:pid>', methods=['DELETE'])
def delete_property(pid):
    user_id = request.args.get("user_id") or session.get("user_id")
    if not user_id: return jsonify({"success": False}), 401
    
    prop = Property.query.filter_by(id=pid, user_id=user_id).first()
    if prop:
        db.session.delete(prop)
        db.session.commit()
        
        payload = {"id": pid}
        sync_to_google_sheet(user_id, "properties", "delete", payload)
        return jsonify({"success": True})
    return jsonify({"success": False}), 404

# --- DATA ROUTING INTERFACES (DEMANDS) ---
@app.route('/api/demands', methods=['GET', 'POST'])
def handle_demands():
    user_id = request.args.get("user_id") or session.get("user_id")
    if not user_id: return jsonify([]), 401
    
    if request.method == 'POST':
        data = request.json
        if data.get("id"):
            d_id = int(data.get("id"))
            demand = Demand.query.filter_by(id=d_id, user_id=user_id).first()
            if demand:
                demand.client_name = data.get("client_name")
                demand.client_phone = data.get("client_phone")
                demand.required_type = data.get("required_type")
                demand.preferred_location = data.get("preferred_location")
                demand.max_budget = data.get("max_budget")
                demand.status = data.get("status")
                demand.notes = data.get("notes")
                db.session.commit()
                sync_to_google_sheet(user_id, "demands", "update", data)
                return jsonify(data)
        else:
            import random
            new_id = random.randint(100000, 999999)
            new_demand = Demand(
                id=new_id,
                user_id=user_id,
                client_name=data.get("client_name"),
                client_phone=data.get("client_phone"),
                required_type=data.get("required_type"),
                preferred_location=data.get("preferred_location"),
                max_budget=data.get("max_budget"),
                status=data.get("status", "Active"),
                notes=data.get("notes")
            )
            db.session.add(new_demand)
            db.session.commit()
            
            data["id"] = new_id
            sync_to_google_sheet(user_id, "demands", "insert", data)
            return jsonify(data)
            
    demands = Demand.query.filter_by(user_id=user_id).all()
    output = []
    for d in demands:
        output.append({
            "id": d.id, "client_name": d.client_name, "client_phone": d.client_phone,
            "required_type": d.required_type, "preferred_location": d.preferred_location,
            "max_budget": d.max_budget, "status": d.status, "notes": d.notes
        })
    return jsonify(output)

@app.route('/api/demands/<int:did>', methods=['DELETE'])
def delete_demand(did):
    user_id = request.args.get("user_id") or session.get("user_id")
    if not user_id: return jsonify({"success": False}), 401
    
    demand = Demand.query.filter_by(id=did, user_id=user_id).first()
    if demand:
        db.session.delete(demand)
        db.session.commit()
        sync_to_google_sheet(user_id, "demands", "delete", {"id": did})
        return jsonify({"success": True})
    return jsonify({"success": False}), 404

# --- DATA ROUTING INTERFACES (TRANSACTIONS) ---
@app.route('/api/transactions', methods=['GET', 'POST'])
def handle_transactions():
    user_id = request.args.get("user_id") or session.get("user_id")
    if not user_id: return jsonify([]), 401
    
    if request.method == 'POST':
        data = request.json
        import random
        new_id = random.randint(100000, 999999)
        new_tx = Transaction(
            id=new_id,
            user_id=user_id,
            property_id=data.get("property_id"),
            trans_type=data.get("trans_type"),
            amount=data.get("amount"),
            category=data.get("category"),
            date=data.get("date")
        )
        db.session.add(new_tx)
        db.session.commit()
        
        data["id"] = new_id
        sync_to_google_sheet(user_id, "transactions", "insert", data)
        return jsonify(data)
        
    transactions = Transaction.query.filter_by(user_id=user_id).all()
    output = []
    for t in transactions:
        output.append({
            "id": t.id, "property_id": t.property_id, "trans_type": t.trans_type,
            "amount": t.amount, "category": t.category, "date": t.date
        })
    return jsonify(output)

@app.route('/api/transactions/<int:tid>', methods=['DELETE'])
def delete_transaction(tid):
    user_id = request.args.get("user_id") or session.get("user_id")
    if not user_id: return jsonify({"success": False}), 401
    
    tx = Transaction.query.filter_by(id=tid, user_id=user_id).first()
    if tx:
        db.session.delete(tx)
        db.session.commit()
        sync_to_google_sheet(user_id, "transactions", "delete", {"id": tid})
        return jsonify({"success": True})
    return jsonify({"success": False}), 404

@app.route('/api/stats', methods=['GET'])
def get_stats():
    user_id = request.args.get("user_id") or session.get("user_id")
    if not user_id: return jsonify({"balance": 0, "income": 0, "expense": 0})
    
    txs = Transaction.query.filter_by(user_id=user_id).all()
    income = sum(t.amount for t in txs if t.trans_type == "Income")
    expense = sum(t.amount for t in txs if t.trans_type == "Expense")
    return jsonify({
        "balance": income - expense,
        "income": income,
        "expense": expense
    })

@app.route('/api/ai/chat', methods=['POST'])
def ai_chat():
    data = request.json
    msg = data.get("message", "").lower()
    user_id = data.get("user_id") or session.get("user_id")
    
    props = Property.query.filter_by(user_id=user_id).all()
    txs = Transaction.query.filter_by(user_id=user_id).all()
    
    if "listing" in msg or "property" in msg:
        reply = f"You currently manage {len(props)} listings in your workspace. "
        available = len([p for p in props if p.status == "Available"])
        reply += f"Currently, {available} properties are Available and {len(props)-available} have been marked as Sold."
    elif "ledger" in msg or "financial" in msg or "money" in msg:
        income = sum(t.amount for t in txs if t.trans_type == "Income")
        expense = sum(t.amount for t in txs if t.trans_type == "Expense")
        reply = f"Financial Analysis Engine report: Total recorded Income is Rs. {income:,}, total operational Expenses are Rs. {expense:,}, yielding a net safe balance of Rs. {income-expense:,}."
    else:
        reply = "I am processing your workspace matrix. I can analyze financial ledger shifts, compute active-to-sold ratios, evaluate budgets, or track records inside your Google Sheets dynamically."
        
    return jsonify({"reply": reply})

if __name__ == '__main__':
    app.run(debug=True, port=5000)
