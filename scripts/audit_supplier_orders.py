"""Read-only supplier audit, usable before the correction migration.

Usage: python scripts/audit_supplier_orders.py /absolute/path/to/tdm.db
Prints orders, costs, funding entries and their IDs. Never changes the database.
"""
import argparse
import json
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('database', type=Path)
    args = parser.parse_args()
    connection = sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('PRAGMA query_only=ON')
        connection.execute('BEGIN')  # Consistent read snapshot.
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
