from datetime import datetime
from decimal import Decimal, InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import (Sale, SaleItem, SalePayment, Product, StockHolding, StockLocation,
                        StockMovement, MoneyAccount, FinancialTransaction)

sales = Blueprint('sales', __name__, url_prefix='/sales')
D=Decimal

def generate_sale_number():
    today=datetime.utcnow(); prefix=f"TDM-{today.strftime('%y%m%d')}"
    latest=Sale.query.filter(Sale.sale_number.like(f'{prefix}-%')).order_by(Sale.id.desc()).first()
    seq=1
    if latest:
        try: seq=int(latest.sale_number.split('-')[-1])+1
        except (ValueError,IndexError): seq=latest.id+1
    return f'{prefix}-{seq:04d}'

def parse_money(raw, label):
    try: value=D(str(raw or '0')).quantize(D('0.01'))
    except (InvalidOperation,ValueError): raise ValueError(f'Enter a valid {label}.')
    if value < 0: raise ValueError(f'{label.title()} cannot be negative.')
    return value

@sales.route('/')
@login_required
def index():
    recent_sales=Sale.query.order_by(Sale.sale_date.desc(),Sale.id.desc()).limit(40).all()
    today=datetime.utcnow().date()
    today_sales=[s for s in recent_sales if s.sale_date.date()==today and s.status=='completed']
    today_revenue=sum((D(str(s.total_amount or 0)) for s in today_sales),D('0'))
    outstanding=sum((D(str(s.outstanding_amount or 0)) for s in Sale.query.filter(Sale.status=='completed').all()),D('0'))
    accounts=MoneyAccount.query.filter_by(is_active=True).order_by(MoneyAccount.name).all()
    return render_template('sales/index.html',recent_sales=recent_sales,today_revenue=today_revenue,
                           today_sale_count=len(today_sales),outstanding_total=outstanding,money_accounts=accounts)

@sales.route('/new', methods=['GET','POST'])
@login_required
def new_sale():
    products=Product.query.filter(Product.is_active.is_(True),Product.quantity>0).order_by(Product.name).all()
    accounts=MoneyAccount.query.filter_by(is_active=True).order_by(MoneyAccount.name).all()
    locations=StockLocation.query.filter_by(is_active=True).order_by(StockLocation.name).all()
    if request.method=='GET':
        return render_template('sales/new.html',products=products,money_accounts=accounts,stock_locations=locations,
                               holdings=StockHolding.query.filter(StockHolding.quantity>0).all())

    product=db.session.get(Product,request.form.get('product_id',type=int))
    location=db.session.get(StockLocation,request.form.get('stock_location_id',type=int))
    qty=request.form.get('quantity',type=int) or 0
    payment_method=request.form.get('payment_method','').strip()
    customer_name=request.form.get('customer_name','').strip()
    customer_contact=request.form.get('customer_contact','').strip()
    notes=request.form.get('notes','').strip()
    account_id=request.form.get('money_account_id',type=int)
    account=db.session.get(MoneyAccount,account_id) if account_id else None
    if not product or not product.is_active or not location or not location.is_active or qty<=0:
        flash('Complete the product, stock location and quantity correctly.','error'); return redirect(url_for('sales.new_sale'))
    holding=StockHolding.query.filter_by(product_id=product.id,stock_location_id=location.id).first()
    if not holding or holding.quantity<qty:
        flash(f'Only {holding.quantity if holding else 0} × {product.name} available at {location.name}.','error'); return redirect(url_for('sales.new_sale'))
    try:
        agreed_unit=parse_money(request.form.get('unit_price'), 'selling price')
        amount_paid=parse_money(request.form.get('amount_paid'), 'amount paid')
    except ValueError as e:
        flash(str(e),'error'); return redirect(url_for('sales.new_sale'))
    if agreed_unit<=0:
        flash('Selling price must be greater than R0.00.','error'); return redirect(url_for('sales.new_sale'))
    agreed_total=(agreed_unit*qty).quantize(D('0.01'))
    listed_total=(D(str(product.selling_price or 0))*qty).quantize(D('0.01'))
    if amount_paid>agreed_total:
        flash('Amount paid cannot be more than the agreed sale total.','error'); return redirect(url_for('sales.new_sale'))
    outstanding=agreed_total-amount_paid
    if amount_paid>0 and (not account or not account.is_active or not payment_method):
        flash('Choose how and where the money received is held.','error'); return redirect(url_for('sales.new_sale'))
    if outstanding>0 and not customer_name:
        flash('Enter the customer name when money is still outstanding.','error'); return redirect(url_for('sales.new_sale'))
    status='paid' if outstanding==0 else ('partially_paid' if amount_paid>0 else 'unpaid')
    now=datetime.utcnow()
    try:
        sale=Sale(sale_number=generate_sale_number(),total_amount=agreed_total,listed_total=listed_total,
                  amount_paid=amount_paid,outstanding_amount=outstanding,payment_status=status,
                  customer_name=customer_name or None,customer_contact=customer_contact or None,
                  payment_method=payment_method or 'credit',money_account_id=(account.id if account else None),
                  sold_by_id=current_user.id,status='completed',notes=notes or None,sale_date=now)
        db.session.add(sale); db.session.flush()
        cost=D(str(product.cost_price or 0))
        db.session.add(SaleItem(sale_id=sale.id,product_id=product.id,quantity=qty,unit_price=agreed_unit,cost_price=cost,
                                line_total=agreed_total,stock_location_id=location.id))
        holding.quantity-=qty; product.quantity-=qty
        db.session.add(StockMovement(product_id=product.id,movement_type='sale',quantity=qty,unit_cost=cost,
                    from_location_id=location.id,reference=sale.sale_number,notes=f'Sold by {current_user.name}',movement_date=now,created_by_id=current_user.id))
        if amount_paid>0:
            payment=SalePayment(sale_id=sale.id,amount=amount_paid,money_account_id=account.id,payment_method=payment_method,
                                payment_date=now,recorded_by_id=current_user.id)
            db.session.add(payment); db.session.flush()
            db.session.add(FinancialTransaction(transaction_type='sale_payment',amount=amount_paid,to_account_id=account.id,
                    description=f'Payment for {sale.sale_number}',reference=sale.sale_number,transaction_date=now,
                    source_type='sale_payment',source_id=payment.id,notes=notes or None,created_by_id=current_user.id))
        db.session.commit()
    except Exception:
        db.session.rollback(); flash('The sale could not be recorded. No stock or money was changed.','error'); return redirect(url_for('sales.new_sale'))
    msg=f'Sale {sale.sale_number} recorded — R{agreed_total:.2f}'
    if outstanding: msg+=f' (R{outstanding:.2f} still owed).'
    flash(msg,'success'); return redirect(url_for('sales.index'))

@sales.route('/<int:sale_id>/payment',methods=['POST'])
@login_required
def record_payment(sale_id):
    sale=db.session.get(Sale,sale_id)
    account=db.session.get(MoneyAccount,request.form.get('money_account_id',type=int))
    method=request.form.get('payment_method','').strip()
    notes=request.form.get('notes','').strip()
    if not sale or sale.status!='completed': flash('Sale not found.','error'); return redirect(url_for('sales.index'))
    try: amount=parse_money(request.form.get('amount'),'payment amount')
    except ValueError as e: flash(str(e),'error'); return redirect(url_for('sales.index'))
    outstanding=D(str(sale.outstanding_amount or 0))
    if amount<=0 or amount>outstanding or not account or not account.is_active or not method:
        flash(f'Enter a payment up to R{outstanding:.2f} and choose its money location.','error'); return redirect(url_for('sales.index'))
    now=datetime.utcnow()
    try:
        payment=SalePayment(sale_id=sale.id,amount=amount,money_account_id=account.id,payment_method=method,payment_date=now,notes=notes or None,recorded_by_id=current_user.id)
        db.session.add(payment); db.session.flush()
        sale.amount_paid=D(str(sale.amount_paid or 0))+amount; sale.outstanding_amount=outstanding-amount
        sale.payment_status='paid' if sale.outstanding_amount==0 else 'partially_paid'
        db.session.add(FinancialTransaction(transaction_type='sale_payment',amount=amount,to_account_id=account.id,
            description=f'Outstanding payment for {sale.sale_number}',reference=sale.sale_number,transaction_date=now,
            source_type='sale_payment',source_id=payment.id,notes=notes or None,created_by_id=current_user.id))
        db.session.commit()
    except Exception:
        db.session.rollback(); flash('Payment could not be recorded.','error'); return redirect(url_for('sales.index'))
    flash(f'R{amount:.2f} received for {sale.sale_number}.','success'); return redirect(url_for('sales.index'))
