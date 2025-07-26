# report/cash_in_out/cash_in_out.py
import frappe
from frappe.utils import getdate

def execute(filters=None):
    filters = filters or {}
    from_date = filters.get("from_date")
    to_date   = filters.get("to_date")

    # 1. Ambil daftar akun kas/bank non-group
    cash_accounts = frappe.get_all(
        "Account",
        filters={ "account_type": ["in", ["Cash", "Bank"]], "is_group": 0 },
        pluck="name"
    )
    if not cash_accounts:
        frappe.throw("Tidak ada akun Cash/Bank terdaftar.")

    # 2. Query GL Entry + exclude Sales Invoice yang dibatalkan
    #    Tambahkan gle.against sebagai against_account
    data = frappe.db.sql("""
        SELECT
            gle.posting_date,
            gle.account,
            gle.against         AS against_account,
            gle.voucher_type,
            gle.voucher_no,
            SUM(gle.debit)  AS total_in,
            SUM(gle.credit) AS total_out
        FROM `tabGL Entry` gle
        LEFT JOIN `tabSales Invoice` si
          ON si.name = gle.voucher_no
         AND gle.voucher_type = 'Sales Invoice'
        WHERE gle.account IN %(accounts)s
          AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          -- hanya ambil yang bukan SI cancelled
          AND (si.name IS NULL OR si.docstatus != 2)
          AND gle.is_cancelled = 0
        GROUP BY
            gle.posting_date,
            gle.account,
            gle.against,
            gle.voucher_type,
            gle.voucher_no
        ORDER BY gle.posting_date
    """, {
        "accounts":  cash_accounts,
        "from_date": from_date,
        "to_date":   to_date
    }, as_dict=1)

    # 3. Hitung total in & out
    total_in  = sum(d.total_in  for d in data)
    total_out = sum(d.total_out for d in data)

    # 4. Definisikan kolom dengan width yang proporsional (px),
    #    termasuk kolom Against Account
    columns = [
        {"label": "Date",            "fieldname": "posting_date",    "fieldtype": "Date",   "width": 100},
        {"label": "Account",         "fieldname": "account",         "fieldtype": "Link",   "options": "Account", "width": 200},
        {"label": "Against Account", "fieldname": "against_account", "fieldtype": "Data",   "width": 200},
        {"label": "Voucher Type",    "fieldname": "voucher_type",    "fieldtype": "Data",   "width": 140},
        {"label": "Voucher No",      "fieldname": "voucher_no",      "fieldtype": "Data",   "width": 140},
        {"label": "In (Debit)",      "fieldname": "total_in",        "fieldtype": "Currency","width": 120},
        {"label": "Out (Credit)",    "fieldname": "total_out",       "fieldtype": "Currency","width": 120},
    ]

    # 5. Tambahkan baris Total di akhir
    data.append({
        "posting_date":   "Total",
        "account":        "",
        "against_account":"",
        "voucher_type":   "",
        "voucher_no":     "",
        "total_in":       total_in,
        "total_out":      total_out
    })

    return columns, data
