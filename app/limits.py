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

def get_webcam_action():
    """
    Returns (is_webcam, action) with action in {'start','frame','stop'}.
    Default to 'frame' so unsolicited frames do NOT auto-start.
    """
    try:
        if request.is_json:
            j = request.get_json(silent=True) or {}
            if j.get("source") == "webcam":
                a = (j.get("action") or "frame").lower()
                if a not in ("start", "frame", "stop"):
                    a = "frame"
                return True, a
    except Exception:
        pass
    return False, "frame"


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

            is_webcam, action = get_webcam_action()

            if is_webcam:
                now = datetime.utcnow()

                # STOP: expire immediately and return lightweight OK
                if action == "stop":
                    sess = (StreamSession.query
                            .filter_by(user_id=current_user.id, service=service_name)
                            .order_by(StreamSession.expires_at.desc())
                            .first())
                    if sess:
                        sess.expires_at = now
                        db.session.commit()
                    # optionally short-circuit here so your endpoint doesn't do heavy work
                    return jsonify({"ok": True, "stopped": True}), 200

                # Clean up expired first
                sess = _get_active_stream_session(current_user.id, service_name)

                if action == "frame":
                    # Allow only if a session is active; DO NOT auto-start
                    if sess:
                        return fn(*args, **kwargs)
                    # Session expired: tell client to stop
                    return jsonify({"error": "stream_session_expired"}), 440

                # action == "start"
                if sess:
                    # Already active, don't consume again
                    return fn(*args, **kwargs)

                # Need to consume ONE use to start a new session
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
                    return jsonify({"error": "free_quota_exceeded",
                                    "retry_in_minutes": mins_left}), 429

                window.uses += 1;
                db.session.commit()
                ttl_min = min(STREAM_SESSION_MIN, FREE_WINDOW_MIN)
                db.session.add(StreamSession(
                    user_id=current_user.id, service=service_name,
                    expires_at=now + timedelta(minutes=ttl_min)
                ))
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
