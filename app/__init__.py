from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from config import Config

app = Flask(__name__, static_folder='static')
app.config.from_object(Config)

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "auth.login"

from app.auth import auth_bp
app.register_blueprint(auth_bp)

from app import routes
from app.models import auth_models