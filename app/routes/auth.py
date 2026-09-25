from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user
from werkzeug.security import generate_password_hash, check_password_hash

from app import db
from app.models import User

auth = Blueprint("auth", __name__, url_prefix="/auth")


@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        user = User.query.filter_by(phone=phone).first()

        if user and check_password_hash(user.password_hash, password):
            if not user.is_active:
                flash("This account is currently inactive.", "error")
                return redirect(url_for("auth.login"))

            login_user(user)
            return redirect(url_for("main.home"))

        flash("Incorrect phone number or password.", "error")

    return render_template("auth/login.html")


@auth.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("auth.login"))