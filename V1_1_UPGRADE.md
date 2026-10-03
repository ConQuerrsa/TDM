# TDM v1.1 Upgrade

This package is designed to be copied over the synchronized `f4e40bd` TDM codebase.
It does not contain or replace `instance/tdm.db`, `.env`, `.git`, or the virtual environment.

## What v1.1 adds
- Partner Draw: permanent partner withdrawal with no debt created.
- Partial/credit sales: agreed price, paid-now amount, outstanding balance and later settlement.
- Existing `TDM-260930-0001` is safely corrected only if it still has the old R200 total: agreed R400, paid R200, outstanding R200.
- Other Money In: debt recoveries/refunds/other receipts without pretending they are product sales.
- Settings page and creation of new money locations (use it to create `Petty Cash`).
- ProductVariant foundation: every existing product gets a compatibility variant without changing its current quantity.
- Inventory Stock Age and explicit SOLD OUT state.
- Removes the temporary demo-sale cleanup route by replacing `sales.py`.

## Local PC first
1. Back up your local DB if you use one.
2. Extract this package into the TDM project root and allow replacement of matching files.
3. Activate the normal TDM virtual environment.
4. Run:

   flask --app run.py db upgrade

5. Start TDM and test:

   python run.py

6. Test these flows before deployment:
   - Settings opens.
   - Add a temporary/test money location if desired.
   - New Sale accepts paid-now less than agreed total.
   - Sales page shows outstanding balance and can receive a later payment.
   - Partner transaction list includes Partner Draw.
   - Money page includes Other money in.
   - Inventory shows SOLD OUT / Low Stock and stock age.

## Production deployment
Before the production migration, keep the backup already created at:
`/home/Tydalapp/tdm-backup-before-v1.1.db`

After committing/pushing the tested PC code, on PythonAnywhere:

   cd ~/TDM
   git pull origin main
   source venv/bin/activate
   flask --app run.py db upgrade

Then reload the PythonAnywhere web app.

Do not run `db.create_all()`. Do not restore/reset/checkout `instance/tdm.db`.

## Enter the two new real transactions after deployment
1. Settings -> Money locations -> add `Petty Cash` (type Cash), if it does not already exist.
2. Money -> Other money in:
   - Type: Historical debt recovery
   - Amount: R100
   - Destination: Petty Cash
   - Date is automatically the actual receipt date/time; explain the old debt in the note.
3. Partners -> Record transaction:
   - Partner: Lindoh
   - Type: Partner Draw
   - Amount: R100
   - Money location: Lindoh Bank Account
   This reduces TYDAL money by R100 and does not increase Lindoh's debt.

## Important accounting behavior
A sale's `total_amount` is now the agreed selling value. Only `amount_paid` creates cash in the financial ledger. Later payments create `sale_payment` ledger entries and do not remove stock again.
