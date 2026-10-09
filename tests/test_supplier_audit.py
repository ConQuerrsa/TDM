import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import unittest
from uuid import uuid4


class SupplierAuditTests(unittest.TestCase):
    def setUp(self):
        self.database = Path('instance') / f'test-audit-{uuid4().hex}.db'
        connection = sqlite3.connect(self.database)
        try:
            connection.executescript('''
                CREATE TABLE supplier_orders (id INTEGER, order_number TEXT, supplier TEXT, goods_cost NUMERIC, status TEXT);
                CREATE TABLE supplier_order_costs (id INTEGER, supplier_order_id INTEGER, amount NUMERIC, description TEXT, cost_date TEXT, funding_type TEXT, partner_id INTEGER, money_account_id INTEGER, created_by_id INTEGER, notes TEXT);
                CREATE TABLE users (id INTEGER, name TEXT, password_hash TEXT);
                CREATE TABLE money_accounts (id INTEGER, name TEXT);
                CREATE TABLE partner_transactions (id INTEGER, partner_id INTEGER, amount NUMERIC, transaction_type TEXT, money_account_id INTEGER, repayment_expected INTEGER, description TEXT, transaction_date TEXT, created_by_id INTEGER, notes TEXT);
                CREATE TABLE financial_transactions (id INTEGER, source_type TEXT, source_id INTEGER, amount NUMERIC, from_account_id INTEGER, to_account_id INTEGER, reversal_of_id INTEGER);
                INSERT INTO supplier_orders VALUES (1,'ORD-FIXTURE','Alibaba',2475,'in_transit'),(2,'OTHER','Other supplier',2475,'in_transit');
                INSERT INTO users VALUES (1,'Sbusiso','FAKE_PASSWORD_SENTINEL');
                INSERT INTO money_accounts VALUES (1,'TYDAL cash');
                INSERT INTO supplier_order_costs VALUES
                    (1,1,150,'Disputed customs','2026-10-04 12:00:00','partner_personal',1,NULL,1,'PRIVATE_NOTE_SENTINEL'),
                    (2,1,350,'Valid customs','2026-10-04 12:00:00','partner_personal',1,NULL,1,NULL),
                    (3,1,650,'TYDAL customs','2026-10-04 12:00:00','tydal_money',NULL,1,1,NULL),
                    (4,1,99,'Unrelated','2026-10-04 12:00:00','tydal_money',NULL,1,1,NULL);
                INSERT INTO partner_transactions VALUES
                    (11,1,150,'personal_expense',NULL,1,'Disputed customs - ORD-FIXTURE','2026-10-04 12:00:00.000000',1,'PRIVATE_NOTE_SENTINEL'),
                    (12,1,350,'personal_expense',NULL,1,'Valid customs - ORD-FIXTURE','2026-10-04 12:00:00.000000',1,NULL);
                INSERT INTO financial_transactions VALUES (13,'supplier_order_cost',3,650,1,NULL,NULL);
            ''')
            connection.commit()
        finally:
            connection.close()

    def tearDown(self):
        self.database.unlink()

    def run_audit(self, *extra):
        before = hashlib.sha256(self.database.read_bytes()).hexdigest()
        result = subprocess.run([sys.executable, 'scripts/audit_supplier_orders.py', str(self.database), '--alibaba-review', *extra],
            capture_output=True, text=True, check=True)
        self.assertEqual(hashlib.sha256(self.database.read_bytes()).hexdigest(), before)
        self.assertNotIn('PRIVATE_NOTE_SENTINEL', result.stdout)
        self.assertNotIn('FAKE_PASSWORD_SENTINEL', result.stdout)
        return json.loads(result.stdout)

    def test_minimal_output_preserves_database_and_identifies_ids(self):
        output = self.run_audit()
        self.assertEqual(output['order_match'], 'unique')
        costs = output['orders'][0]['costs']
        self.assertEqual([cost['amount'] for cost in costs], [150,350,650])
        self.assertEqual([cost['exact_funding_ids'] for cost in costs], [[11],[12],[13]])
        self.assertTrue(all(cost['funding_match'] == 'unique' for cost in costs))

    def test_ambiguous_and_nonmatching_funding(self):
        connection = sqlite3.connect(self.database)
        try:
            connection.execute('INSERT INTO partner_transactions SELECT 14,partner_id,amount,transaction_type,money_account_id,repayment_expected,description,transaction_date,created_by_id,notes FROM partner_transactions WHERE id=11')
            connection.execute("UPDATE partner_transactions SET description='Different event' WHERE id=12")
            connection.commit()
        finally:
            connection.close()
        costs = self.run_audit()['orders'][0]['costs']
        self.assertEqual(costs[0]['funding_match'], 'ambiguous')
        self.assertEqual(costs[0]['exact_funding_ids'], [11,14])
        self.assertEqual(costs[1]['funding_match'], 'missing')
        self.assertEqual(costs[1]['funding_candidates'][0]['id'], 12)
        self.assertFalse(costs[1]['funding_candidates'][0]['exact_match'])

    def test_unknown_order_refuses_guessing(self):
        self.assertEqual(self.run_audit('--order-id', '999'), {'order_match':'missing','orders':[]})
