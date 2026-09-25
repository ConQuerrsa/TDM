from datetime import datetime, timedelta

from flask import Blueprint, render_template, request
from flask_login import login_required
from sqlalchemy import or_

from app.models import FinancialTransaction, User


activity = Blueprint("activity", __name__, url_prefix="/activity")


@activity.route("/")
@login_required
def index():
    user_id = request.args.get("user", type=int)
    activity_type = request.args.get("type", "").strip()
    period = request.args.get("period", "all").strip()

    query = FinancialTransaction.query

    # Filter by person
    if user_id:
        query = query.filter(
            FinancialTransaction.created_by_id == user_id
        )

    # Filter by transaction/source type
    if activity_type:
        query = query.filter(
            or_(
                FinancialTransaction.source_type == activity_type,
                FinancialTransaction.transaction_type == activity_type
            )
        )

    # Time filter
    now = datetime.utcnow()

    if period == "today":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        query = query.filter(
            FinancialTransaction.transaction_date >= start
        )

    elif period == "7days":
        query = query.filter(
            FinancialTransaction.transaction_date >= now - timedelta(days=7)
        )

    elif period == "30days":
        query = query.filter(
            FinancialTransaction.transaction_date >= now - timedelta(days=30)
        )

    activities = (
        query
        .order_by(
            FinancialTransaction.transaction_date.desc(),
            FinancialTransaction.id.desc()
        )
        .limit(200)
        .all()
    )

    users = User.query.order_by(User.name.asc()).all()

    today_start = now.replace(
        hour=0,
        minute=0,
        second=0,
        microsecond=0
    )

    today_count = FinancialTransaction.query.filter(
        FinancialTransaction.transaction_date >= today_start
    ).count()

    seven_day_count = FinancialTransaction.query.filter(
        FinancialTransaction.transaction_date >= now - timedelta(days=7)
    ).count()

    return render_template(
        "activity/index.html",
        activities=activities,
        users=users,
        today_count=today_count,
        seven_day_count=seven_day_count,
        selected_user=user_id,
        selected_type=activity_type,
        selected_period=period,
    )