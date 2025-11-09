from datetime import datetime, timedelta
from functools import wraps
from flask import current_app, request, redirect, url_for, flash, jsonify
from flask_login import current_user
from app import db
from app.models.auth_models import ServiceUsage, StreamSession

# =============================================================================
# In-memory stream cache (process-local; switch to Redis for multi-worker setup)
# key: (user_id, service) -> expires_at (UTC datetime)
# =============================================================================
_STREAM_CACHE = {}

def _stream_set(uid, service, expires_at_dt: datetime):
    _STREAM_CACHE[(uid, service)] = expires_at_dt

def _stream_get(uid, service):
    return _STREAM_CACHE.get((uid, service))

def _stream_clear(uid, service):
    _STREAM_CACHE.pop((uid, service), None)

def _stream_ok(uid, service) -> bool:
    exp = _stream_get(uid, service)
    return bool(exp and exp > datetime.utcnow())

def _stream_seconds_left(uid, service) -> int:
    exp = _stream_get(uid, service)
    if not exp:
        return 0
    delta = int((exp - datetime.utcnow()).total_seconds())
    return max(0, delta)

def _cleanup_expired_sessions():
    now = datetime.utcnow()
    expired = [k for k, exp in _STREAM_CACHE.items() if exp <= now]
    for k in expired:
        _STREAM_CACHE.pop(k, None)

# =============================================================================
# DB helper
# =============================================================================
def _get_active_stream_session(user_id, service):
    """Return active StreamSession from DB, or None if expired."""
    now = datetime.utcnow()
    sess = (StreamSession.query
            .filter_by(user_id=user_id, service=service)
            .order_by(StreamSession.expires_at.desc())
            .first())
    if sess and sess.expires_at <= now:
        try:
            db.session.delete(sess)
            db.session.commit()
        except Exception:
            db.session.rollback()
        return None
    return sess

def is_json_request():
    return request.is_json or request.headers.get("X-Requested-With") == "XMLHttpRequest"

def get_webcam_action():
    """Return (is_webcam, action) with action in {'start','frame','stop'}."""
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
    return bool(user and user.plan in ("plus-monthly", "plus-annual")
                and user.plan_until and user.plan_until > datetime.utcnow())

# =============================================================================
# MAIN DECORATOR
# =============================================================================
def enforce_quota(service_name: str):
    """
    Usage:
      - Webcam (stream) endpoints call with {"source":"webcam","action":"start|frame|stop"}.
      - Non-stream endpoints (single calls) count 1 use per call.
    """

    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            # 0) Require authentication
            try:
                j = request.get_json(silent=True) or {}
                print("[QUOTA]", service_name, "json:", j)
            except Exception as _:
                print("[QUOTA]", service_name, "no-json")

            if not current_user.is_authenticated:
                if is_json_request():
                    return jsonify({"error": "auth_required"}), 401
                return redirect(url_for("auth.login"))

            # 1) Paid (subscribed) users skip limits entirely
            if is_subscribed(current_user):
                return fn(*args, **kwargs)

            # 2) Load config
            FREE_USES = int(current_app.config.get("FREE_USES", 3))
            FREE_WINDOW_MIN = int(current_app.config.get("FREE_WINDOW_MIN", 30))
            STREAM_SESSION_MIN = int(current_app.config.get("STREAM_SESSION_MIN", 2))
            now = datetime.utcnow()  # Use utcnow() if your DB is in UTC

            # 3) Webcam / stream mode
            is_webcam, action = get_webcam_action()
            if is_webcam:
                uid = current_user.id
                _cleanup_expired_sessions()

                # ---- STOP ----
                if action == "stop":
                    # (This logic seems fine, no token consumption)
                    sess = (StreamSession.query
                            .filter_by(user_id=uid, service=service_name)
                            .order_by(StreamSession.expires_at.desc())
                            .first())
                    if sess:
                        sess.expires_at = now
                        db.session.commit()
                    _stream_clear(uid, service_name)
                    return jsonify({"ok": True, "stopped": True}), 200

                # ---- FRAME ----
                if action == "frame":
                    # (This logic seems fine, no token consumption)
                    if _stream_ok(uid, service_name):
                        return fn(*args, **kwargs)
                    sess = _get_active_stream_session(uid, service_name)
                    if sess and sess.expires_at > now:
                        _stream_set(uid, service_name, sess.expires_at)
                        return fn(*args, **kwargs)
                    _stream_clear(uid, service_name)
                    return jsonify({"error": "stream_session_expired"}), 440

                # ---- START ----
                if _stream_ok(uid, service_name):
                    return fn(*args, **kwargs)

                sess = _get_active_stream_session(uid, service_name)
                if sess and sess.expires_at > now:
                    _stream_set(uid, service_name, sess.expires_at)
                    return fn(*args, **kwargs)

                # Not active: need to consume a use
                window = (ServiceUsage.query
                          .filter_by(user_id=uid, service=service_name)
                          .order_by(ServiceUsage.window_start.desc())
                          .first())
                if (not window) or (now - window.window_start > timedelta(minutes=FREE_WINDOW_MIN)):
                    window = ServiceUsage(user_id=uid, service=service_name,
                                          window_start=now, uses=0)
                    db.session.add(window)
                    # No commit needed yet, will commit below

                if window.uses >= FREE_USES:
                    # <<< MODIFICATION START >>>
                    # --- Free uses are gone. Check for paid tokens. ---
                    paid_tokens = current_user.tokens or 0
                    if paid_tokens > 0:
                        # YES, consume one paid token
                        current_user.tokens -= 1
                        # db.session.commit() # Commit handled below

                        # And create the stream session
                        ttl_min = min(STREAM_SESSION_MIN, FREE_WINDOW_MIN)
                        expires_at = now + timedelta(minutes=ttl_min)
                        new_sess = StreamSession(user_id=uid, service=service_name, expires_at=expires_at)
                        db.session.add(new_sess)
                        db.session.commit()  # Commit paid token and new session

                        _stream_set(uid, service_name, expires_at)
                        return fn(*args, **kwargs)  # Run the function
                    # <<< MODIFICATION END >>>

                    # --- No free uses AND no paid tokens. Block. ---
                    retry_in = (window.window_start + timedelta(minutes=FREE_WINDOW_MIN)) - now
                    mins_left = max(0, int((retry_in.total_seconds() + 59) // 60))
                    return jsonify({"error": "free_quota_exceeded",
                                    "retry_in_minutes": mins_left}), 429

                # --- Free uses are available. Consume one. ---
                window.uses += 1
                # db.session.commit() # Commit handled below

                # create session
                ttl_min = min(STREAM_SESSION_MIN, FREE_WINDOW_MIN)
                expires_at = now + timedelta(minutes=ttl_min)

                new_sess = StreamSession(user_id=uid, service=service_name, expires_at=expires_at)
                db.session.add(new_sess)
                db.session.commit()  # Commit free use and new session

                _stream_set(uid, service_name, expires_at)
                return fn(*args, **kwargs)

            # 4) Non-stream: 1 call = 1 use
            window = (ServiceUsage.query
                      .filter_by(user_id=current_user.id, service=service_name)
                      .order_by(ServiceUsage.window_start.desc())
                      .first())
            if (not window) or (now - window.window_start > timedelta(minutes=FREE_WINDOW_MIN)):
                window = ServiceUsage(user_id=current_user.id, service=service_name,
                                      window_start=now, uses=0)
                db.session.add(window)
                # No commit needed yet

            if window.uses >= FREE_USES:
                # <<< MODIFICATION START >>>
                # --- Free uses are gone. Check for paid tokens. ---
                paid_tokens = current_user.tokens or 0
                if paid_tokens > 0:
                    # YES, consume one paid token
                    current_user.tokens -= 1
                    db.session.commit()
                    return fn(*args, **kwargs)  # Run the function
                # <<< MODIFICATION END >>>

                # --- No free uses AND no paid tokens. Block. ---
                retry_in = (window.window_start + timedelta(minutes=FREE_WINDOW_MIN)) - now
                mins_left = max(0, int((retry_in.total_seconds() + 59) // 60))
                if is_json_request():
                    return jsonify({"error": "free_quota_exceeded",
                                    "message": f"Free quota reached. Try again in ~{mins_left} minutes.",
                                    "retry_in_minutes": mins_left}), 429
                flash(f"Free quota reached. Try again in ~{mins_left} minutes.", "warning")
                return redirect(url_for("index"))

            # --- Free uses are available. Consume one. ---
            window.uses += 1
            db.session.commit()
            return fn(*args, **kwargs)

        return wrapper

    return decorator

# =============================================================================
# Debug helpers
# =============================================================================
def stream_seconds_left_for(user_id, service):
    return _stream_seconds_left(user_id, service)

def stream_debug_info(user_id, service):
    secs = _stream_seconds_left(user_id, service)
    return {
        "service": service,
        "active": _stream_ok(user_id, service),
        "seconds_left": secs,
    }
