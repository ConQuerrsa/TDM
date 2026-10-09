"""Supplier corrections and receipts. Callers commit once or roll back on failure."""
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN
from sqlalchemy import update
from app import db
from app.models import (SupplierOrder, SupplierOrderCost, SupplierCostReversal,
    SupplierOrderReceipt, PartnerTransaction, FinancialTransaction, Purchase,
    PurchaseItem, Product, StockLocation, StockHolding, StockMovement)


class SupplierError(ValueError):
    pass


def amount(value):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or result > Decimal('9999999999.99'):
            raise ValueError()
        if result != result.quantize(Decimal('.01')):
            raise ValueError()
        return result.quantize(Decimal('.01'))
    except (InvalidOperation, ValueError, TypeError):
        raise SupplierError('Enter a valid non-negative amount with at most two decimals.')


def lock_order(order_id, receiving=False):
    # First write serializes SQLite writers; conditional status also guards stale requests.
    result = db.session.execute(update(SupplierOrder).where(
        SupplierOrder.id == order_id, SupplierOrder.status == 'in_transit'
    ).values(status='received' if receiving else 'in_transit'),
        execution_options={'synchronize_session': False})
    if result.rowcount != 1:
        raise SupplierError('Only an in-transit order can be changed or received once.')
    db.session.expire_all()
    return db.session.get(SupplierOrder, order_id)


def partner_matches(cost):
    query = PartnerTransaction.query.filter_by(
        partner_id=cost.partner_id, transaction_type='personal_expense',
        amount=cost.amount, money_account_id=None, repayment_expected=True)
    if cost.partner_transaction_id:
        return query.filter_by(id=cost.partner_transaction_id).all()
    # Legacy rows have no FK. Refuse partial or ambiguous matches.
    return query.filter_by(description=f'{cost.description} - {cost.order.order_number}',
        transaction_date=cost.cost_date, created_by_id=cost.created_by_id,
        notes=cost.notes).all()


def reverse_cost(order_id, cost_id, actor_id, reason, confirmed_transaction_id):
    order = lock_order(order_id)
    cost = db.session.get(SupplierOrderCost, cost_id)
    if not cost or cost.supplier_order_id != order.id or cost.reversal:
        raise SupplierError('Cost is unavailable or has already been reversed.')
    if not reason or not reason.strip():
        raise SupplierError('A correction reason is required.')
    audit = SupplierCostReversal(cost_id=cost.id, reason=reason.strip(), created_by_id=actor_id)
    if cost.funding_type == 'partner_personal':
        matches = partner_matches(cost)
        if len(matches) != 1 or str(matches[0].id) != str(confirmed_transaction_id):
            raise SupplierError('The original partner transaction must be uniquely matched and confirmed.')
        original = matches[0]
        if SupplierCostReversal.query.filter_by(original_partner_transaction_id=original.id).first():
            raise SupplierError('This partner transaction has already been reversed.')
        # Existing partner reports sum signed personal_expense amounts. This contra entry
        # cancels only the original funding, including when it offset an existing debt.
        contra = PartnerTransaction(partner_id=original.partner_id,
            transaction_type='personal_expense', amount=-original.amount,
            repayment_expected=True, description=f'Reversal of partner transaction #{original.id}',
            notes=reason.strip(), created_by_id=actor_id)
        db.session.add(contra)
        db.session.flush()
        audit.original_partner_transaction_id = original.id
        audit.partner_transaction_id = contra.id
    elif cost.funding_type == 'tydal_money':
        matches = FinancialTransaction.query.filter_by(source_type='supplier_order_cost',
            source_id=cost.id, amount=cost.amount, from_account_id=cost.money_account_id,
            to_account_id=None, reversal_of_id=None).all()
        if len(matches) != 1 or str(matches[0].id) != str(confirmed_transaction_id):
            raise SupplierError('The original financial transaction must be uniquely matched and confirmed.')
        original = matches[0]
        if FinancialTransaction.query.filter_by(reversal_of_id=original.id).first():
            raise SupplierError('This financial transaction has already been reversed.')
        contra = FinancialTransaction(transaction_type='supplier_cost_reversal', amount=original.amount,
            from_account_id=original.to_account_id, to_account_id=original.from_account_id,
            reversal_of_id=original.id, source_type='supplier_order_cost', source_id=cost.id,
            description=f'Reversal of financial transaction #{original.id}', notes=reason.strip(),
            created_by_id=actor_id)
        db.session.add(contra)
        db.session.flush()
        audit.financial_transaction_id = contra.id
    else:
        raise SupplierError('Unsupported funding type; correction requires investigation.')
    db.session.add(audit)
    db.session.flush()
    db.session.expire(cost, ['reversal'])
    return audit


def allocate(total, weights):
    """Largest-remainder cents allocation; deterministic and exactly reconciled."""
    denominator = sum(weights)
    if denominator <= 0:
        raise SupplierError('Received goods costs must be greater than zero.')
    raw = [total * weight / denominator for weight in weights]
    result = [value.quantize(Decimal('.01'), rounding=ROUND_DOWN) for value in raw]
    cents = int((total - sum(result)) * 100)
    for index in sorted(range(len(raw)), key=lambda i: (-(raw[i] - result[i]), i))[:cents]:
        result[index] += Decimal('.01')
    return result


def receive_order(order_id, actor_id, lines):
    order = lock_order(order_id, receiving=True)
    if not lines or len(lines) > 200:
        raise SupplierError('Enter between one and 200 received lines.')
    prepared = []
    for line in lines:
        try:
            quantity = int(str(line.get('quantity', '')))
            location = db.session.get(StockLocation, int(line.get('location_id', '')))
        except (ValueError, TypeError):
            raise SupplierError('Choose a stock location and a whole-number quantity.')
        if quantity <= 0 or quantity > 1000000 or not location or not location.is_active:
            raise SupplierError('Quantity must be positive and the stock location active.')
        goods_total = amount(line.get('goods_total'))
        if goods_total <= 0:
            raise SupplierError('Each received line needs a positive goods cost.')
        product_id = line.get('product_id')
        if product_id and product_id != '__new__':
            try:
                product = db.session.get(Product, int(product_id))
            except (ValueError, TypeError):
                raise SupplierError('Choose a valid product.')
            if not product or not product.is_active:
                raise SupplierError('The selected product is unavailable.')
        elif product_id == '__new__':
            fields = {}
            for key, limit in [('name',150), ('brand',100), ('category',100), ('size',50), ('color',50)]:
                value = str(line.get(key, '')).strip()
                if len(value) > limit:
                    raise SupplierError(f'{key.title()} is too long.')
                fields[key] = value or None
            if not fields['name']:
                raise SupplierError('Enter the new product family name.')
            # Keep the existing Product-per-size/colour inventory representation.
            matches = Product.query.filter_by(**fields).all()
            if len(matches) > 1 or (matches and not matches[0].is_active):
                raise SupplierError('Product identity is ambiguous or inactive; choose an existing product.')
            if matches:
                product = matches[0]
            else:
                product = Product(**fields, quantity=0, supplier=order.supplier,
                    selling_price=amount(line.get('selling_price', '0')))
                db.session.add(product)
                db.session.flush()
        else:
            raise SupplierError('Choose an existing product or New product.')
        if sum(h.quantity for h in product.holdings) != product.quantity:
            raise SupplierError('Existing product stock disagrees with its locations; reconcile before receipt.')
        prepared.append((product, quantity, location, goods_total))
    weights = [row[3] for row in prepared]
    if sum(weights) != order.goods_cost:
        raise SupplierError('Received goods line totals must equal the recorded order goods cost.')
    totals = allocate(order.landed_cost, weights)
    purchase = Purchase(purchase_number=f'REC-{order.id}', supplier=order.supplier,
        total_amount=order.landed_cost, purchased_by_id=actor_id, status='completed',
        notes=f'Receipt of {order.order_number}; payments recorded previously.')
    db.session.add(purchase)
    db.session.flush()
    product_totals = {}
    for (product, quantity, location, _), total in zip(prepared, totals):
        summary = product_totals.setdefault(product.id, [product, 0, Decimal('0')])
        summary[1] += quantity
        summary[2] += total
        unit = (total / quantity).quantize(Decimal('.01'))
        holding = StockHolding.query.filter_by(product_id=product.id, stock_location_id=location.id).first()
        if not holding:
            holding = StockHolding(product_id=product.id, stock_location_id=location.id, quantity=0)
            db.session.add(holding)
        holding.quantity += quantity
        db.session.add(PurchaseItem(purchase_id=purchase.id, product_id=product.id,
            quantity=quantity, unit_cost=unit, line_total=total))
        db.session.add(StockMovement(product_id=product.id, movement_type='purchase', quantity=quantity,
            unit_cost=unit, to_location_id=location.id, reference=order.order_number,
            notes=f'Allocated landed cost R{total:.2f}; purchase #{purchase.id}', created_by_id=actor_id))
        db.session.flush()
    for product, quantity, total in product_totals.values():
        old_qty = product.quantity
        product.cost_price = ((product.cost_price * old_qty + total) / (old_qty + quantity)).quantize(Decimal('.01'))
        product.quantity += quantity
    receipt = SupplierOrderReceipt(supplier_order_id=order.id, purchase_id=purchase.id, received_by_id=actor_id)
    db.session.add(receipt)
    db.session.flush()
    return receipt
