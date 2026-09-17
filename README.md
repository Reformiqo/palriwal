### Palriwal

Palriwal Customizations

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app palriwal
```

### TCS Engine (buying and selling transactions)

A TCS equivalent of the native ERPNext TDS engine, built to the FRD
"TCS Engine v3.0" and extended to the sales side and to the order and delivery stages.
Four components, matching the four the TDS engine has:

| # | Component | Where |
|---|-----------|-------|
| 1 | `TCS Category` master with `TCS Rate` and `TCS Account` child tables | `palriwal/palriwal/doctype/tcs_*` |
| 2 | `custom_tcs_category` link on Supplier and Customer (active categories only) | `palriwal/palriwal/tcs/custom_fields.py`, `public/js/tcs_party.js` |
| 3 | Engine on Purchase Order, Purchase Receipt, Purchase Invoice, Sales Order, Delivery Note and Sales Invoice: `Apply TCS`, category, threshold logic, automatic tax row, five read-only tracking fields | `palriwal/palriwal/tcs/engine.py`, `tcs_math.py`, `public/js/tcs_transaction.js` |
| 4 | Reports `TCS Computation Summary` (party type filter), `TCS Receivable Monthly` (purchases) and `TCS Payable Monthly` (sales) | `palriwal/palriwal/report/tcs_*` |

Accounting direction, one row per company in the `TCS Account` table:

| Transactions | TCS collected by | Engine row | Account column | Effect |
|--------------|------------------|------------|----------------|--------|
| Purchase Order, Purchase Receipt, Purchase Invoice | the supplier, from us | `Actual`, `Add` in Purchase Taxes and Charges | Receivable Account (Asset, TCS Receivable) | Debited on the invoice; we owe the supplier more |
| Sales Order, Delivery Note, Sales Invoice | us, from the customer | `Actual` in Sales Taxes and Charges | Payable Account (Liability, TCS Payable) | Credited on the invoice; the customer owes us more |

Orders, receipts and delivery notes show the TCS on their totals and hand the engine row, `Apply TCS`
and the category to the invoice through the standard mapping, where the engine recomputes it. Only the
invoice posts GL. The cumulative party total is always measured on submitted invoices, so an order or
receipt shows the position it would create but never counts towards it.

How it runs:

- Custom fields are created idempotently by `after_install` / `after_migrate`, so `bench migrate` is enough.
- The engine runs on `validate` of each transaction (hooks.py `doc_events`). It owns exactly one row in the
  taxes table, flagged `custom_is_tcs_row`, and never touches manually added tax rows.
- The document base (Grand Total or Net Total per category) is measured with the engine row removed, so
  saving repeatedly never changes the amount. The rate row is resolved by posting date, or by transaction
  date on orders. The cumulative party total covers submitted invoices of the party, category and fiscal
  year only.
- The threshold arithmetic has no frappe dependency and is tested against Sheet 13 of the FRD:

```bash
python -m unittest palriwal.palriwal.tcs.test_tcs_math
```

Site setup after install (configuration, not code):

1. Create a `TCS Receivable` ledger (Asset, non-group) for purchases and/or a `TCS Payable` ledger
   (Liability, non-group) for sales, per statutory section or combined.
2. Create a `TCS Category` (Accounts Manager) with the CA-confirmed rate rows and, per company, the
   Receivable Account for purchases and/or the Payable Account for sales. Add a new rate row each
   financial year; never edit an old row.
3. Set `TCS Category` on each supplier that collects TCS from you and on each customer you collect TCS from.
   `Apply TCS` then defaults on their invoices.
4. Optionally add `TCS Category` and the three reports to the Accounting workspace (Taxes section) from the
   workspace editor.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/palriwal
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
