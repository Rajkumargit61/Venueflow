from flask import Flask, send_from_directory, request, jsonify, session, render_template
from werkzeug.security import generate_password_hash, check_password_hash
import json
import os
import threading
import time
import requests
import pymongo
import mongomock
import xml.etree.ElementTree as ET
import qrcode
import base64
from io import BytesIO

app = Flask(__name__, static_folder='.')
app.secret_key = 'super_secret_venue_key'

# ---------- MONGODB SETUP ----------
try:
    mongo_uri = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
    print(f"Attempting to connect to MongoDB server at {mongo_uri}...")
    client = pymongo.MongoClient(mongo_uri, serverSelectionTimeoutMS=2000)
    client.server_info() # force connect to trigger exception if offline
    db = client.venueflow
    db_mode = "Production (MongoDB)"
except Exception as e:
    print(f"MongoDB connection failed ({e}). Falling back to MongoMock (In-Memory)...")
    client = mongomock.MongoClient()
    db = client.venueflow
    db_mode = "Testing (MongoMock)"

def init_mongo():
    if db.users.count_documents({"username": "admin"}) == 0:
        db.users.insert_one({
            "username": "admin",
            "password_hash": generate_password_hash("admin"),
            "role": "admin"
        })
    
    if db.venue_data.count_documents({"key": "live_state"}) == 0:
        default_state = {
            "football": {"home": "MNC", "away": "MUN", "score": "2 - 1", "time": "75:12", "status": "LIVE - 2nd Half"},
            "cricket": {"home": "IND", "away": "AUS", "score": "245/4", "time": "Overs: 42.1", "status": "LIVE - Innings 2"},
            "basketball": {"home": "LAL", "away": "BOS", "score": "108 - 104", "time": "Q4 02:15", "status": "LIVE - Q4"},
            "tennis": {"home": "ALC", "away": "DJO", "score": "2 - 0", "time": "Pts: 40 - 15", "status": "LIVE - Set 3"},
            "wait_times": {"restroom": "1 Min", "merch": "8 Min", "pizza": "15 Min"}
        }
        db.venue_data.insert_one({"key": "live_state", "value_json": json.dumps(default_state)})

# ---------- BACKGROUND API POLLING THREAD ----------
def sync_external_apis():
    """ Concurrently runs and fetches external scores for MongoDB synchronization. """
    with app.app_context():
        while True:
            try:
                doc = db.venue_data.find_one({"key": "live_state"})
                if doc:
                    state = json.loads(doc['value_json'])
                    
                    # 1. Fetch Timer for generic simulations
                    try:
                        r_time = requests.get('http://worldtimeapi.org/api/timezone/Etc/UTC', timeout=5)
                        if r_time.status_code == 200:
                            seconds = int(r_time.json()['datetime'][17:19])
                            state['football']['score'] = f"{2 + (seconds // 20)} - 1"
                            state['football']['time'] = f"75:{str(seconds).zfill(2)}"
                            state['basketball']['score'] = f"{100 + seconds} - {104 + (seconds // 2)}"
                            pts = [0, 15, 30, 40]
                            state['tennis']['time'] = f"Pts: {pts[(seconds // 15) % 4]} - 15"
                    except: pass # gracefully skip if generic time server fails
                    
                    # 2. Fetch Real-Time Cricket Scores from ESPN Cricinfo RSS
                    try:
                        r_cric = requests.get('http://static.cricinfo.com/rss/livescores.xml', timeout=5)
                        if r_cric.status_code == 200:
                            root = ET.fromstring(r_cric.content)
                            live_match_title = None
                            ipl_terms = ['mumbai', 'rajasthan', 'chennai', 'kolkata', 'delhi', 'punjab', 'gujarat', 'lucknow', 'bangalore', 'bengaluru', 'hyderabad', 'ipl']
                            
                            for item in root.findall('./channel/item'):
                                title = item.find('title').text
                                if any(term in title.lower() for term in ipl_terms):
                                    live_match_title = title
                                    break
                                    
                            if not live_match_title and root.find('./channel/item') is not None:
                                live_match_title = root.find('./channel/item').find('title').text
                                
                            if live_match_title:
                                state['cricket']['status'] = "LIVE - ESPN API"
                                state['cricket']['home'] = "LIVE"
                                state['cricket']['away'] = "IPL"
                                state['cricket']['score'] = live_match_title
                                state['cricket']['time'] = "Real-Time Update"
                    except Exception as e:
                        print("Cricket Fetch Error:", e)

                    # Update Mongo
                    db.venue_data.update_one({"key": "live_state"}, {"$set": {"value_json": json.dumps(state)}})
                    print(f"[{db_mode}] Pipeline Sync Complete -> Sent to UI")
            except Exception as e:
                print("Background Thread Fatal:", e)
                
            time.sleep(5)  # Poll APIs every 5 seconds

# ---------- ROUTES ----------
@app.route('/')
def route_home(): return render_template('home.html')

@app.route('/map')
def route_map(): return render_template('map.html')

@app.route('/order')
def route_order(): return render_template('order.html')

@app.route('/tickets')
def route_tickets():
    qr_b64 = None
    if session.get('username'):
        user_pass = f"VENUEFLOW_PASS_{session.get('username').upper()}_VIP"
        qr = qrcode.QRCode(version=1, box_size=10, border=4)
        qr.add_data(user_pass)
        qr.make(fit=True)
        img = qr.make_image(fill_color="white", back_color="#0f172a")
        
        buf = BytesIO()
        img.save(buf, format="PNG")
        qr_b64 = base64.b64encode(buf.getvalue()).decode('utf-8')
        
    return render_template('tickets.html', qr_code=qr_b64)

@app.route('/admin')
def route_admin(): return render_template('admin.html')

@app.route('/<path:path>')
def serve_static(path): return send_from_directory('.', path)

@app.route('/api/me', methods=['GET'])
def cur_user():
    user = session.get('username')
    return jsonify({"logged_in": bool(user), "username": user, "role": session.get('role')})

@app.route('/api/register', methods=['POST'])
def register():
    un, pw = request.json.get('username'), request.json.get('password')
    if not un or not pw: return jsonify({"success": False}), 400
    
    if db.users.find_one({"username": un}):
        return jsonify({"success": False, "message": "Username taken"}), 400
        
    db.users.insert_one({"username": un, "password_hash": generate_password_hash(pw), "role": "attendee"})
    session['username'] = un
    session['role'] = 'attendee'
    return jsonify({"success": True})

@app.route('/api/login', methods=['POST'])
def login():
    un, pw = request.json.get('username'), request.json.get('password')
    user = db.users.find_one({"username": un})
    
    if user and check_password_hash(user['password_hash'], pw):
        session['username'] = user['username']
        session['role'] = user['role']
        return jsonify({"success": True, "role": user['role']})
    return jsonify({"success": False, "message": "Invalid password"}), 401

@app.route('/api/logout', methods=['POST'])
def logout():
    session.clear()
    return jsonify({"success": True})

@app.route('/api/venue_data', methods=['GET'])
def get_venue_data():
    doc = db.venue_data.find_one({"key": "live_state"})
    return jsonify({"success": True, "data": json.loads(doc['value_json']) if doc else {}})

@app.route('/api/admin/update_data', methods=['POST'])
def update_venue_data():
    if session.get('role') != 'admin': return jsonify({"success": False}), 403
    new_state = request.json
    doc = db.venue_data.find_one({"key": "live_state"})
    if doc:
        current_state = json.loads(doc['value_json'])
        current_state['wait_times'] = new_state.get('wait_times', current_state['wait_times'])
        db.venue_data.update_one({"key": "live_state"}, {"$set": {"value_json": json.dumps(current_state)}})
    return jsonify({"success": True, "message": "Wait times deployed via MongoDB!"})

@app.route('/api/order', methods=['POST'])
def place_order():
    if not session.get('username'): return jsonify({"success": False}), 401
    items = str(request.json.get('items', []))
    res = db.orders.insert_one({"items": items, "total_price": 0.0, "status": "Preparing"})
    return jsonify({"success": True, "message": f"Order #{str(res.inserted_id)[:6]} placed successfully!"})

init_mongo()
threading.Thread(target=sync_external_apis, daemon=True).start()

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True, use_reloader=False)
