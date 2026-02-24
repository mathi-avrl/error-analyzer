# Flask
from flask import Flask, make_response, request, render_template

import orjson
import mechanics_ndb
import mechanics_jwt
# Logging
import logging

logging.basicConfig(
    format="%(asctime)s,%(msecs)d %(levelname)-8s [%(filename)s:%(lineno)d] %(message)s",
    datefmt="%Y-%m-%d:%H:%M:%S",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


app = Flask(__name__, template_folder='templates')
recording = False
@app.route("/", methods=["GET"])
def main_handler():
    """Serve the bot metrics dashboard"""
    return render_template('index.html')

@app.route("/record/start", methods=["POST"])
def start_recording():
    global recording
    recording = True
    return {"success": True, "recording": True}, 200
 

@app.route("/record/stop", methods=["POST"])
def stop_recording():
    global recording
    recording = False
    return {"success": True, "recording": False}, 200

@app.route("/api/get-bot-data", methods=["GET"])
def get_bot_data():
    """Fetch bot data from Datastore filtered by date and client name"""
    try:
        # Get date and client_name from query parameters
        selected_date = request.args.get('date', None)
        client_name = request.args.get('client_name', None)

        if not client_name:
            return orjson.dumps({'status': 'failed', 'message': 'Client name is required'}), 400, {
                'Content-type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        
        jwt_token = request.headers.get('Authentication', None)
        if jwt_token:
            status, payload = mechanics_jwt.verify_token_with_jwks(jwt_token)
            if not status:
                return {"status": "failed", "message": "Failed to authenticate, invalid token"}, 401

        bot_data = mechanics_ndb.get_bot_metrics(selected_date=selected_date, client_name=client_name)
 
        return orjson.dumps({'status': 'success', 'data': bot_data}), 200, {
            'Content-type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        }
    except Exception as e:
        logger.error(f"Error fetching bot data: {e}")
        return orjson.dumps({'status': 'failed', 'message': str(e)}), 500, {
            'Content-type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        }

@app.route("/store", methods=["GET","OPTIONS", "POST"])
def insert_data():
    
    if request.method == "OPTIONS":
        response = make_response()
        response.headers.add('Access-Control-Allow-Origin', "*")
        response.headers.add('Access-Control-Allow-Headers', "*")
        response.headers.add('Access-Control-Allow-Methods', "*")
        return response
    elif request.method == "POST":
        params = request.get_json(force=True)
        # Extract values from nested structure
        client_name = params.get('client_name', '')
        account_name = params.get('username', '')
        push_data = params.get('push_data', {})
        logging_obj = push_data.get('logging_obj', {})
        data = logging_obj.get('data', {})
        errors = data.get('errors', {})

        jwt_token = params.get('session_key', None)
        if jwt_token:
            status, payload = mechanics_jwt.verify_token_with_jwks(jwt_token)
            if not status:
                return {"status": "failed", "message": "Failed to authenticate, invalid token"}, 401
        
        # Safely extract caller_details
        caller_details = errors.get('caller_details', '')
        avrl_user_id = caller_details.split(':')[0] if isinstance(caller_details, str) and caller_details else ''
        
        # Convert error dictionary to JSON string
        error_message_str = orjson.dumps(errors).decode('utf-8') if errors else ''
        
        result = mechanics_ndb.update_datastore(
            client_name=client_name,
            account_name=account_name,
            avrl_user_id=avrl_user_id,
            error_message=error_message_str,
            # request_body=pricing_request
        )
        return orjson.dumps(result), 200, {'Content-type': 'application/json', 'Access-Control-Allow-Origin': '*'}
    else:
        return orjson.dumps({'error': 'Method not allowed'}), 405, {'Content-type': 'application/json', 'Access-Control-Allow-Origin': '*'}

@app.errorhandler(404)
def page_not_found(e):
    # Note that we set the 404 status explicitly
    return 'You are looking for something else', 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
