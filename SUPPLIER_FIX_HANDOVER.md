# Supplier correction and receiving handover

Local implementation is ready for review. No production deployment, migration, payment correction, or parcel receipt has been performed.

## Inspection

- Starting branch: `main`; baseline commit: `8d7dc43` (`Stop tracking local database and Python cache files`). Starting worktree was clean.
- Development branch: `fix/supplier-cost-reversal-receiving`. This handover accompanies the reviewed local implementation commit.
- `instance/tdm.db` is ignored and untracked. It is at migration `c4f1a8d9e221`, with **no supplier orders, landed costs, or personal-expense transactions**. Consequently the actual erroneous R150 ID and its production partner position cannot be determined locally. No claim is made that production matches this checkout.
- Supplier orders and adding landed costs were implemented. Receive Order had no route or form. There was no cost reversal mechanism. FinancialTransaction already supported `reversal_of_id`; legacy personal-funded costs had no partner-transaction FK.
- Inventory, sales, purchases and movements use one Product per size/colour, grouped into families in the inventory UI. ProductVariant is defined but unused by every route. Receiving preserves the active representation rather than introducing a second stock counter.

## Implementation and files

- `app/services/supplier_orders.py`: transaction-scoped correction and receipt operations; conditional order updates serialize changes. Callers commit once or roll back completely.
- `app/models.py` and migration `d8e2b6a41001`: link new costs to partner transactions, append uniquely linked reversal audits, and link one supplier order to one receipt Purchase. Existing records are retained.
- `app/routes/purchases.py` and purchase templates: review/confirm a correction, require its reason and original funding transaction ID, enter actual received lines and stock locations, and display receipt allocations. New forms and the existing cost form use Flask-WTF CSRF validation.
- `app/routes/reports.py` and purchases summary: receipt value is excluded from new purchase spending. A receipt is labelled as previously paid stock in purchase history.
- `app/__init__.py`: optional configuration override for isolated tests. No startup schema creation.
- `tests/test_supplier_orders.py`: 16 focused tests, including simultaneous requests against file-backed SQLite.
- `scripts/audit_supplier_orders.py`: read-only record inspection, usable before migration.
- `scripts/verify_supplier_migration.py`: upgrade/downgrade verification on a disposable copy; source database is opened read-only.

## R150 correction procedure

1. Obtain actual production evidence using the read-only audit script below. Confirm the Alibaba order, cost ID, partner name, original accounting transaction ID, descriptions, timestamps and amount. Inspect the legitimate R350 and R650 records and existing R250 opening-money correction too.
2. Approve that specific correction before changing production. This implementation does not select a record merely because its amount is R150.
3. After approved deployment/migration, open the identified order and select **Review correction** on the erroneous cost. Review its original funding transaction, enter the reason (Sbusiso confirmed R350 personal customs; this R150 was erroneous), then confirm once.
4. Historical partner funding is accepted only when partner, amount, type, repayment flag, description/order number, timestamp, creator and notes uniquely match. Ambiguous or missing matches are refused. New costs use a direct FK. If historical matching fails, investigate; do not weaken the match or guess an ID.
5. The original positive cost remains visible with its reversal reason and date and is excluded from effective landed cost. There is no negative landed-cost row. A signed negative `personal_expense` contra entry cancels the original partner funding; existing partner and reporting calculations already sum these amounts. The audit links both entries.
6. Expected result: duties R1,000; landed cost R3,475; legitimate personal funding R350; TYDAL funding R650. The partner position moves **R150 toward the partner owing TYDAL**, relative to the erroneous position. Its absolute value requires actual production history. The opening-money R250 reclassification remains untouched. No money-account entry is created for a personal-funded reversal.

A TYDAL-funded correction, if explicitly selected, instead appends a financial reversal with swapped account direction and `reversal_of_id`. Both paths refuse duplicate reversals. Corrections are locked after receipt.

## Receiving procedure

Receive only after the actual parcel arrives and the R150 correction is verified. Open the supplier order, select **Receive Order**, and choose existing products/variants or enter new family, brand, category, size, colour and selling price. Enter quantities, stock locations/holding partners, and the goods cost for each **whole line**.

Goods line totals must sum to the recorded goods cost (R2,475). The current effective landed cost (expected R3,475) is allocated in proportion to those totals using deterministic largest-remainder rounding. PurchaseItem line totals retain the exact allocation; unit costs and weighted-average Product costs are rounded to cents under the existing schema, so multiplying displayed unit cost by quantity can differ from the exact line total by a few cents.

Receipt creates a Purchase, its items, holdings and incoming stock movements, and changes the order to `received` atomically. It creates no FinancialTransaction, PartnerTransaction, Expense or Sale. Existing account and partner balances remain unchanged. Duplicate requests, inactive/missing selections, invalid quantities, incomplete forms, goods total mismatches and existing product/holding quantity disagreements are refused. Multiple lines can allocate stock across different partners. Existing matching product identities are reused; ambiguous identities require an explicit existing-product selection.

## Validation

Run from the repository root with its existing virtual environment:

```powershell
.\venv\Scripts\python.exe -m unittest discover -s tests -v
.\venv\Scripts\python.exe -m scripts.verify_supplier_migration instance/tdm.db
.\venv\Scripts\python.exe scripts/audit_supplier_orders.py instance/tdm.db
git diff --check
```

Results: **16 tests passed**. Tested legitimate R350/R650 preservation, R250 preservation, R150-only reversal, correct partner movement, duplicate/ambiguous correction rejection, cash reversal, receiving once, existing variants and new identities, proportional rounding, multiple locations, unchanged ledgers, invalid/incomplete inputs, CSRF, full rollback after stock or audit writes, and simultaneous receipt/reversal requests. Migration upgrade and downgrade passed on a copy of the local pre-migration database; existing rows were preserved and foreign-key checks passed. The original local database remains at `c4f1a8d9e221`.

The verification script expects a source at `c4f1a8d9e221`; do not point application tests at a business database. Existing `datetime.utcnow()` deprecation warnings remain. Production data and an actual browser session have not been tested.

## Deployment preparation — execute only after explicit approval

The intended source, migration, supporting audit/verification scripts, tests and this handover are committed locally after diff review and a fresh passing run of all 16 tests. No push, merge or deployment has been performed. Never stage the instance directory, `.env`, audit output, backups or business database files. Publish the reviewed branch through the normal review process.

On PythonAnywhere, use the application's configured virtual environment. Record the **actual production commit**, database revision and ledger/partner snapshots. Review production worktree differences before checking out a reviewed release. Keep database backup/audit output outside Git and private.

Read-only inspection command, after the reviewed audit script is available:

```bash
cd /home/Tydalapp/TDM
python scripts/audit_supplier_orders.py /home/Tydalapp/TDM/instance/tdm.db
python -m flask --app run:app db current
git status --short
git rev-parse HEAD
```

Pause application writes before backing up and migrating. Create a consistent backup using SQLite's backup API; choose a new destination and keep all writers paused until the migration and smoke checks finish:

```bash
python - <<'PY'
from contextlib import closing
from datetime import datetime
from pathlib import Path
import sqlite3
source = Path('/home/Tydalapp/TDM/instance/tdm.db')
backup = Path('/home/Tydalapp') / ('tdm-before-supplier-fix-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f') + '.sqlite-backup')
with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
    with closing(sqlite3.connect(backup)) as dst:
        src.backup(dst)
print(backup)
PY
```

After backup verification and approved release checkout:

```bash
python -m unittest discover -s tests -v
python -m flask --app run:app db current
python -m flask --app run:app db upgrade d8e2b6a41001
python -m flask --app run:app db current
```

Use PythonAnywhere's Web tab to reload the configured app. Confirm login, supplier order detail, correction review and receipt form render before resuming writes. Apply the separately approved R150 correction and verify actual ledger snapshots. **Do not confirm receipt while the parcel is in transit.** Never upload a local database over production.

## Rollback

- Before any new correction/receipt business writes, return to the recorded production code commit. If schema restoration is needed, restore the verified backup while all application connections and writers are stopped, then reload. Local baseline `8d7dc43` is not proof of the previously deployed production commit.
- After any corrections or receipts, do not simply revert code or downgrade schema: old code would count voided costs and receipts incorrectly, and downgrade would remove audit links. Prefer a forward repair. A full code/database restore requires explicit approval, a fresh backup of the current state, and a plan to preserve/replay all intervening business activity.
- The migration downgrade was tested only on a disposable copy. It is not an approved production rollback command.
