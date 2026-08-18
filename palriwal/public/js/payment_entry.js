// Palriwal customisations for the Payment Entry form.
//
// This file merges the two Client Scripts that previously lived in the site
// database (DocType: Payment Entry, Apply To: Form):
//
//   1. "last series no. pop up = Payment Entry"
//      Shows a dashboard headline with the last document created in the
//      currently selected naming series.
//
//   2. "COMPANY WISE SERIES BIFURGATION IN LIST DROPDOWN = payment entry"
//      Restricts the naming_series dropdown to the series allowed for the
//      selected company.
//
// Loaded through hooks.py -> doctype_js.
//
// IMPORTANT: disable (or delete) the two original Client Scripts on the site.
// If they stay enabled, both the database copy and this file register handlers
// on the same events and every action runs twice.

(function () {
	// -----------------------------------------------------------------
	// 1. Last entry in the selected naming series
	// -----------------------------------------------------------------

	function show_last_series_entry(frm) {
		if (!frm.doc.naming_series) return;

		frappe.call({
			method: "frappe.client.get_list",
			args: {
				doctype: frm.doctype,
				filters: {
					naming_series: frm.doc.naming_series,
				},
				fields: ["name", "creation"],
				order_by: "name desc",
				limit_page_length: 1,
			},
			callback: function (r) {
				if (r.message && r.message.length > 0) {
					let last_doc = r.message[0];
					frm.dashboard.set_headline(
						`Last entry in "${frm.doc.naming_series}" series: <b>${last_doc.name}</b> (created ${frappe.datetime.comment_when(last_doc.creation)})`
					);
				} else {
					frm.dashboard.set_headline(
						`No previous entries found for series "${frm.doc.naming_series}".`
					);
				}
			},
		});
	}

	// -----------------------------------------------------------------
	// 2. Company-wise naming series bifurcation
	// -----------------------------------------------------------------

	const COMPANY_NAMING_SERIES = {
		"Jay Ambey Traders": ["BANK-JAT-.YYYY.-"],
		"PALRIWAL METALS AND MINERALS PRIVATE LIMITED": ["BANK-PM-.YYYY.-"],
	};

	function apply_company_naming_series(frm) {
		// naming_series is only editable before the first save
		if (!frm.is_new()) return;

		// The original script fell back to a bare `ALL_SERIES` identifier here,
		// which was never defined and threw a ReferenceError for any company
		// outside the map (including a form with no company set yet). Falling
		// back to "no restriction" keeps the standard naming_series options
		// intact, which is what the crash effectively produced anyway — minus
		// the exception that aborted the rest of the event chain.
		const options = COMPANY_NAMING_SERIES[frm.doc.company];
		if (!options || options.length === 0) return;

		frm.set_df_property("naming_series", "options", options.join("\n"));
		frm.refresh_field("naming_series");

		// Reset only if the current pick is invalid for this company
		if (!options.includes(frm.doc.naming_series)) {
			frm.set_value("naming_series", options[0]);
		}
	}

	// -----------------------------------------------------------------
	// Handlers
	// -----------------------------------------------------------------

	frappe.ui.form.on("Payment Entry", {
		onload_post_render(frm) {
			apply_company_naming_series(frm);
		},
		refresh(frm) {
			// Order matters: apply_company_naming_series() may change
			// naming_series (which fires the naming_series trigger below), so it
			// runs first. That way every lookup in flight is querying the final
			// series value and the headline cannot land on a stale series.
			apply_company_naming_series(frm);

			if (frm.is_new() && frm.doc.naming_series) {
				show_last_series_entry(frm);
			}
		},
		company(frm) {
			apply_company_naming_series(frm);
		},
		naming_series(frm) {
			show_last_series_entry(frm);
		},
	});
})();
