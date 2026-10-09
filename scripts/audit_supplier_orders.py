"""Read-only supplier audit, usable before the correction migration.

Usage: python scripts/audit_supplier_orders.py /absolute/path/to/tdm.db
Prints orders, costs, funding entries and their IDs. Never changes the database.
"""
import argparse
import json
from datetime import datetime
from decimal import Decimal
import sqlite3
from pathlib import Path


def same_date(left, right):
    try:
        return datetime.fromisoformat(left) == datetime.fromisoformat(right)
    except (ValueError, TypeError):
        return False


def alibaba_review(connection, order_id=None):
    """Minimal review only. Matching metadata is inspected but never printed."""
    orders = connection.execute(
        'SELECT id,order_number,supplier,goods_cost,status FROM supplier_orders ORDER BY id').fetchall()
    orders = [order for order in orders if 'alibaba' in order['supplier'].casefold()
        and Decimal(str(order['goods_cost'])) == Decimal('2475')
        and (order_id is None or order['id'] == order_id)]
    output = {'order_match': 'unique' if len(orders) == 1 else 'missing' if not orders else 'ambiguous',
        'orders': []}
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    for order in orders:
        record = dict(order)
        record['costs'] = []
        costs = connection.execute('SELECT * FROM supplier_order_costs WHERE supplier_order_id=? ORDER BY id', (order['id'],))
        for cost in costs:
            if Decimal(str(cost['amount'])) not in {Decimal('150'), Decimal('350'), Decimal('650')}:
                continue
            row = {key: cost[key] for key in ('id', 'amount', 'description', 'cost_date', 'funding_type')}
            row['already_reversed'] = bool(connection.execute(
                'SELECT 1 FROM supplier_cost_reversals WHERE cost_id=?', (cost['id'],)).fetchone()) if 'supplier_cost_reversals' in tables else False
            candidates, exact_ids = [], []
            if cost['funding_type'] == 'partner_personal':
                partner = connection.execute('SELECT name FROM users WHERE id=?', (cost['partner_id'],)).fetchone()
                row['payer'] = partner[0] if partner else 'Missing partner'
                link = cost['partner_transaction_id'] if 'partner_transaction_id' in cost.keys() else None
                transactions = connection.execute(
                    "SELECT * FROM partner_transactions WHERE partner_id=? AND amount=? AND transaction_type='personal_expense' ORDER BY id",
                    (cost['partner_id'], cost['amount'])).fetchall()
                for transaction in transactions:
                    base_match = transaction['money_account_id'] is None and bool(transaction['repayment_expected'])
                    exact = base_match and (transaction['id'] == link if link else (
                        transaction['description'] == f"{cost['description']} - {order['order_number']}"
                        and same_date(transaction['transaction_date'], cost['cost_date'])
                        and transaction['created_by_id'] == cost['created_by_id']
                        and transaction['notes'] == cost['notes']))
                    used = bool(connection.execute(
                        'SELECT 1 FROM supplier_cost_reversals WHERE original_partner_transaction_id=?',
                        (transaction['id'],)).fetchone()) if 'supplier_cost_reversals' in tables else False
                    candidates.append({'id': transaction['id'], 'exact_match': exact, 'already_reversed': used})
                    if exact:
                        exact_ids.append(transaction['id'])
                row['funding_ledger'] = 'partner_transactions'
            elif cost['funding_type'] == 'tydal_money':
                account = connection.execute('SELECT name FROM money_accounts WHERE id=?', (cost['money_account_id'],)).fetchone()
                row['payer'] = account[0] if account else 'Missing money account'
                transactions = connection.execute(
                    "SELECT * FROM financial_transactions WHERE source_type='supplier_order_cost' AND source_id=? ORDER BY id",
                    (cost['id'],)).fetchall()
                for transaction in transactions:
                    exact = (Decimal(str(transaction['amount'])) == Decimal(str(cost['amount']))
                        and transaction['from_account_id'] == cost['money_account_id']
                        and transaction['to_account_id'] is None and transaction['reversal_of_id'] is None)
                    used = bool(connection.execute('SELECT 1 FROM financial_transactions WHERE reversal_of_id=?', (transaction['id'],)).fetchone())
                    candidates.append({'id':transaction['id'], 'exact_match':exact, 'already_reversed':used})
                    if exact:
                        exact_ids.append(transaction['id'])
                row['funding_ledger'] = 'financial_transactions'
            else:
                row['funding_ledger'] = 'unsupported'
            row['funding_candidates'] = candidates
            row['exact_funding_ids'] = exact_ids
            row['funding_match'] = 'unique' if len(exact_ids) == 1 else 'missing' if not exact_ids else 'ambiguous'
            record['costs'].append(row)
        output['orders'].append(record)
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    parser.add_argument('--alibaba-review', action='store_true', help='Show only Alibaba R2475 orders, R150/R350/R650 costs and funding match IDs; omit notes and creator metadata.')
    parser.add_argument('--order-id', type=int, help='Narrow focused review to a known order ID.')
    args = parser.parse_args()
    if args.order_id is not None and not args.alibaba_review:
        parser.error('--order-id requires --alibaba-review')
    connection = sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')  # Consistent read snapshot.
        if args.alibaba_review:
            print(json.dumps(alibaba_review(connection, args.order_id), indent=2, ensure_ascii=False))
            return
        orders = connection.execute('SELECT id,order_number,supplier,goods_cost,status FROM supplier_orders').fetchall()
        for order in orders:
            record = dict(order)
            record['costs'] = []
            for cost in connection.execute('SELECT * FROM supplier_order_costs WHERE supplier_order_id=? ORDER BY id', (order['id'],)):
                row = dict(cost)
                if cost['funding_type'] == 'partner_personal':
                    row['partner_name'] = connection.execute('SELECT name FROM users WHERE id=?', (cost['partner_id'],)).fetchone()[0]
                    row['funding_candidates'] = [dict(t) for t in connection.execute(
                        'SELECT id,partner_id,transaction_type,amount,description,transaction_date,repayment_expected,notes,created_by_id FROM partner_transactions WHERE partner_id=? AND amount=? AND transaction_type=?',
                        (cost['partner_id'], cost['amount'], 'personal_expense'))]
                else:
                    row['funding_candidates'] = [dict(t) for t in connection.execute(
                        'SELECT id,amount,from_account_id,to_account_id,description,reversal_of_id FROM financial_transactions WHERE source_type=? AND source_id=?',
                        ('supplier_order_cost', cost['id']))]
                record['costs'].append(row)
            print(json.dumps(record, indent=2, ensure_ascii=False))
        if not orders:
            print('No supplier orders exist in this database.')
    finally:
        connection.close()


if __name__ == '__main__':
    main()
