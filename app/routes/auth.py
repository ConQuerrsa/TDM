from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user
from werkzeug.security import check_password_hash

from app.models import User


auth = Blueprint("auth", __name__, url_prefix="/auth")


def normalize_phone(phone):
    """
    Convert South African phone-number formats to one comparable format.

    Examples:
    0684704656       -> 27684704656
    +27684704656     -> 27684704656
    +27 68 470 4656  -> 27684704656
    27 68 470 4656   -> 27684704656
    """
    if not phone:
        return ""

    # Keep digits only
    digits = "".join(char for char in phone if char.isdigit())

    # Local SA format: 0XXXXXXXXX -> 27XXXXXXXXX
    if len(digits) == 10 and digits.startswith("0"):
        digits = "27" + digits[1:]

    return digits


@auth.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        entered_phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")

        normalized_entered_phone = normalize_phone(entered_phone)

        # Accounts are few, so normalize existing stored numbers while comparing.
        # This also supports old accounts saved in different formats.
        user = next(
            (
                account
                for account in User.query.all()
                if normalize_phone(account.phone) == normalized_entered_phone
            ),
            None,
        )

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