### Palriwal

Palriwal Customizations

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app palriwal
```

### TCS Engine (Supplier and Purchase Invoice)

A TCS equivalent of the native ERPNext TDS engine, built to the FRD
"TCS Engine v3.0". Four components, matching the four the TDS engine has:

| # | Component | Where |
|---|-----------|-------|
| 1 | `TCS Category` master with `TCS Rate` and `TCS Account` child tables | `palriwal/palriwal/doctype/tcs_*` |
| 2 | `Supplier.custom_tcs_category` link (active categories only) | `palriwal/palriwal/tcs/custom_fields.py`, `public/js/tcs_supplier.js` |
| 3 | Purchase Invoice engine: `Apply TCS`, category, threshold logic, automatic `Add` tax row, five read-only tracking fields | `palriwal/palriwal/tcs/engine.py`, `tcs_math.py`, `public/js/tcs_purchase_invoice.js` |
| 4 | Reports `TCS Computation Summary` and `TCS Receivable Monthly` | `palriwal/palriwal/report/tcs_*` |

How it runs:

- Custom fields are created idempotently by `after_install` / `after_migrate`, so `bench migrate` is enough.
- The engine runs on Purchase Invoice `validate` (hooks.py `doc_events`). It owns exactly one row in
  Purchase Taxes and Charges, flagged `custom_is_tcs_row`, `charge_type = Actual`, `add_deduct_tax = Add`,
  posted to the TCS Receivable asset account mapped for the company. Manual tax rows are never touched.
- The invoice base (Grand Total or Net Total per category) is measured with the engine row removed, so
  saving repeatedly never changes the amount. The cumulative party total covers submitted Purchase Invoices
  of the supplier, category and fiscal year only.
- The threshold arithmetic has no frappe dependency and is tested against Sheet 13 of the FRD:

```bash
python -m unittest palriwal.palriwal.tcs.test_tcs_math
```

Site setup after install (configuration, not code):

1. Create a `TCS Receivable` ledger (Asset, non-group) per statutory section or one combined ledger.
2. Create a `TCS Category` (Accounts Manager) with the CA-confirmed rate rows and the company account mapping.
   Add a new rate row each financial year; never edit an old row.
3. Set `TCS Category` on each supplier that collects TCS. `Apply TCS` then defaults on their invoices.
4. Optionally add `TCS Category` and the two reports to the Accounting workspace (Taxes section) from the
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
