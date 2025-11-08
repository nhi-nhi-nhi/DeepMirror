from datetime import datetime
from flask_login import UserMixin
from app import db, login_manager

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    pw_hash = db.Column(db.String(255), nullable=False)
    plan = db.Column(db.String(50), default="free")
    plan_until = db.Column(db.DateTime, nullable=True)
    tokens = db.Column(db.Integer, default=3, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

class ServiceUsage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    service = db.Column(db.String(64), index=True, nullable=False)
    window_start = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    uses = db.Column(db.Integer, nullable=False, default=0)

class StreamSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), index=True, nullable=False)
    service = db.Column(db.String(64), index=True, nullable=False)
    expires_at = db.Column(db.DateTime, nullable=False)
