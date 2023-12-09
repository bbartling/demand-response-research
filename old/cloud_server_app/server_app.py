from flask import Flask, request, jsonify, render_template
from flask_jwt_extended import JWTManager, jwt_required, create_access_token
from datetime import datetime, timezone, timedelta
import pytz
import logging
import os
from dateutil import parser
import secrets
import string

# Generate a random secret key with a specified length (e.g., 32 characters)
def generate_random_secret_key(length):
    alphabet = string.ascii_letters + string.digits + string.punctuation
    return ''.join(secrets.choice(alphabet) for _ in range(length))

# Example: Generate a 32-character random secret key
secret_key = generate_random_secret_key(32)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# User credentials (Consider a more secure storage in production)
users = {"user1": "password123"}

# Timezone and Flask setup
nyc_tz = pytz.timezone('America/New_York')
app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', secret_key)
jwt = JWTManager(app)

# In-memory storage
payload_data = {}

@app.route("/update/data", methods=["POST"])
@jwt_required()
def update_data():
    data = request.get_json()
    for key, value in data.items():
        # Parse the key as NYC time
        dt_key_nyc = parser.isoparse(key).astimezone(nyc_tz)
        payload_data[dt_key_nyc] = value['payload']
    return jsonify({"status": "success", "info": "Data updated successfully"}), 200


@app.route("/payload/current", methods=["GET"])
def get_current_payload():
    # Get the current time in NYC timezone
    nyc_now = datetime.now(nyc_tz)

    # Round down to the nearest quarter hour
    rounded_time = nyc_now - timedelta(minutes=nyc_now.minute % 15,
                                       seconds=nyc_now.second,
                                       microseconds=nyc_now.microsecond)

    # Try to find a payload for the rounded time
    payload = payload_data.get(rounded_time, None)
    rounded_time_iso = f"timeblock is {rounded_time.isoformat()}"
    response = {
        "status": "success",
        "info": rounded_time_iso if payload is not None else "timeblock is not found",
        "server_time_corrected": rounded_time_iso,
        "timezone": str(nyc_tz),
        "payload": payload if payload is not None else 0
    }

    return jsonify(response)

# Index Route
@app.route("/")
def index():
    return render_template("index_.html")

@app.route("/login", methods=["POST"])
def login_():
    if not request.is_json:
        return jsonify({"info": "Bad request"}), 400

    username = request.json.get("username", None)
    password = request.json.get("password", None)
    logger.info("LOGIN HIT: %s %s", username, password)

    if not username:
        return jsonify({"info": "Missing username parameter"}), 400
    if not password:
        return jsonify({"info": "Missing password parameter"}), 400

    if username in users and users[username] == password:
        access_token = create_access_token(identity=username)
        return jsonify(access_token=access_token), 200

    logger.info("Login successful for user: %s", username)
    return jsonify({"info": "Bad username or password"}), 401

# Main Function
if __name__ == "__main__":
    app.run(debug=False, port=5000)
