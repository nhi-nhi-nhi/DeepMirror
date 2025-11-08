# config.py
import os, secrets
basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Dev default; in prod, set SECRET_KEY via env
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))

    # SQLite file lives next to config.py
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(basedir, "app.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    FREE_USES = int(os.getenv("FREE_USES", 3))
    FREE_WINDOW_MIN = int(os.getenv("FREE_WINDOW_MIN", 30))
    STREAM_SESSION_MIN = int(os.getenv("STREAM_SESSION_MIN", 1))

