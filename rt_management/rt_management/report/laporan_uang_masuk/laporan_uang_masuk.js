// Copyright (c) 2025, PT Sopwer Teknologi Indonesia and contributors
// For license information, please see license.txt


frappe.query_reports["Laporan Uang Masuk"] = {
    "filters": [
        {
            "fieldname":"from_date",
            "label":"From Date",
            "fieldtype":"Date",
            "default": frappe.datetime.add_months(frappe.datetime.get_today(), -1)
        },
        {
            "fieldname":"to_date",
            "label":"To Date",
            "fieldtype":"Date",
            "default": frappe.datetime.get_today()
        }
    ]
};
