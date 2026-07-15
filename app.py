import os
import base64
import random
from flask import Flask, request, jsonify
from flask_bcrypt import Bcrypt
from flask_cors import CORS  # Frontend-Backend connection ke liye lazmi hai
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
# CORS enable kiya taake aapka HTML is backend se baat kar sake
CORS(app, supports_credentials=True)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ali_estate_secure_super_secret_key_2026")

# --- NEON.COM POSTGRESQL CONFIGURATION ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    'postgresql://neondb_owner:your_password@ep-some-endpoint.eastus2.azure.neon.tech/neondb?sslmode=require'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
bcrypt = Bcrypt(app)

# --- DATABASE MODELS ---
class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.String(100), primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

class Property(db.Model):
    __tablename__ = 'properties'
    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)
    title = db.Column(db.String(200))
    project_name = db.Column(db.String(200))
    type = db.Column(db.String(50))
    price = db.Column(db.Float)
    location = db.Column(db.String(200))
    owner_name = db.Column(db.String(100))
    owner_phone = db.Column(db.String(50))
    status = db.Column(db.String(50))
    owner_demand = db.Column(db.String(100))
    description = db.Column(db.Text)

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.BigInteger, primary_key=True)
    user_id = db.Column(db.String(100), nullable=False)
    property_id = db.Column(db.String(100))
    trans_type = db.Column(db.String(50))  # Income / Expense
    amount = db.Column(db.Float)
    category = db.Column(db.String(100))
    date = db.Column(db.String(50))

# Automatically create tables in Neon if they don't exist
with app.app_context():
    db.create_all()

# --- AUTH ENDPOINTS ---
@app.route('/api/auth/register', methods=['POST'])
def register():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password")
    
    if not email or not password:
        return jsonify({"message": "Missing email or password"}), 400
        
    if User.query.filter_by(email=email).first():
        return jsonify({"message": "User already exists"}), 400
        
    hashed_pw = bcrypt.generate_password_hash(password).decode('utf-8')
    user_id = base64.b64encode(email.encode()).decode()
    
    new_user = User(id=user_id, email=email, password=hashed_pw)
    db.session.add(new_user)
    db.session.commit()
    
    return jsonify({"user_id": user_id, "message": "Registered successfully"})

@app.route('/api/auth/login', methods=['POST'])
def login():
    data = request.json or {}
    email = data.get("email")
    password = data.get("password")
    
    user = User.query.filter_by(email=email).first()
    if user and bcrypt.check_password_hash(user.password, password):
        return jsonify({"user_id": user.id, "message": "Logged in successfully"})
        
    return jsonify({"message": "Invalid email or password"}), 401

# --- PROPERTIES API ---
@app.route('/api/properties', methods=['GET', 'POST'])
def handle_properties():
    user_id = request.args.get("user_id")
    if not user_id: 
        return jsonify({"message": "Unauthorized: user_id missing"}), 401
    
    if request.method == 'POST':
        data = request.json or {}
        if data.get("id"):  # Edit Property
            p_id = int(data.get("id"))
            prop = Property.query.filter_by(id=p_id, user_id=user_id).first()
            if prop:
                prop.title = data.get("title")
                prop.project_name = data.get("project_name")
                prop.type = data.get("type")
                prop.price = float(data.get("price") or 0)
                prop.location = data.get("location")
                prop.owner_name = data.get("owner_name")
                prop.owner_phone = data.get("owner_phone")
                prop.status = data.get("status")
                prop.owner_demand = data.get("owner_demand")
                prop.description = data.get("description")
                db.session.commit()
                return jsonify({"status": "updated", "id": p_id})
        else:  # New Property
            new_id = random.randint(100000, 999999)
            new_prop = Property(
                id=new_id,
                user_id=user_id,
                title=data.get("title"),
                project_name=data.get("project_name"),
                type=data.get("type"),
                price=float(data.get("price") or 0),
                location=data.get("location"),
                owner_name=data.get("owner_name"),
                owner_phone=data.get("owner_phone"),
                status=data.get("status", "Available"),
                owner_demand=data.get("owner_demand"),
                description=data.get("description")
            )
            db.session.add(new_prop)
            db.session.commit()
            return jsonify({"status": "created", "id": new_id})
            
    # GET Request
    properties = Property.query.filter_by(user_id=user_id).all()
    return jsonify([{
        "id": p.id, "title": p.title, "project_name": p.project_name, "type": p.type,
        "price": p.price, "location": p.location, "owner_name": p.owner_name,
        "owner_phone": p.owner_phone, "status": p.status, "owner_demand": p.owner_demand,
        "description": p.description
    } for p in properties])

@app.route('/api/properties/<int:pid>', methods=['DELETE'])
def delete_property(pid):
    user_id = request.args.get("user_id")
    if not user_id: return jsonify({"success": False}), 401
    
    prop = Property.query.filter_by(id=pid, user_id=user_id).first()
    if prop:
        db.session.delete(prop)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False}), 404

# --- TRANSACTIONS API ---
@app.route('/api/transactions', methods=['GET', 'POST'])
def handle_transactions():
    user_id = request.args.get("user_id")
    if not user_id: return jsonify([]), 401
    
    if request.method == 'POST':
        data = request.json or {}
        new_id = random.randint(100000, 999999)
        new_tx = Transaction(
            id=new_id,
            user_id=user_id,
            property_id=data.get("property_id"),
            trans_type=data.get("trans_type"),
            amount=float(data.get("amount") or 0),
            category=data.get("category"),
            date=data.get("date")
        )
        db.session.add(new_tx)
        db.session.commit()
        return jsonify({"status": "created", "id": new_id})
        
    txs = Transaction.query.filter_by(user_id=user_id).all()
    return jsonify([{
        "id": t.id, "property_id": t.property_id, "trans_type": t.trans_type,
        "amount": t.amount, "category": t.category, "date": t.date
    } for t in txs])

@app.route('/api/stats', methods=['GET'])
def get_stats():
    user_id = request.args.get("user_id")
    if not user_id: return jsonify({"balance": 0, "income": 0, "expense": 0})
    
    txs = Transaction.query.filter_by(user_id=user_id).all()
    income = sum(t.amount for t in txs if t.trans_type == "Income")
    expense = sum(t.amount for t in txs if t.trans_type == "Expense")
    return jsonify({
        "balance": income - expense,
        "income": income,
        "expense": expense
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
