from flask import Flask, request, jsonify, render_template
from flask_caching import Cache
import pandas as pd
import datetime
import pytz
import sqlite3
from sqlalchemy import create_engine
from flask_jwt_extended import JWTManager, jwt_required, create_access_token
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

users = {
    'user1': 'password123'
}

tz = pytz.timezone('America/Chicago')

cache = Cache()
app = Flask(__name__)
app.config['JWT_SECRET_KEY'] = 'your_jwt_secret_key_here'
jwt = JWTManager(app)
cache.init_app(app, config={'CACHE_TYPE': 'SimpleCache'})

@app.route('/login', methods=['POST'])
def login_():
    if not request.is_json:
        return jsonify({"info": "Bad request"}), 400

    username = request.json.get('username', None)
    password = request.json.get('password', None)
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

@cache.cached(timeout=60, key_prefix='get_state_from_df')
def get_state_from_df():
    try:
        con = sqlite3.connect('payload_storage.db')
        df = pd.read_sql("SELECT * from payload_data", con)
        df.rename(columns={'index':'Time Block'}, inplace=True)
        df.set_index('Time Block')
        df['Time Block'] = pd.to_datetime(df['Time Block']).dt.round(freq='T')
        utc_time = datetime.datetime.utcnow()
        utc_time = utc_time.replace(tzinfo=pytz.UTC)   
        corrected_time = utc_time.astimezone(tz) 
        current_block = corrected_time.replace(minute = (corrected_time.minute - corrected_time.minute % 15), second=0, microsecond=0)
        current_block_no_tz = current_block.replace(tzinfo=None)

        # brute force through excel file to find a matching date
        for row in df.iterrows():
            if row[1][0].replace(second=0, microsecond=0) == current_block_no_tz:
                date = row[1][0].replace(second=0, microsecond=0)
                info = f'timeblock is {date}'
                response_obj = {'status':'success','info':info,'server_time_corrected':str(corrected_time),'timezone':str(tz),'payload':row[1][1]}
                logger.info(response_obj)   
                return jsonify(response_obj), 200 

        info = "timeblock not found"
        response_obj = {'status':'success','info':info,'server_time_corrected':str(corrected_time),'timezone':str(tz),'payload':0}
        logger.info(response_obj)   
        return jsonify(response_obj), 200   

    except Exception as error:
        err = f"Internal Server Error - {error}"
        response_obj = {'status':'fail','info':err,'server_time_corrected':str(corrected_time),'timezone':str(tz),'payload':0}
        logger.error(response_obj)   
        return jsonify(response_obj), 500 



@app.route('/payload/current', methods=['GET'])
def event_state_current():
    cache_key = 'get_state_from_df'  # This should match the key_prefix in the @cache decorator
    cached_value = cache.get(cache_key)
    if cached_value:
        logger.info("Retrieving data from cache.")
        return cached_value
    else:
        logger.info("Fetching data and updating cache.")
        return get_state_from_df()



@app.route('/update/data', methods=['POST'])
@jwt_required()
def json_payloader():
    try:
        r = request.json
        logger.info("Update Data Request: \n%s", r)
        df = pd.read_json(r).T

        engine = create_engine('sqlite:///payload_storage.db', echo=True)
        with engine.connect() as conn:
            sqlite_table = "payload_data"
            df.to_sql(sqlite_table, conn, if_exists='replace')

        response_obj = {
            'status': 'success',
            'info': 'parsed and saved successfully',
            'timezone_config': str(tz)
        }
        return jsonify(response_obj), 200

    except Exception as error:
        response_obj = {
            'status': 'fail',
            'info': f"Internal Server Error - {error}",
            'timezone_config': str(tz)
        }
        logger.error(response_obj)   
        return jsonify(response_obj), 500

@app.route('/')
def index():
    return render_template('index.html')

if __name__ == '__main__':
    #app.run(debug=True, port=5000, host='0.0.0.0')
    app.run(debug=False, port=5000)

