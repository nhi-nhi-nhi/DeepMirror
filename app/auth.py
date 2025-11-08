from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash
from app import db
from app.models.auth_models import User

# Key bí mật cố định để kích hoạt token
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
    return render_template("auth_account.html", title="Account Settings")


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
        # Lấy thông tin từ form
        tokens_to_add = int(request.form.get("tokens_option", 0))  # Số token đã chọn
        submitted_key = request.form.get("admin_key", "")

        # 1. Kiểm tra Key bí mật
        if submitted_key != ADMIN_KEY:
            flash("Key kích hoạt không hợp lệ. Vui lòng kiểm tra lại.", "danger")
            return redirect(url_for("auth.upgrade_tokens"))

        # 2. Kiểm tra số lượng tokens hợp lệ
        if tokens_to_add <= 0:
            flash("Vui lòng chọn số lượng tokens hợp lệ.", "danger")
            return redirect(url_for("auth.upgrade_tokens"))

        # 3. Cập nhật Tokens
        current_user.tokens += tokens_to_add
        db.session.commit()

        flash(f"Đã thêm thành công {tokens_to_add} tokens vào tài khoản! Tổng tokens hiện tại: {current_user.tokens}",
              "success")
        return redirect(url_for("auth.account"))

    # Hiển thị trang mua tokens (GET)
    return render_template("auth_upgrade.html", title="Upgrade Tokens")
# END: ROUTE MUA TOKENS