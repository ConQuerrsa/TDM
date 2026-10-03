from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import BusinessSettings, MoneyAccount, FinancialTransaction
from decimal import Decimal

settings = Blueprint('settings', __name__, url_prefix='/settings')

@settings.route('/')
@login_required
def index():
    business=BusinessSettings.query.first()
    accounts=MoneyAccount.query.order_by(MoneyAccount.name).all()
    return render_template('settings/index.html',business=business,accounts=accounts)

@settings.route('/money-location',methods=['POST'])
@login_required
def add_money_location():
    if current_user.role!='admin':
        flash('Only the TDM administrator can add money locations.','error'); return redirect(url_for('settings.index'))
    name=request.form.get('name','').strip(); account_type=request.form.get('account_type','other').strip()
    if not name: flash('Enter a money location name.','error'); return redirect(url_for('settings.index'))
    if MoneyAccount.query.filter(db.func.lower(MoneyAccount.name)==name.lower()).first():
        flash('That money location already exists.','error'); return redirect(url_for('settings.index'))
    account=MoneyAccount(name=name,account_type=account_type,opening_balance=Decimal('0.00'),is_active=True)
    db.session.add(account); db.session.commit(); flash(f'{name} added.','success'); return redirect(url_for('settings.index'))
