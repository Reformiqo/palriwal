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

The `Apply TCS` checkbox sits in the document header next to the other flags (after Is Subcontracted on
the orders, after Consider for Tax Withholding on the invoices); the TCS section with the category and the
tracking fields appears below the taxes table while it is ticked.

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

### Delivery Order flow (Purchase Order -> Delivery Order -> Delivery Note -> Purchase Receipt)

Backend replacement for the Server / Client Scripts that ran this flow. Code in
`palriwal/palriwal/delivery_order`, report in `palriwal/palriwal/report/delivery_order_tracker`.

| Step | Where | What happens |
|------|-------|--------------|
| PO -> DO | Purchase Order, `Create > Delivery Order` (Jay Ambey Traders) | Same prompt as before. The Delivery Order may not take more than the PO item's pending qty (PO qty - qty on draft/submitted DOs); checked on every DO save. |
| DO -> DN | Delivery Order, `Create Delivery Note` | Dialog with DO Qty, Delivered, Pending and an editable Qty to Deliver per row (defaults to pending, may be partial). Opens an unsaved Delivery Note with `Delivery Out` and the row links set. |
| DN save | `validate` | Each item row is linked to its Delivery Order row (`custom_delivery_order`, `custom_delivery_order_item`). The linked qty may not exceed the row's pending qty; a fully delivered DO takes nothing more. Items not on the DO stay unlinked and outside the flow. |
| DN submit | `on_submit` | Delivered / Pending Qty and Delivery Status of the DO are recomputed. A draft Purchase Receipt is made for exactly the Delivery Note qty (PO rate, PO taxes, `Stores - <abbr>` warehouse). Returns reduce Delivered Qty and make no receipt. |
| DN cancel | `on_cancel` | Its submitted Purchase Receipts are cancelled, draft ones deleted, and the DO quantities recomputed. |
| PR save | `validate` | A receipt made from a Delivery Note may not receive more of an item than the note delivered (other open receipts of the same note included) and cannot be submitted while the note is not submitted. |
| DO | `Create Payment` | Same Payment Entry as before (grand total, against the PO, one per DO). |

Delivered Qty = sum of submitted Delivery Note qty against the row (returns negative), Pending Qty =
DO Qty - Delivered Qty. Both are recomputed from the Delivery Notes each time (never incremented), on
the DO rows (`custom_delivered_qty`, `custom_pending_qty`) and as totals with a `Delivery Status`
(Not / Partly / Fully Delivered) on the DO. The DO list shows the status as its indicator.

Report **Delivery Order Tracker**: PO, PO item, DO, DO row, DN, DN row, PR and PR row with ordered,
DO, delivered, pending, DN, PR and not-yet-received quantities, dates, statuses, supplier, customer,
item and warehouses. Views: `Transaction Detail` (one line per DN / PR row) and `Delivery Order
Summary` (one line per DO row). Filters: company, DO date range, delivery status, only pending,
Purchase Receipt status (Not Created / Draft / Submitted), PO, DO, supplier, customer, item.

`bench migrate` creates the custom fields and runs `patches/v1_0/setup_delivery_order_tracking`,
which links the rows of existing Delivery Notes to their DO rows and fills Delivered / Pending Qty
on every submitted DO. Existing Purchase Receipts are not changed.

Cutover, once the flow is tested on the site:

1. The app runs before the Server Scripts on the same event, so while they are still enabled the
   receipt is made by the app (with the right qty) and the scripts only report that it exists. The
   app's buttons carry the same labels as the Client Scripts', so each shows once.
2. Disable these scripts (Server Script / Client Script list, untick Enabled / tick Disabled):
   - Server Script `Creating purchase receipt on delivery note submission only if it has delivery out id selected - N`
   - Server Script `Cancelling purchase receipt when delivery note is cancelled`
   - Server Script `Get pending qty in dn creation from po - N`
   - Server Script `Making Delivery Out from PO - N`
   - Server Script `Making Payment Entry from Delivery Out for linked PO- N`
   - Client Script `Making Delivery Note from PO - N` (Purchase Order)
   - Client Script `Making Payment Entry from Delivery Out for linked PO- N` (Delivery Order)
   - Client Script `Updated Creating purchase receipt on delivery note submission only if it has delivery out id selected - N` (Delivery Note)
3. Until the first Server Script above is disabled it still makes a full-DO-qty receipt for a
   Delivery Note *return* that carries `Delivery Out`; the app does not.

The quantity rules have no frappe dependency and are unit tested:

```bash
python -m unittest palriwal.palriwal.delivery_order.test_qty_math
```

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
