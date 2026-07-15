import os
import random
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)
# CORS enable kiya taake aapka HTML bina kisi security block ke connect ho sake
CORS(app)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "ali_estate_secure_super_secret_key_2026")

# --- NEON.COM POSTGRESQL CONFIGURATION ---
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get(
    'DATABASE_URL', 
    'postgresql://neondb_owner:your_password@ep-some-endpoint.eastus2.azure.neon.tech/neondb?sslmode=require'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- DATABASE MODELS ---
class Property(db.Model):
    __tablename__ = 'properties'
    id = db.Column(db.BigInteger, primary_key=True)
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
    property_id = db.Column(db.String(100))
    trans_type = db.Column(db.String(50))  # Income / Expense
    amount = db.Column(db.Float)
    category = db.Column(db.String(100))
    date = db.Column(db.String(50))

# Automatically create tables in Neon if they don't exist
with app.app_context():
    db.create_all()

# --- PROPERTIES API ---
@app.route('/api/properties', methods=['GET', 'POST'])
def handle_properties():
    if request.method == 'POST':
        data = request.json or {}
        if data.get("id"):  # Edit Property
            p_id = int(data.get("id"))
            prop = Property.query.filter_by(id=p_id).first()
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
    properties = Property.query.all()
    return jsonify([{
        "id": p.id, "title": p.title, "project_name": p.project_name, "type": p.type,
        "price": p.price, "location": p.location, "owner_name": p.owner_name,
        "owner_phone": p.owner_phone, "status": p.status, "owner_demand": p.owner_demand,
        "description": p.description
    } for p in properties])

@app.route('/api/properties/<int:pid>', methods=['DELETE'])
def delete_property(pid):
    prop = Property.query.filter_by(id=pid).first()
    if prop:
        db.session.delete(prop)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False}), 404

# --- TRANSACTIONS API ---
@app.route('/api/transactions', methods=['GET', 'POST'])
def handle_transactions():
    if request.method == 'POST':
        data = request.json or {}
        new_id = random.randint(100000, 999999)
        new_tx = Transaction(
            id=new_id,
            property_id=data.get("property_id"),
            trans_type=data.get("trans_type"),
            amount=float(data.get("amount") or 0),
            category=data.get("category"),
            date=data.get("date")
        )
        db.session.add(new_tx)
        db.session.commit()
        return jsonify({"status": "created", "id": new_id})
        
    txs = Transaction.query.all()
    return jsonify([{
        "id": t.id, "property_id": t.property_id, "trans_type": t.trans_type,
        "amount": t.amount, "category": t.category, "date": t.date
    } for t in txs])

@app.route('/api/stats', methods=['GET'])
def get_stats():
    txs = Transaction.query.all()
    income = sum(t.amount for t in txs if t.trans_type == "Income")
    expense = sum(t.amount for t in txs if t.trans_type == "Expense")
    return jsonify({
        "balance": income - expense,
        "income": income,
        "expense": expense
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
