from functools import wraps

from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.security import generate_password_hash

from app import db
from app.models import User


team = Blueprint("team", __name__, url_prefix="/team")


def admin_required(view_function):
    @wraps(view_function)
    def wrapped_view(*args, **kwargs):
        if current_user.role != "admin":
            flash("Only an administrator can manage team accounts.", "error")
            return redirect(url_for("main.home"))

        return view_function(*args, **kwargs)

    return wrapped_view


@team.route("/")
@login_required
@admin_required
def index():
    users = User.query.order_by(User.created_at.asc()).all()

    active_count = sum(1 for user in users if user.is_active)
    admin_count = sum(1 for user in users if user.role == "admin")

    return render_template(
        "team/index.html",
        users=users,
        active_count=active_count,
        admin_count=admin_count,
    )


@team.route("/create", methods=["POST"])
@login_required
@admin_required
def create():
    name = request.form.get("name", "").strip()
    phone = request.form.get("phone", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "partner").strip().lower()

    if not name or not phone or not password:
        flash("Name, phone number and password are required.", "error")
        return redirect(url_for("team.index"))

    if role not in {"admin", "partner"}:
        flash("Invalid account role.", "error")
        return redirect(url_for("team.index"))

    if len(password) < 8:
        flash("Temporary password must contain at least 8 characters.", "error")
        return redirect(url_for("team.index"))

    existing_user = User.query.filter_by(phone=phone).first()

    if existing_user:
        flash("That phone number already belongs to a TDM account.", "error")
        return redirect(url_for("team.index"))

    user = User(
        name=name,
        phone=phone,
        password_hash=generate_password_hash(password),
        role=role,
        is_active=True,
    )

    db.session.add(user)
    db.session.commit()

    flash(f"{name}'s TDM account has been created.", "success")
    return redirect(url_for("team.index"))


@team.route("/<int:user_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_status(user_id):
    user = db.session.get(User, user_id)

    if not user:
        flash("Account not found.", "error")
        return redirect(url_for("team.index"))

    if user.id == current_user.id:
        flash("You cannot deactivate your own account.", "error")
        return redirect(url_for("team.index"))

    user.is_active = not user.is_active
    db.session.commit()

    state = "activated" if user.is_active else "deactivated"

    flash(f"{user.name}'s account has been {state}.", "success")
    return redirect(url_for("team.index"))


@team.route("/<int:user_id>/password", methods=["POST"])
@login_required
@admin_required
def reset_password(user_id):
    user = db.session.get(User, user_id)

    if not user:
        flash("Account not found.", "error")
        return redirect(url_for("team.index"))

    new_password = request.form.get("new_password", "")

    if len(new_password) < 8:
        flash("New password must contain at least 8 characters.", "error")
        return redirect(url_for("team.index"))

    user.password_hash = generate_password_hash(new_password)
    db.session.commit()

    flash(f"Password reset for {user.name}.", "success")
    return redirect(url_for("team.index"))


@team.route("/<int:user_id>/role", methods=["POST"])
@login_required
@admin_required
def change_role(user_id):
    user = db.session.get(User, user_id)

    if not user:
        flash("Account not found.", "error")
        return redirect(url_for("team.index"))

    new_role = request.form.get("role", "").strip().lower()

    if new_role not in {"admin", "partner"}:
        flash("Invalid account role.", "error")
        return redirect(url_for("team.index"))

    if user.id == current_user.id and new_role != "admin":
        flash("You cannot remove your own administrator access.", "error")
        return redirect(url_for("team.index"))

    user.role = new_role
    db.session.commit()

    flash(f"{user.name} is now a {new_role}.", "success")
    return redirect(url_for("team.index"))