import json
import os
from datetime import datetime, timedelta

from flask import Flask, render_template, request, jsonify, session, url_for, flash, send_file, send_from_directory, make_response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user
from pydantic import BaseModel, ValidationError, Field, Extra
from typing import Optional
from werkzeug.utils import redirect
from werkzeug.middleware.proxy_fix import ProxyFix
from flask_session import Session
import uuid
import uvicorn
import hypercorn.asyncio
import asyncio
from hypercorn.config import Config
import ssl
from asgiref.wsgi import WsgiToAsgi
from agent_chat import send_message, get_agents, end_conversation, update_document_status_and_session, setVar, \
    get_menu, setTAT, get_set_vars, update_set_var_status, call_login_api, callGetInfoAPI, pendingSetVar, \
    get_pending_set_vars, update_pendingsetvar_status, get_all_agents, add_new_agent, fetch_user_role, send_otp, \
    db as firestore_db
from manage_docs import upload, list_fileInfo, delete, download_file
from db_connection import getUserDetails
# from gemini import generate
from matching import getMatch, save_logs_as_excel
from flask_cors import CORS
from flask_talisman import Talisman
from flask_wtf.csrf import CSRFProtect
import logging
import base64

from cibil import cibil_regen

# Configure logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(levelname)s - %(message)s')
# Create a logger
logger = logging.getLogger(__name__)

# app = Flask(__name__, static_folder='aiml11')

# Configure the Flask secret through the FLASK_SECRET_KEY environment variable.
# # Secure Cookies
# app.config['SESSION_TYPE'] = 'filesystem'  # Using filesystem for session storage
# app.config['SESSION_FILE_DIR'] = '/tmp/flask_sessions'  # Define a secure directory for session files
# app.config['SESSION_PERMANENT'] = False  # Ensure cookies are not stored permanently
# app.config['SESSION_USE_SIGNER'] = True  # Prevents tampering
# app.config['SESSION_FILE_THRESHOLD'] = 100  # Limit the number of stored sessions
# app.config['SESSION_COOKIE_SECURE'] = True  # Ensure cookies are only sent over HTTPS
# app.config['SESSION_COOKIE_HTTPONLY'] = True  # No JavaScript access
# app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'  # Prevents CSRF attacks
# app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(minutes=30)  # Auto-expire sessions after 30 mins of inactivity
# app.wsgi_app = ProxyFix(app.wsgi_app,x_proto=1,x_host=1)


app = Flask(__name__, static_folder='aiml11')
asgi_app = WsgiToAsgi(app)
APP_SECRET_KEY = os.environ.get('FLASK_SECRET_KEY')
if not APP_SECRET_KEY:
    APP_SECRET_KEY = os.urandom(32)
    logger.warning("FLASK_SECRET_KEY is unset; using a temporary key for this process")

app.config.update(
    SECRET_KEY=APP_SECRET_KEY,
    SESSION_TYPE='filesystem',  # Using filesystem for session storage
    SESSION_FILE_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flask_sessions'),
    SESSION_PERMANENT=False,  # Ensure cookies are not stored permanently
    SESSION_USE_SIGNER=True,  # Prevents tampering
    SESSION_FILE_THRESHOLD=100,  # Limit the number of stored sessions
    SESSION_COOKIE_SECURE=False,  # Allow cookies over HTTP for local dev
    SESSION_COOKIE_HTTPONLY=True,  # No JavaScript access
    SESSION_COOKIE_SAMESITE='Lax',  # Lax works for local dev redirects
    PERMANENT_SESSION_LIFETIME=timedelta(minutes=30)  # Session lifetime
)


@app.after_request
def force_strict_samesite(response):
    response.headers.pop('Server', None)
    return response



# Initialize session
Session(app)


# Ensure the session directory has secure permissions
_session_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flask_sessions')
os.makedirs(_session_dir, exist_ok=True)
logger.debug("SAME SITE %s", app.config['SESSION_COOKIE_SAMESITE'])
logger.debug("COOKIE_HTTPONLY %s", app.config['SESSION_COOKIE_HTTPONLY'])
logger.debug("COOKIE_SECURE %s", app.config['SESSION_COOKIE_SECURE']) 
# # Secure Cookies
# app.config['SESSION_TYPE'] = 'filesystem'
# app.config['SESSION_COOKIE_SECURE'] = True
# app.config['SESSION_COOKIE_HTTPONLY'] = True  # No JavaScript access
# app.config['SESSION_COOKIE_SAMESITE'] = 'Strict'  # Prevents CSRF attacks
# app.config['SESSION_PERMANENT'] = False
# app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
# Session(app)



login_manager = LoginManager(app)
login_manager.login_view = 'login'

BUCKET_NAME = 'cbstestdata'


PROJECT_NAME = "cbsdocs"
csrf = CSRFProtect(app)

CORS(app, resources={r"../aiml11/static/firebaseConfig.json": {"origins": "*"}})

talisman = Talisman(
    app,
    force_https=False,
    content_security_policy={
        'default-src': ['https://10.199.14.108',
        'https://localhost:8411'
        ],
        'connect-src': [
            "'self'",
            'https://firestore.googleapis.com',  # Allow Firebase Firestore API
            'https://securetoken.googleapis.com',  # Allow token exchanges
        ],
        'img-src': ["'self'", 'data:'],
        'script-src': [
            "'self'",
            'https://10.199.14.108:8411',
            'https://www.gstatic.com',
            'https://www.googleapis.com',
            'https://10.250.54.142:7099',
            'https://localhost:8411',   ],
        'style-src': [
            "'self'",
            'https://fonts.googleapis.com',
        ],
        'font-src': [
            "'self'",
            'https://fonts.gstatic.com',
        ],
        # LIVE
        # 'object-src': ["'none'"],
        # 'frame-src': ['https://10.199.14.108:8411'],
        # 'frame-ancestors': ['https://10.199.14.108:8411'],
        # 'form-action': ["'self'"],

        # LOCAL
        'object-src': '\'self\'',
        'frame-src': '\'self\'',
        'frame-ancestors': '\'self\'',
        'form-action': '\'self\'',
    },
    frame_options='DENY',
    referrer_policy='strict-origin-when-cross-origin',
    permissions_policy={
        'accelerometer': '()',
        'camera': '()',
        'microphone': '()',
    }
)

class User(UserMixin):
    users = {}  # This will simulate a user database (can be replaced with a real database query)

    def __init__(self, id, username, initializer, name, role):
        self.id = id
        self.username = username
        self.initializer = initializer
        self.name = name
        self.role = role

    def get_id(self):
        return str(self.id)

    @classmethod
    def get(cls, user_id):
        # Simulate retrieving a user by ID from the "database"
        return cls.users.get(user_id)

    @classmethod
    def create(cls, id, username, initializer, name, role):
        # Create and store a new user (simulating database save)
        user = cls(id, username, initializer, name, role)
        cls.users[id] = user
        return user


def load_users_from_json():
    with open('users.json', 'r') as file:
        users = json.load(file)
    return users


users_data = load_users_from_json()

json_file_path = "./users.json"


def get_user_by_username(username):
    # call_login_api(username, password)
    for user_data in users_data:
        
        if user_data['username'] == username:
            return User(user_data['id'], user_data['username'], user_data['password'], user_data['name'],
                        user_data['role'])

    return


@login_manager.user_loader
def load_user(user_id):
    for user_data in users_data:

        if str(user_data['id']).strip() == str(user_id).strip():
            return User(user_data['id'], user_data['username'], user_data['password'], user_data['name'],
                        user_data['role'])
    return None

# @login_manager.user_loader
# def load_user(user_id):
#     global users_data  
#     for user_data in users_data:
#         if str(user_data['id']).strip() == str(user_id).strip():
#             # Remove user from users_data once logged in
#             users_data = [u for u in users_data if u['id'] != user_id]
#             return User(user_data['id'], user_data['username'], user_data['password'], user_data['name'], user_data['role'])
#     return None


# --------------------- Helper Function ---------------------
def set_session(user):
    """
    Clears the old session and sets new session values.
    """
    session.clear()
    session['session_id'] = str(uuid.uuid4())  # Assign a new session ID
    session['username'] = user.username
    session['name'] = user.name
    session['role'] = user.role
    session['id'] = user.id
    session['ip'] = request.remote_addr  # Bind session to user IP
    session.modified = True


# ---------------- Secure Session Decorator ----------------
def secure_route(route_func):
    """
    Ensures session is valid and bound to the user's IP.
    """
    @wraps(route_func)
    def wrapped(*args, **kwargs):
        if 'username' not in session or session.get('ip') != request.remote_addr:
            logger.warning(f"Session hijacking attempt detected! IP mismatch for user {session.get('username')}")
            session.clear()
            return redirect(url_for('login'))
        return route_func(*args, **kwargs)
    return wrapped

""" ----------------- set routes ---------------------- """




@app.route('/aiml11/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        initializer = request.form.get('initializer') or request.form.get('password')
        otp = request.form.get('otp')
        logger.debug("In Login %s")
        user = get_user_by_username(username)
        logger.debug("user %s",user)
        sent_otp = session.get('sent_otp', "")  # Retrieve stored OTP from session

        if user:
            logger.debug("IN IFF %s")
            set_session(user)
            if user.role == "agent":
                if user.initializer == initializer:
                    login_user(user)
                    return redirect(url_for('agent_dashboard'))
            elif user.role == "user":
                if user.initializer == initializer:
                    login_user(user)                                     
                return redirect(url_for('index'))
            elif user.role == "checker":
                if user.initializer == initializer:
                    login_user(user)
                return redirect(url_for('bank_staff_dashboard'))
            elif user.role == "admin":
                if user.initializer == initializer:
                    login_user(user)
                return redirect(url_for('admin_portal'))
        else:
            logger.debug("In ELSE %s")
            if otp:
                
                if sent_otp == otp:
                    return redirect(url_for('bank_staff_dashboard'))
            else:
                
                users = call_login_api(username, initializer)
                data = json.loads(users)
                logger.debug("Response data %s", data.get('Result'))
                try:
                    if data.get('Result') == 'SUCCESS':
                        
                        mobile_number = getUserDetails(data.get('EmployeeNumber'))
                       
                         # Add user to session
                        user = User(
                            id=data.get('EmployeeNumber'),
                            username=username,
                            initializer=initializer,
                            name=data.get('CName'),
                            role=data.get('Designation')
                        )

                        users_data.append({
                            'id': data.get('EmployeeNumber'),
                            'username': username,
                            'password': initializer,
                            'name': data.get('CName'),
                            'role': data.get('Designation')
                        })

                        login_user(user)
                        set_session(user)
                        
                        if fetch_user_role(str(username).strip()).strip() == "agent":
                            return redirect(url_for('agent_dashboard'))
                        elif fetch_user_role(str(username).strip()).strip() == "checker":
                            logger.debug("IN CHECKER %s",mobile_number)
                            response = send_otp(mobile_number)
                            logger.debug("send_otp %s", response["otp"])
                            if response["success"]:
                                session['sent_otp'] = response["otp"]  
                            return render_template('home.html', success=True, otp=otp)
                        else:
                            logger.debug("INDEX ELSE %s")
                            return redirect(url_for('index'))
                except Exception as e:
                    logger.debug(f"Error occurred: {e}")

        flash('Login Unsuccessful. Please check username and password', 'danger')
    return render_template('home.html')


@app.route('/aiml11/logout', methods=['POST'])
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('login'))


@app.route('/aiml11/index')
@login_required
def index():
    if 'username' not in session or session.get('ip') != request.remote_addr:
        session.clear()
        return redirect(url_for('login'))
    user_data = {
        "username": session.get('username', 'Guest'),
        "name": session.get('name', 'Guest'),
        "role": session.get('role', 'User'),
        "id": session.get('id', 'User_id')
    }
    # username = session.get('username', 'Guest')
    # name = session.get('name', 'Guest')
    # role = session.get('role', 'User')
    # id = session.get('id', 'User_id')
    logger.debug("send_otp %s",user_data["username"])
    return render_template('index.html', user_data=user_data)

@app.route('/aiml11/workflow')
def workflow():
    user_data = {
        "username": session.get('username', 'Guest'),
        "name": session.get('name', 'Guest'),
        "role": session.get('role', 'User'),
        "id": session.get('id', 'User_id')
    }
    logger.debug("workflow page accessed by %s", user_data["username"])
    return render_template('workflow.html', user_data=user_data)


@app.route('/aiml11/workflow/submit', methods=['POST'])
def workflow_submit():
    if 'username' not in session or session.get('ip') != request.remote_addr:
        session.clear()
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid workflow data"}), 400

        fields = ('operation', 'requirement', 'parameter', 'authority')
        if any(not isinstance(data.get(field), str) for field in fields):
            return jsonify({"status": "error", "message": "All fields must be strings"}), 400

        operation, requirement, parameter, authority = (data[field].strip() for field in fields)

        if not all([operation, requirement, parameter, authority]):
            return jsonify({"status": "error", "message": "All fields are required"}), 400

        entry = {
            "operation": operation,
            "requirement": requirement,
            "parameter": parameter,
            "authority": authority,
            "created_by": session.get('username'),
            "created_at": datetime.utcnow().isoformat() + "Z"
        }
        _, document_ref = firestore_db.collection('workflow_menu').add(entry)
        entry['id'] = document_ref.id
        logger.info("Workflow entry saved to Firestore: %s", document_ref.id)
        return jsonify({
            "status": "success",
            "message": "Workflow submitted successfully",
            "entry": entry
        }), 201
    except Exception as e:
        logger.exception("workflow_submit Firestore write failed")
        return jsonify({"status": "error", "message": "Unable to save workflow entry"}), 500


@app.route('/aiml11/workflow/entries', methods=['GET'])
def workflow_entries():
    if 'username' not in session or session.get('ip') != request.remote_addr:
        session.clear()
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    try:
        documents = firestore_db.collection('workflow_menu').where(
            'created_by', '==', session.get('username')
        ).stream()
        entries = []
        for document in documents:
            entry = document.to_dict()
            entry['id'] = document.id
            entries.append(entry)
        return jsonify({"status": "success", "entries": entries})
    except Exception as e:
        logger.exception("workflow_entries Firestore read failed")
        return jsonify({"status": "error", "message": "Unable to load workflow entries"}), 500


@app.route('/aiml11/workflow/edit/<document_id>', methods=['PUT'])
def workflow_edit(document_id):
    if 'username' not in session or session.get('ip') != request.remote_addr:
        session.clear()
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    try:
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            return jsonify({"status": "error", "message": "Invalid workflow data"}), 400

        fields = ('operation', 'requirement', 'parameter', 'authority')
        if any(not isinstance(data.get(field), str) for field in fields):
            return jsonify({"status": "error", "message": "All fields must be strings"}), 400

        updated_fields = {field: data[field].strip() for field in fields}
        if not all(updated_fields.values()):
            return jsonify({"status": "error", "message": "All fields are required"}), 400

        document_ref = firestore_db.collection('workflow_menu').document(document_id)
        document = document_ref.get()
        if not document.exists:
            return jsonify({"status": "error", "message": "Workflow entry not found"}), 404
        existing_entry = document.to_dict()
        if existing_entry.get('created_by') != session.get('username'):
            return jsonify({"status": "error", "message": "Forbidden"}), 403

        document_ref.update(updated_fields)
        existing_entry.update(updated_fields)
        existing_entry['id'] = document_id
        return jsonify({"status": "success", "message": "Workflow entry updated", "entry": existing_entry})
    except Exception:
        logger.exception("workflow_edit Firestore update failed")
        return jsonify({"status": "error", "message": "Unable to update workflow entry"}), 500

 
@app.route('/aiml11/documents')
def documents():
    return render_template('documents.html')


@app.route('/aiml11/set_var_list')
def setVarList():
    if 'username' not in session or session.get('ip') != request.remote_addr:
        session.clear()
        return redirect(url_for('login'))

    user_data = {
        "username": session.get('username', 'Guest'),
        "name": session.get('name', 'Guest'),
        "role": session.get('role', 'User'),
        "id": session.get('id', 'User_id')
    }

    return render_template('set_var_list.html', user_data=user_data)


@app.route('/aiml11/pending_set_var')
def pendingSetVars():
    if 'username' not in session or session.get('ip') != request.remote_addr:
        session.clear()
        return redirect(url_for('login'))


    user_data = {
        "username": session.get('username', 'Guest'),
        "name": session.get('name', 'Guest'),
        "role": session.get('role', 'User'),
        "id": session.get('id', 'User_id')
    }
    return render_template('pending_setvar.html', user_data=user_data)


@app.route('/aiml11/bank_staff_dashboard')
def bank_staff_dashboard():
    if 'username' not in session or session.get('ip') != request.remote_addr:
        session.clear()
        return redirect(url_for('login'))

    global users_data
    logger.debug("bank_staff_dashboard %s")
    user_data = {
        "username": session.get('username', 'Guest'),
        "name": session.get('name', 'Guest'),
        "role": session.get('role', 'User'),
        "id": session.get('id', 'User_id')
    }
    users_data = [u for u in users_data if u['id'] != id]
    return render_template('bank_staff_dashboard.html', user_data=user_data)


@app.route('/aiml11/admin_portal')
def admin_portal():
    if 'username' not in session or session.get('ip') != request.remote_addr:
        session.clear()
        return redirect(url_for('login'))

    user_data = {
        "username": session.get('username', 'Guest'),
        "name": session.get('name', 'Guest'),
        "role": session.get('role', 'User'),
        "id": session.get('id', 'User_id')
    }

    return render_template('admin_portal.html', user_data=user_data)


@app.route('/aiml11/agent_dashboard')
@login_required
def agent_dashboard():
    if 'username' not in session or session.get('ip') != request.remote_addr:
        session.clear()
        return redirect(url_for('login'))

    user_data = {
        "username": session.get('username', 'Guest'),
        "name": session.get('name', 'Guest'),
        "role": session.get('role', 'User'),
        "id": session.get('id', 'User_id')
    }

    return render_template('agent_dashboard.html', user_data=user_data)


@app.route('/aiml11/agent_list_view')
@login_required
def agent_list_view():
    if 'username' not in session or session.get('ip') != request.remote_addr:
        session.clear()
        return redirect(url_for('login'))

    user_data = {
        "username": session.get('username', 'Guest'),
        "name": session.get('name', 'Guest'),
        "role": session.get('role', 'User'),
        "id": session.get('id', 'User_id')
    }

    return render_template('agent_list.html', user_data=user_data)


"""-------------- API --------------------------"""

"""
* This API is used to generate answers from uploaded Excel documents.
* 'Menu' refers to the folder in the bucket from which the answer should be extracted.
"""


@app.route('/aiml11/getAnswer', methods=['POST'])
def getAnswer():
    try:
        username = session.get('username', 'Guest')
        user_id = session.get('id', 'User_id')
        data = request.get_json()
        query = data.get("query")
        menu = data.get("menu")

        print("data----------", data)
        print("query---------", query)
        if data.get("menu_type") =="claps_flow":
            print("CLASP FLOW WORKING")
            
            clap_id = data.get("clap_id")
            lap_id = data.get("lap_id")

            print("clap_id====", clap_id)
            print("lap_id====", lap_id)
            if clap_id:
                cibil_res = "CLAPS id validated"
                
            if(clap_id and lap_id):
                req_time = datetime.utcnow()
                cibil_res = cibil_regen(clap_id , lap_id, user_id, username, req_time)
                
                print("cibil_res----", cibil_res)
    
            # cibil_res = "CLAPS id validated"
            response = getMatch(cibil_res, menu, username, user_id)
        else:
            response = getMatch(query, menu, username, user_id)
            print("response---------", response)
        
        return response
    except Exception as e:
        print(e)
        return jsonify({"status": "false", "answer": "Failed fetch result, Do you want to connect to agent?",
                        "agentTransfer": "false", "error": e}), 500



"""
* This API is used to Send message in Agent Chat, to Firestore DB.
"""


@app.route('/aiml11/send_message', methods=['POST'])
def sendMessage():
    try:

        return send_message(request)
    except Exception as e:

        return jsonify({"error": str(e)}), 500


"""
* This API is used to get the available agents for connecting the user
"""


@app.route('/aiml11/available_agent', methods=['POST'])
def available_agent():
    try:
        return get_agents()
    except Exception as e:
        return "false"


"""
* This API is used to get the all the agents, Used in admin Dashboard for listing all agents
"""


@app.route('/aiml11/getAllAgents', methods=['POST'])
def getAllAgents():
    try:
        return get_all_agents()
    except Exception as e:
        return "false"


"""
* This API is used to add new agent, used in admin Dashboard
"""


@app.route('/aiml11/addNewAgent', methods=['POST'])
def addAgent():
    try:
        data = request.get_json()
        return add_new_agent(data)
    except Exception as e:
        return "false"


"""
* This API is used to get end conversation, used in Agent dashboard
"""


@app.route('/aiml11/end_conversation', methods=['POST'])
def conversation_end():
    data = request.get_json()
    agent_id = data.get("agent_id")
    user_id = data.get("user_id")
    return end_conversation(agent_id, user_id)


"""
* This API is used to update agent status, used in Agent dashboard
"""


@app.route('/aiml11/agent_status', methods=['POST'])
def agent_status():
    data = request.get_json()
    agent_id = data.get("agent_id")
    status = data.get("status")

    return update_document_status_and_session(agent_id, status)


"""
* This API is used to update the setvar from agent side, used in Agent dashboard
"""

@app.route('/aiml11/setvar', methods=['POST'])
def set_var():
    data = request.get_json()
    return setVar(data)

"""
* This API is used to update the SetTAT to user from agent side, used in Agent dashboard
"""


@app.route('/aiml11/setTAT', methods=['POST'])
def set_tats():
    data = request.get_json()
    return setTAT(data)

"""
* Maker approver
"""

@app.route('/aiml11/cibil_regen', methods=['POST'])
def set_cibilregen():
    data = request.get_json()

    date = data.get('date')
    status = data.get('status')
    cibilId = data.get('id')
    cibilRejenRes =  update_set_var_status(date, cibilId, status)
    return cibilRejenRes
    
"""
* This API is used to list all menu, used in Branch User
"""


@app.route('/aiml11/get_menu', methods=['POST'])
def get_menu_options():
    return get_menu()


"""
* This API is used to list all setVar
"""


class GetSetVarRequest(BaseModel):
    date: str = Field(..., pattern=r"^\d{8}$")  # Enforce YYYYMMDD format
    agent_id: Optional[str] = None  # ? Optional agent_id

    class Config:
        extra = Extra.forbid  # ?? Forbid extra fields


@app.route('/aiml11/get_set_var', methods=['POST'])
def get_set_var():
    try:
        data = request.get_json()
        validated_data = GetSetVarRequest(**data)  # ? Strict Validation
        logger.debug("This is the validated data: %s", validated_data)
        # ? Call function with only validated values
        return get_set_vars(validated_data.date, validated_data.agent_id)

    except ValidationError as e:
        return jsonify({"error": "Invalid input", "details": e.errors()}), 400  # ?? Return 400 for extra fields


"""
* This API is used to list all pending SetVAR, used in Agent Dashboard
"""


@app.route('/aiml11/get_pending_set_var', methods=['POST'])
def get_pending_set_var():
    data = request.get_json()
    date = data.get('date')
    agent_id = data.get('agent_id')
    return get_pending_set_vars(date, agent_id)


"""
* This API is used to Update Setvar to finacle, used in Bank Dashboard
"""

# ? Define Schema with Strict Validation
class UpdateFIRequest(BaseModel):
    FI_REQUEST_ID: str
    CX_Reference_number: str
    chanel: str
    menu: str
    module_Name: str
    subModule_Name: str  # ? Corrected from subMod ule_Name to subModule_Name
    variableName: str
    variableValue: str
    expDate: str = Field(..., pattern=r"^\d{2}-\d{2}-\d{4}$")  # Ensure date format DD-MM-YYYY

    class Config:
        extra = Extra.forbid  # ?? Reject extra fields


@app.route('/aiml11/updateFI', methods=['POST'])
def updateFI():
    try:
        data = request.get_json()
        validated_data = UpdateFIRequest(**data)  # ? Strict Validation

        return callGetInfoAPI(validated_data.dict())  # ? Only pass validated data

    except ValidationError as e:
        return jsonify({"error": "Invalid input", "details": e.errors()}), 400


"""
* This API is used to Update Setvar status in firebase, used in Bank Dashboard
"""


@app.route('/aiml11/update_setvar_status', methods=['POST'])
def update_setvar():
    data = request.get_json()
    date = data.get('date')
    status = data.get('status')
    id = data.get('id')
    return update_set_var_status(date, id, status)


"""
* This API is used to Update Pending Setvar status in firebase, used in Agent Dashboard
"""


@app.route('/aiml11/update_pending_setvar_status', methods=['POST'])
def update_pending_setvar():
    data = request.get_json()
    date = data.get('date')
    status = data.get('status')
    id = data.get('id')
    return update_pendingsetvar_status(date, id, status)


"""
* This API is used to Upload documents to GCP Bucket
"""


@app.route('/aiml11/upload_bucket', methods=['POST'])
def upload_bucket():
    file = request.files["file"]
    user_doc_date = request.form.get("doc_date")

    user_id = ""
    if user_doc_date != "":
        user_id = request.form.get("user_id")
    if file.filename == "":
        return "No selected file", 400

    bucket_name = BUCKET_NAME

    file_name = file.filename

    if user_doc_date != "":
        result = upload(
            bucket_name, PROJECT_NAME + "/agent_docs/" + user_doc_date + "/" + user_id, file.read(), file.content_type,
            file_name)
    else:
        folder = request.form.get("menu")
        result = upload(
            bucket_name, PROJECT_NAME + "/" + folder, file.read(), file.content_type, file_name)
    return result


"""
* This API is used to download documents from GCP Bucket
"""


@app.route('/aiml11/download_file', methods=['POST'])
def download_file_bucket():
    data = request.get_json()
    file_name = data.get("file_name")
    return download_file(BUCKET_NAME, file_name)


"""
* This API is used to List  documents from GCP Bucket
"""


@app.route('/aiml11/document/list', methods=['POST'])
def list_files_bucket():
    data = request.get_json()
    user_doc = data.get("user_doc")
    return list_fileInfo(BUCKET_NAME, PROJECT_NAME + "/" + user_doc)


"""
* This API is used to Upload delete docs from GCP Bucket
"""


@app.route('/aiml11/document/delete', methods=['POST'])
def delete_file_bucket():
    data = request.get_json()
    FILE_NAME = data.get('fileName')
    return delete(BUCKET_NAME, PROJECT_NAME, FILE_NAME)


"""
* This API is used to Update Setvar into Pending table from agent is not available
"""


@app.route('/aiml11/uploadPendingSetVar', methods=['POST'])
def uploadPendingSetVar():
    data = request.get_json()
    return pendingSetVar(data)


"""
* This API is used to download Chat log
"""

@app.route('/aiml11/download_log', methods=['POST'])
def download_log():
    try:
        # Generate log files
        agent_logs_file, chatbot_logs_file = save_logs_as_excel()

        # Parse request data
        data = request.get_json()
        filename = data.get('filename')

        if not filename:
            return jsonify({"status": "error", "message": "Filename is required"}), 400

        # Check if the requested file exists
        if filename not in [agent_logs_file, chatbot_logs_file]:
            return jsonify({"status": "error", "message": "File not found"}), 404

        # Send the file for download
        return send_file(filename, as_attachment=True)

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# Create an SSL context
context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
context.options |= ssl.OP_NO_SSLv2
context.options |= ssl.OP_NO_SSLv3
context.minimum_version = ssl.TLSVersion.TLSv1_2
context.maximum_version = ssl.TLSVersion.TLSv1_3
context.set_ciphers('ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256')
context.set_ecdh_curve('secp384r1')
context.load_cert_chain(certfile='cert.pem', keyfile='cert.pem')
ciphers = ('ECDHE-ECDSA-AES256-GCM-SHA384:''ECDHE-RSA-AES256-GCM-SHA384:''ECDHE-ECDSA-CHACHA20-POLY1305:''ECDHE-RSA-CHACHA20-POLY1305:''ECDHE-ECDSA-AES128-GCM-SHA256:''ECDHE-RSA-AES128-GCM-SHA256:')

@app.after_request
def secure_headers(response):
    if 'Set-Cookie' in response.headers:
        # Replace any existing SameSite value with Strict
        cookies = response.headers.getlist('Set-Cookie')
        new_cookies = []
        for cookie in cookies:
            new_cookie = cookie.replace('SameSite=Lax', 'SameSite=Strict')
            new_cookie = new_cookie.replace('SameSite=None', 'SameSite=Strict')
            new_cookies.append(new_cookie)
        response.headers.set('Set-Cookie', new_cookies)
    return response

@app.route('/set_cookie')
def set_cookie():
    response = make_response("Cookie Set")
    response.set_cookie(
        'session',
        str(uuid.uuid4()),
        secure=True,
        httponly=True,
        samesite='Strict'
    )
    return response

@app.after_request
def add_cache_control(response):
    response.headers['Cache-Control'] = 'no-store'
    response.headers['Server'] = ''
    return response

if __name__ == '__main__':   
    app.config.update(
        SECRET_KEY=APP_SECRET_KEY,
        SESSION_TYPE='filesystem',
        SESSION_FILE_DIR=os.path.join(os.path.dirname(os.path.abspath(__file__)), 'flask_sessions'),
        SESSION_PERMANENT=False,
        SESSION_USE_SIGNER=True,
        SESSION_FILE_THRESHOLD=100,
        SESSION_COOKIE_SECURE=False,  # Allow cookies over HTTP for local dev
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=30)
    )

    logger.debug(f"COOKIE_SECURE: {app.config['SESSION_COOKIE_SECURE']}")

    app.run(host='0.0.0.0', port=8411, debug=False)
    # uvicorn.run(asgi_app, host="0.0.0.0", port=8411, ssl_ciphers = ciphers, ssl_keyfile="cert.pem", ssl_certfile="cert.pem", server_header=False, log_level="info")
    # asyncio.run(hypercorn.asyncio.serve(asgi_app, config))
