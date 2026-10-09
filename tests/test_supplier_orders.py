import unittest
from datetime import datetime
from decimal import Decimal
from unittest.mock import patch
from app import create_app, db
from app.models import (User, MoneyAccount, SupplierOrder, SupplierOrderCost,
    PartnerTransaction, FinancialTransaction, SupplierCostReversal, SupplierOrderReceipt,
    Product, StockLocation, StockHolding, StockMovement, Purchase, PurchaseItem)
from app.services.supplier_orders import receive_order, reverse_cost, allocate, SupplierError

D = Decimal


class SupplierTests(unittest.TestCase):
    def setUp(self):
        self.app = create_app({'TESTING': True, 'SQLALCHEMY_DATABASE_URI': 'sqlite://',
            'SECRET_KEY': 'test', 'WTF_CSRF_ENABLED': False})
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()  # Disposable in-memory fixtures only.
        user = User(name='Sbusiso', phone='test', password_hash='test')
        db.session.add(user)
        db.session.flush()
        self.uid = user.id
        self.location = StockLocation(name='Sbusiso stock', owner_user_id=user.id)
        self.account = MoneyAccount(name='TYDAL cash', account_type='cash')
        self.order = SupplierOrder(order_number='TEST-ALIBABA', supplier='Alibaba',
            goods_cost=D('2475'), created_by_id=user.id, is_historical=True)
        db.session.add_all([self.location, self.account, self.order])
        db.session.flush()
        db.session.add(FinancialTransaction(transaction_type='opening_balance', amount=1000,
            to_account_id=self.account.id, description='Opening', created_by_id=user.id))
        # Preserve a separate historical R250 reclassification.
        db.session.add(PartnerTransaction(partner_id=user.id, transaction_type='withdrawal',
            amount=250, description='Opening reclassification', created_by_id=user.id))
        self.valid = self.personal_cost(350, 'Valid customs')
        self.error = self.personal_cost(150, 'Erroneous additional customs')
        self.business = SupplierOrderCost(supplier_order_id=self.order.id, amount=650,
            cost_type='customs_duties', description='TYDAL customs', funding_type='tydal_money',
            money_account_id=self.account.id, created_by_id=user.id)
        db.session.add(self.business)
        db.session.flush()
        db.session.add(FinancialTransaction(transaction_type='supplier_order_cost', amount=650,
            from_account_id=self.account.id, source_type='supplier_order_cost', source_id=self.business.id,
            description='TYDAL customs', created_by_id=user.id))
        db.session.commit()
        self.client = self.app.test_client()
        with self.client.session_transaction() as session:
            session['_user_id'] = str(user.id)
            session['_fresh'] = True

    def personal_cost(self, value, description):
        date = datetime(2026, 10, 4, 12)
        cost = SupplierOrderCost(supplier_order_id=self.order.id, amount=value,
            cost_type='customs_duties', description=description, funding_type='partner_personal',
            partner_id=self.uid, created_by_id=self.uid, cost_date=date)
        transaction = PartnerTransaction(partner_id=self.uid, transaction_type='personal_expense',
            amount=value, description=f'{description} - {self.order.order_number}',
            repayment_expected=True, transaction_date=date, created_by_id=self.uid)
        db.session.add_all([cost, transaction])
        db.session.flush()
        return cost

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        db.engine.dispose()
        self.context.pop()

    def position(self):
        return sum(t.amount if t.transaction_type == 'personal_expense' else -t.amount
            for t in PartnerTransaction.query.all())

    def financial_snapshot(self):
        return [(t.id,t.amount,t.from_account_id,t.to_account_id) for t in FinancialTransaction.query.order_by(FinancialTransaction.id)]

    def reverse(self):
        original = PartnerTransaction.query.filter_by(amount=150, transaction_type='personal_expense').one()
        reverse_cost(self.order.id, self.error.id, self.uid, 'Confirmed personal customs was R350', original.id)
        db.session.commit()

    def line(self, **overrides):
        line = dict(product_id='__new__', name='TYDAL Shirt', brand='TYDAL', category='Shirts',
            size='M', color='Blue', quantity='3', location_id=str(self.location.id),
            goods_total='2475', selling_price='1500')
        line.update(overrides)
        return line

    def test_reverse_only_error_and_prevent_repeat(self):
        before = self.financial_snapshot()
        self.assertEqual(self.order.landed_cost, D('3625'))
        self.assertEqual(self.position(), D('250'))
        self.reverse()
        self.assertEqual(self.order.landed_cost, D('3475'))
        self.assertEqual(self.position(), D('100'))
        self.assertEqual(self.valid.amount, D('350'))
        self.assertIsNone(self.valid.reversal)
        self.assertIsNone(self.business.reversal)
        self.assertEqual(self.financial_snapshot(), before)
        with self.assertRaises(SupplierError):
            reverse_cost(self.order.id, self.error.id, self.uid, 'Again', 1)
        db.session.rollback()
        self.assertEqual(SupplierCostReversal.query.count(), 1)
        self.assertEqual(PartnerTransaction.query.filter_by(description='Opening reclassification').one().amount, D('250'))

    def test_ambiguous_legacy_match_refused(self):
        self.personal_cost(150, 'Erroneous additional customs')
        db.session.commit()
        with self.assertRaises(SupplierError):
            reverse_cost(self.order.id, self.error.id, self.uid, 'Reason', 1)
        db.session.rollback()
        self.assertEqual(SupplierCostReversal.query.count(), 0)

    def test_wrong_partner_link_refused(self):
        self.error.partner_transaction_id = PartnerTransaction.query.filter_by(amount=350).one().id
        db.session.commit()
        with self.assertRaises(SupplierError):
            reverse_cost(self.order.id, self.error.id, self.uid, 'Reason', self.error.partner_transaction_id)
        db.session.rollback()

    def test_financial_reversal(self):
        original = FinancialTransaction.query.filter_by(source_id=self.business.id).one()
        reverse_cost(self.order.id, self.business.id, self.uid, 'Test incorrect cash entry', original.id)
        db.session.commit()
        reversal = FinancialTransaction.query.filter_by(reversal_of_id=original.id).one()
        self.assertEqual(reversal.to_account_id, self.account.id)
        self.assertEqual(reversal.amount, D('650'))
        self.assertEqual(self.order.landed_cost, D('2975'))

    def test_receive_once_and_preserve_all_balances(self):
        self.reverse()
        before = self.financial_snapshot()
        position = self.position()
        receipt = receive_order(self.order.id, self.uid, [self.line()])
        db.session.commit()
        self.assertEqual(self.order.status, 'received')
        self.assertEqual(receipt.purchase.total_amount, D('3475'))
        self.assertEqual(sum(i.line_total for i in receipt.purchase.items), D('3475'))
        self.assertEqual(Product.query.one().quantity, 3)
        self.assertEqual(StockHolding.query.one().quantity, 3)
        self.assertEqual(StockMovement.query.one().quantity, 3)
        self.assertEqual(self.financial_snapshot(), before)
        self.assertEqual(self.position(), position)
        with self.assertRaises(SupplierError):
            receive_order(self.order.id, self.uid, [self.line()])
        db.session.rollback()
        self.assertEqual(Product.query.one().quantity, 3)
        self.assertEqual(SupplierOrderReceipt.query.count(), 1)
        with self.assertRaises(SupplierError):
            reverse_cost(self.order.id, self.valid.id, self.uid, 'Too late', 1)
        db.session.rollback()

    def test_existing_variant_multiple_locations_weighted_cost(self):
        self.reverse()
        product = Product(name='Existing shirt', size='M', color='Blue', quantity=2, cost_price=100)
        other = StockLocation(name='Other partner')
        db.session.add_all([product, other]); db.session.flush()
        db.session.add(StockHolding(product_id=product.id, stock_location_id=self.location.id, quantity=2))
        db.session.commit()
        receive_order(self.order.id, self.uid, [self.line(product_id=str(product.id), quantity='1', goods_total='825'),
            self.line(product_id=str(product.id), quantity='2', goods_total='1650', location_id=str(other.id))])
        db.session.commit()
        self.assertEqual(product.quantity, 5)
        self.assertEqual(product.cost_price, D('735'))
        self.assertEqual(StockMovement.query.count(), 2)
        self.assertEqual(sum(h.quantity for h in product.holdings), 5)
        self.assertEqual(sum(i.line_total for i in PurchaseItem.query.all()), D('3475'))

    def test_new_identity_reuses_existing_product(self):
        self.reverse()
        product = Product(name='TYDAL Shirt', brand='TYDAL', category='Shirts', size='M', color='Blue', quantity=0)
        db.session.add(product); db.session.commit()
        receive_order(self.order.id, self.uid, [self.line()]); db.session.commit()
        self.assertEqual(Product.query.count(), 1)
        self.assertEqual(product.quantity, 3)

    def test_invalid_lines_roll_back(self):
        for overrides in [dict(quantity='0'), dict(quantity='-1'), dict(quantity='1.5'),
            dict(goods_total='NaN'), dict(goods_total='Infinity'), dict(goods_total='1.001'),
            dict(goods_total='0'), dict(goods_total='100'), dict(location_id='999'),
            dict(product_id='999'), dict(name='')]:
            with self.subTest(overrides=overrides):
                with self.assertRaises(SupplierError):
                    receive_order(self.order.id, self.uid, [self.line(**overrides)])
                db.session.rollback()
                self.assertEqual(self.order.status, 'in_transit')
                self.assertEqual(Product.query.count(), 0)
                self.assertEqual(Purchase.query.count(), 0)

    def test_failure_after_stock_write_rolls_back(self):
        before = self.financial_snapshot()
        real_flush = db.session.flush
        def fail_after_movement(*args, **kwargs):
            real_flush(*args, **kwargs)
            if db.session.connection().exec_driver_sql("SELECT count(*) FROM stock_movements").scalar():
                raise RuntimeError('Injected failure after stock write')
        with patch.object(db.session, 'flush', side_effect=fail_after_movement):
            with self.assertRaises(RuntimeError):
                receive_order(self.order.id, self.uid, [self.line()])
        db.session.rollback()
        self.assertEqual(self.order.status, 'in_transit')
        self.assertEqual(Product.query.count(), 0)
        self.assertEqual(StockHolding.query.count(), 0)
        self.assertEqual(StockMovement.query.count(), 0)
        self.assertEqual(Purchase.query.count(), 0)
        self.assertEqual(self.financial_snapshot(), before)

    def test_correction_route_and_new_cost_direct_link(self):
        original = PartnerTransaction.query.filter_by(amount=150, transaction_type='personal_expense').one()
        path = f'/purchases/orders/{self.order.id}/cost/{self.error.id}/reverse'
        self.assertEqual(self.client.post(path, data={'transaction_id':str(original.id), 'reason':'Confirmed erroneous R150'}).status_code, 302)
        self.assertEqual(self.order.landed_cost, D('3475'))
        self.client.post(path, data={'transaction_id':str(original.id), 'reason':'Repeated'})
        self.assertEqual(SupplierCostReversal.query.count(), 1)
        self.client.post(f'/purchases/orders/{self.order.id}/cost', data={
            'cost_type':'shipping', 'description':'Test direct link', 'amount':'10',
            'funding_type':'partner_personal', 'partner_id':str(self.uid)})
        new_cost = SupplierOrderCost.query.filter_by(description='Test direct link').one()
        self.assertIsNotNone(new_cost.partner_transaction_id)
        self.assertEqual(db.session.get(PartnerTransaction, new_cost.partner_transaction_id).amount, D('10'))

    def test_failure_during_reversal_rolls_back(self):
        original = PartnerTransaction.query.filter_by(amount=150, transaction_type='personal_expense').one()
        before = self.position()
        real_flush = db.session.flush
        def fail_on_audit(*args, **kwargs):
            real_flush(*args, **kwargs)
            if db.session.connection().exec_driver_sql('SELECT count(*) FROM supplier_cost_reversals').scalar():
                raise RuntimeError('Injected audit failure')
        with patch.object(db.session, 'flush', side_effect=fail_on_audit):
            with self.assertRaises(RuntimeError):
                reverse_cost(self.order.id, self.error.id, self.uid, 'Reason', original.id)
        db.session.rollback()
        self.assertEqual(self.position(), before)
        self.assertEqual(self.order.landed_cost, D('3625'))
        self.assertEqual(SupplierCostReversal.query.count(), 0)

    def test_proportional_allocation_rounding(self):
        self.assertEqual(allocate(D('1'), [D('1')]*3), [D('.34'), D('.33'), D('.33')])
        self.assertEqual(allocate(D('3475'), [D('825'), D('1650')]), [D('1158.33'), D('2316.67')])

    def test_http_templates_and_receipt_report(self):
        self.reverse()
        for path in [f'/purchases/orders/{self.order.id}', f'/purchases/orders/{self.order.id}/receive',
            f'/purchases/orders/{self.order.id}/cost/{self.valid.id}/reverse']:
            self.assertEqual(self.client.get(path).status_code, 200)
        result = self.client.post(f'/purchases/orders/{self.order.id}/receive', data=self.line())
        self.assertEqual(result.status_code, 302)
        self.assertIn(b'Received items', self.client.get(f'/purchases/orders/{self.order.id}').data)
        for path in ['/purchases/', '/reports/', '/inventory/']:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200)
        from unittest.mock import patch as mock_patch
        with mock_patch('app.routes.reports.render_template') as render:
            render.return_value = 'report'
            self.client.get('/reports/')
            self.assertEqual(render.call_args.kwargs['purchase_spend'], D('0'))

    def test_http_invalid_incomplete_and_csrf(self):
        path = f'/purchases/orders/{self.order.id}/receive'
        self.assertEqual(self.client.post(path, data={'product_id':'__new__'}).status_code, 400)
        self.assertEqual(self.client.post(path, data=self.line(quantity='0')).status_code, 400)
        self.assertEqual(Product.query.count(), 0)
        self.app.config['WTF_CSRF_ENABLED'] = True
        self.assertEqual(self.client.post(path, data=self.line()).status_code, 400)
        self.assertEqual(self.client.post(f'/purchases/orders/{self.order.id}/cost/{self.error.id}/reverse',
            data={'reason':'test','transaction_id':'1'}).status_code, 400)
        self.assertEqual(self.client.post(f'/purchases/orders/{self.order.id}/cost', data={}).status_code, 400)


class ConcurrentSupplierTests(unittest.TestCase):
    def setUp(self):
        from pathlib import Path
        from uuid import uuid4
        self.database = Path('instance') / f'test-supplier-{uuid4().hex}.db'
        self.app = create_app({'TESTING':True, 'SQLALCHEMY_DATABASE_URI':f'sqlite:///{self.database.resolve().as_posix()}'})
        with self.app.app_context():
            db.create_all()
            user = User(name='Fixture', phone='fixture', password_hash='fixture')
            db.session.add(user); db.session.flush()
            order = SupplierOrder(order_number='CONCURRENT', supplier='Fixture', goods_cost=10, created_by_id=user.id)
            location = StockLocation(name='Fixture stock')
            db.session.add_all([order, location]); db.session.flush()
            transaction = PartnerTransaction(partner_id=user.id, transaction_type='personal_expense',
                amount=1, repayment_expected=True, created_by_id=user.id)
            db.session.add(transaction); db.session.flush()
            cost = SupplierOrderCost(supplier_order_id=order.id, cost_type='other', description='Fixture',
                amount=1, funding_type='partner_personal', partner_id=user.id,
                partner_transaction_id=transaction.id, created_by_id=user.id)
            db.session.add(cost); db.session.commit()
            self.uid, self.oid, self.lid, self.cid, self.tid = user.id, order.id, location.id, cost.id, transaction.id
            db.session.remove()

    def tearDown(self):
        with self.app.app_context():
            db.session.remove()
            db.engine.dispose()
        self.database.unlink()

    def race(self, action):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier
        barrier = Barrier(2)
        def worker():
            with self.app.app_context():
                barrier.wait(timeout=10)
                try:
                    action()
                    db.session.commit()
                    return 'success'
                except SupplierError:
                    db.session.rollback()
                    return 'rejected'
                finally:
                    db.session.remove()
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _: worker(), range(2)))
        self.assertEqual(sorted(results), ['rejected', 'success'])

    def test_simultaneous_receipts_increase_stock_once(self):
        self.race(lambda: receive_order(self.oid, self.uid, [{
            'product_id':'__new__', 'name':'Fixture shirt', 'quantity':'1',
            'goods_total':'10', 'location_id':str(self.lid)}]))
        with self.app.app_context():
            self.assertEqual(Product.query.one().quantity, 1)
            self.assertEqual(StockMovement.query.count(), 1)
            self.assertEqual(SupplierOrderReceipt.query.count(), 1)

    def test_simultaneous_reversals_offset_funding_once(self):
        self.race(lambda: reverse_cost(self.oid, self.cid, self.uid, 'Fixture correction', self.tid))
        with self.app.app_context():
            self.assertEqual(SupplierCostReversal.query.count(), 1)
            self.assertEqual(sum(t.amount for t in PartnerTransaction.query.all()), D('0'))
            self.assertEqual(db.session.get(SupplierOrder, self.oid).landed_cost, D('10'))


if __name__ == '__main__':
    unittest.main()
