from datetime import datetime, timedelta
from functools import wraps
from flask import current_app, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from app import db
from app.models.auth_models import ServiceUsage, StreamSession
# helper to get/cleanup the latest stream session

def _get_active_stream_session(user_id, service):
    now = datetime.utcnow()
    sess = (StreamSession.query
            .filter_by(user_id=user_id, service=service)
            .order_by(StreamSession.expires_at.desc())
            .first())
    if sess and sess.expires_at <= now:
        # clean up expired session so it can't be re-used
        db.session.delete(sess)
        db.session.commit()
        return None
    return sess

def is_json_request():
    return request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"

def webcam_action_and_flag():
    """
    Returns (is_webcam, action) where action in {"start_or_frame", "stop"}.
    Default action is start_or_frame to treat frames as part of an active session.
    """
    try:
        if request.is_json:
            j = request.get_json(silent=True) or {}
            if j.get("source") == "webcam":
                action = j.get("action", "start_or_frame")
                return True, ("stop" if action == "stop" else "start_or_frame")
    except Exception:
        pass
    return False, "start_or_frame"


def is_subscribed(user):
    return bool(user and user.plan in ("plus-monthly","plus-annual")
                and user.plan_until and user.plan_until > datetime.utcnow())

def enforce_quota(service_name: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # 0) NEVER run the endpoint if not logged in
            if not current_user.is_authenticated:
                if is_json_request():
                    return jsonify({"error": "auth_required"}), 401
                return redirect(url_for("auth.login"))

            if is_subscribed(current_user):
                return fn(*args, **kwargs)

            FREE_USES = int(current_app.config.get("FREE_USES", 5))
            FREE_WINDOW_MIN = int(current_app.config.get("FREE_WINDOW_MIN", 30))
            STREAM_SESSION_MIN = int(current_app.config.get("STREAM_SESSION_MIN", 5))
            now = datetime.utcnow()

            is_webcam, action = webcam_action_and_flag()

            if is_webcam:
                now = datetime.utcnow()

                # STOP request: expire immediately
                if action == "stop":
                    sess = (StreamSession.query
                            .filter_by(user_id=current_user.id, service=service_name)
                            .order_by(StreamSession.expires_at.desc())
                            .first())
                    if sess:
                        sess.expires_at = now  # expire now
                        db.session.commit()
                    return fn(*args, **kwargs)

                # Active session? allow frame, DO NOT touch expires_at
                sess = _get_active_stream_session(current_user.id, service_name)
                if sess:
                    return fn(*args, **kwargs)

                # No active session -> need to consume ONE use and start a new session
                window = (ServiceUsage.query
                          .filter_by(user_id=current_user.id, service=service_name)
                          .order_by(ServiceUsage.window_start.desc())
                          .first())

                if (not window) or (now - window.window_start > timedelta(minutes=FREE_WINDOW_MIN)):
                    window = ServiceUsage(
                        user_id=current_user.id, service=service_name,
                        window_start=now, uses=0
                    )
                    db.session.add(window);
                    db.session.commit()

                if window.uses >= FREE_USES:
                    retry_in = (window.window_start + timedelta(minutes=FREE_WINDOW_MIN)) - now
                    mins_left = max(0, int(retry_in.total_seconds() // 60))
                    if is_json_request():
                        return jsonify({"error": "free_quota_exceeded",
                                        "retry_in_minutes": mins_left}), 429
                    flash(f"Free quota reached. Try again in ~{mins_left} minutes.", "warning")
                    return redirect(url_for("index"))

                # consume one use and start fixed-length session
                window.uses += 1;
                db.session.commit()
                ttl_min = min(STREAM_SESSION_MIN, FREE_WINDOW_MIN)
                new_sess = StreamSession(user_id=current_user.id,
                                         service=service_name,
                                         expires_at=now + timedelta(minutes=ttl_min))
                db.session.add(new_sess);
                db.session.commit()
                return fn(*args, **kwargs)

            # 2) Non-stream path: 1 call = 1 use
            window = (ServiceUsage.query
                      .filter_by(user_id=current_user.id, service=service_name)
                      .order_by(ServiceUsage.window_start.desc())
                      .first())
            if (not window) or (now - window.window_start > timedelta(minutes=FREE_WINDOW_MIN)):
                window = ServiceUsage(user_id=current_user.id, service=service_name,
                                      window_start=now, uses=0)
                db.session.add(window); db.session.commit()

            if window.uses >= FREE_USES:
                retry_in = (window.window_start + timedelta(minutes=FREE_WINDOW_MIN)) - now
                mins_left = max(0, int(retry_in.total_seconds() // 60))
                if is_json_request():
                    return jsonify({"error":"free_quota_exceeded",
                                    "message":f"Free quota reached. Try again in ~{mins_left} minutes.",
                                    "retry_in_minutes": mins_left}), 429
                flash(f"Free quota reached. Try again in ~{mins_left} minutes.","warning")
                return redirect(url_for("index"))

            window.uses += 1; db.session.commit()
            return fn(*args, **kwargs)
        return wrapper
    return decorator
