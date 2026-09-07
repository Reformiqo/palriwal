### Palriwal

Palriwal Customizations

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app palriwal
```

### TCS Engine (Purchase and Sales Invoices)

A TCS equivalent of the native ERPNext TDS engine, built to the FRD
"TCS Engine v3.0" and extended to the sales side. Four components, matching the four the TDS engine has:

| # | Component | Where |
|---|-----------|-------|
| 1 | `TCS Category` master with `TCS Rate` and `TCS Account` child tables | `palriwal/palriwal/doctype/tcs_*` |
| 2 | `custom_tcs_category` link on Supplier and Customer (active categories only) | `palriwal/palriwal/tcs/custom_fields.py`, `public/js/tcs_party.js` |
| 3 | Invoice engine on Purchase Invoice and Sales Invoice: `Apply TCS`, category, threshold logic, automatic tax row, five read-only tracking fields | `palriwal/palriwal/tcs/engine.py`, `tcs_math.py`, `public/js/tcs_invoice.js` |
| 4 | Reports `TCS Computation Summary` (party type filter), `TCS Receivable Monthly` (purchases) and `TCS Payable Monthly` (sales) | `palriwal/palriwal/report/tcs_*` |

Accounting direction, one row per company in the `TCS Account` table:

| Invoice | TCS collected by | Engine row | Account column | Effect |
|---------|------------------|------------|----------------|--------|
| Purchase Invoice | the supplier, from us | `Actual`, `Add` in Purchase Taxes and Charges | Receivable Account (Asset, TCS Receivable) | Debited; we owe the supplier more |
| Sales Invoice | us, from the customer | `Actual` in Sales Taxes and Charges | Payable Account (Liability, TCS Payable) | Credited; the customer owes us more |

How it runs:

- Custom fields are created idempotently by `after_install` / `after_migrate`, so `bench migrate` is enough.
- The engine runs on invoice `validate` (hooks.py `doc_events`). It owns exactly one row in the taxes table,
  flagged `custom_is_tcs_row`, and never touches manually added tax rows.
- The invoice base (Grand Total or Net Total per category) is measured with the engine row removed, so
  saving repeatedly never changes the amount. The cumulative party total covers submitted invoices of the
  same type for the party, category and fiscal year only.
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
