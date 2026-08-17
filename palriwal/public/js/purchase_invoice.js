// Palriwal customisations for the Purchase Invoice form.
//
// This file merges the two Client Scripts that previously lived in the site
// database (DocType: Purchase Invoice, Apply To: Form):
//
//   1. "last series no. pop up - purchase invoice"
//      Shows an intro banner with the last document created in the currently
//      selected naming series.
//
//   2. "COMPANY WISE SERIES BIFURGATION IN LIST DROPDOWN"
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

	const FILTER_BY_COMPANY = true;

	function series_to_like_pattern(series) {
		if (!series) return null;
		return (
			series
				.replace(/\.#+\./g, "%")
				.replace(/\.(YYYY|YY|MMMM|MM|DD|WW|FY)\./g, "%")
				.replace(/#+/g, "%")
				.replace(/\./g, "") + "%"
		);
	}

	function show_last_series_entry(frm) {
		frm.set_intro(null);
		frm.__series_token = (frm.__series_token || 0) + 1;
		const token = frm.__series_token;

		if (!frm.is_new() || !frm.doc.naming_series) return;

		const series = frm.doc.naming_series;
		const filters = { name: ["like", series_to_like_pattern(series)] };
		if (FILTER_BY_COMPANY && frm.doc.company) filters.company = frm.doc.company;

		frappe.db
			.get_list("Purchase Invoice", {
				filters: filters,
				fields: ["name", "creation"],
				order_by: "name desc",
				limit: 1,
			})
			.then((r) => {
				if (token !== frm.__series_token) return;

				if (!r || !r.length) {
					frm.set_intro(__('No entries yet in "{0}" series.', [series]), "blue");
					return;
				}

				const d = r[0];
				const link = `<a href="/app/purchase-invoice/${encodeURIComponent(d.name)}"
                         target="_blank"><b>${frappe.utils.escape_html(d.name)}</b></a>`;

				frm.set_intro(
					__('Last entry in "{0}" series: {1} (created {2})', [
						series,
						link,
						frappe.datetime.comment_when(d.creation),
					]),
					"blue"
				);
			});
	}

	// -----------------------------------------------------------------
	// 2. Company-wise naming series bifurcation
	// -----------------------------------------------------------------

	const COMPANY_NAMING_SERIES = {
		"Jay Ambey Traders": [
			"PI/.#####./26-27",
			"TI/.#####./26-27",
			"PIFE/.#####.26-27",
			"CN/.#####./26-27",
			"DN/.#####./26-27",
		],
		"PALRIWAL METALS AND MINERALS PRIVATE LIMITED": ["PINV-.YY.-"],
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

	frappe.ui.form.on("Purchase Invoice", {
		onload_post_render(frm) {
			apply_company_naming_series(frm);
		},
		refresh(frm) {
			// Order matters: apply_company_naming_series() may change
			// naming_series, so the banner is drawn after it to reflect the final
			// value. The token guard in show_last_series_entry() discards any
			// superseded lookup.
			apply_company_naming_series(frm);
			show_last_series_entry(frm);
		},
		company(frm) {
			apply_company_naming_series(frm);
			show_last_series_entry(frm);
		},
		naming_series(frm) {
			show_last_series_entry(frm);
		},
	});
})();
