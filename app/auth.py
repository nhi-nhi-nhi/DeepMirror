from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models.auth_models import User, ServiceUsage
from datetime import datetime, timezone, timedelta

ADMIN_KEY = "ADMIN"

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        if not email or not pw:
            flash("Email and password required.", "warning")
            return redirect(url_for("auth.register"))
        if User.query.filter_by(email=email).first():
            flash("Email already registered.", "warning")
            return redirect(url_for("auth.register"))

        user = User(email=email, pw_hash=generate_password_hash(pw))
        db.session.add(user)
        db.session.commit()

        login_user(user)
        return redirect(url_for("index"))

    return render_template("auth_register.html")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        pw = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if not user or not check_password_hash(user.pw_hash, pw):
            flash("Invalid credentials.", "danger")
            return redirect(url_for("auth.login"))

        login_user(user)
        return redirect(url_for("index"))

    return render_template("auth_login.html")


@auth_bp.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))


@auth_bp.route("/account")
@login_required
def account():
    # --- START FIX: Get all 3 token types ---

    # 1. Get the single SHARED pool of Paid Tokens
    paid_tokens = current_user.tokens or 0

    # 2. Get Config
    cfg = {
        "FREE_USES": int(current_app.config.get("FREE_USES", 3)),
        "FREE_WINDOW_MIN": int(current_app.config.get("FREE_WINDOW_MIN", 30)),
    }
    now = datetime.now(timezone.utc)

    # 3. Helper function to get free uses for a specific service
    def get_remaining_free_uses(service_name):
        w = (ServiceUsage.query
             .filter_by(user_id=current_user.id, service=service_name)
             .order_by(ServiceUsage.window_start.desc())
             .first())

        uses = 0
        if w:
            w_start = w.window_start
            if not w_start.tzinfo:
                w_start = w_start.replace(tzinfo=timezone.utc)

            window_total_seconds = cfg["FREE_WINDOW_MIN"] * 60
            elapsed_seconds = int((now - w_start).total_seconds())

            if elapsed_seconds < window_total_seconds:
                uses = w.uses  # Window is valid, get uses

        return max(0, cfg["FREE_USES"] - uses)

    # 4. Calculate free uses for each service
    free_detect_uses = get_remaining_free_uses("deepfake_detect")
    free_swap_uses = get_remaining_free_uses("face_swap")

    # --- END FIX ---

    # 5. Pass all three values to the template
    return render_template("auth_account.html",
                           title="Account Settings",
                           paid_tokens=paid_tokens,
                           free_detect_uses=free_detect_uses,
                           free_swap_uses=free_swap_uses)


@auth_bp.route("/change-password", methods=["GET", "POST"])
@login_required
def change_password():
    if request.method == "POST":
        old_pw = request.form.get("old_password", "")
        new_pw = request.form.get("new_password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if not check_password_hash(current_user.pw_hash, old_pw):
            flash("Mật khẩu cũ không chính xác.", "danger")
            return redirect(url_for("auth.change_password"))

        if len(new_pw) < 6:
            flash("Mật khẩu mới phải có ít nhất 6 ký tự.", "danger")
            return redirect(url_for("auth.change_password"))

        if new_pw != confirm_pw:
            flash("Mật khẩu mới và xác nhận mật khẩu không khớp.", "danger")
            return redirect(url_for("auth.change_password"))

        current_user.pw_hash = generate_password_hash(new_pw)
        db.session.commit()

        flash("Mật khẩu đã được thay đổi thành công!", "success")
        return redirect(url_for("auth.account"))

    return render_template("auth_change_password.html", title="Change Password")


# START: ROUTE MUA TOKENS
@auth_bp.route("/upgrade", methods=["GET", "POST"])
@login_required
def upgrade_tokens():
    if request.method == "POST":
        tokens_to_add = int(request.form.get("tokens_option", 0))
        submitted_key = request.form.get("admin_key", "")

        if submitted_key != ADMIN_KEY:
            flash("Key kích hoạt không hợp lệ. Vui lòng kiểm tra lại.", "danger")
            return redirect(url_for("auth.upgrade_tokens"))

        if tokens_to_add <= 0:
            flash("Vui lòng chọn số lượng tokens hợp lệ.", "danger")
            return redirect(url_for("auth.upgrade_tokens"))

        current_user.tokens += tokens_to_add
        db.session.commit()

        flash(f"Đã thêm thành công {tokens_to_add} tokens vào tài khoản!", "success")
        return redirect(url_for("auth.account"))

    return render_template("auth_upgrade.html", title="Upgrade Tokens")
# END: ROUTE MUA TOKENS