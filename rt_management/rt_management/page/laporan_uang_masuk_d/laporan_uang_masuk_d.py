# report/cash_in_out/cash_in_out.py
import frappe
from frappe.utils import flt

@frappe.whitelist()
def get_data(from_date, to_date, account=None):
    # 1. Pastikan filter cash/bank account diberikan
    if not account:
        frappe.throw("Pilih satu Cash/Bank Account terlebih dahulu.")
    args = {"from_date": from_date, "to_date": to_date, "account": account}

    # 2. Hitung Saldo Awal
    opening = flt(frappe.db.sql("""
        SELECT COALESCE(SUM(debit)-SUM(credit),0)
        FROM `tabGL Entry`
        WHERE posting_date < %(from_date)s
          AND account = %(account)s
          AND is_cancelled = 0
    """, args)[0][0])

    # 3. Ambil semua Payment Entry Reference untuk account & periode
    payments = frappe.db.sql("""
        SELECT pe.name AS pe_name, ref.reference_name AS si_name,
               ref.allocated_amount AS alloc
        FROM `tabPayment Entry Reference` ref
        JOIN `tabPayment Entry` pe
          ON pe.name = ref.parent
         AND pe.docstatus = 1
         AND pe.paid_to = %(account)s
         AND pe.posting_date BETWEEN %(from_date)s AND %(to_date)s
        WHERE ref.allocated_amount > 0
    """, args, as_dict=1)

    # 4. Prorate per Sales Invoice Item → kumpulkan per income_account
    incoming_map = {}
    for p in payments:
        si = frappe.get_doc("Sales Invoice", p.si_name)
        # total invoice untuk proporsi
        total_si = flt(si.grand_total) or 1.0
        for item in si.items:
            inc_acc = item.income_account
            # prorate berdasarkan proporsi amount/keseluruhan
            amount = flt(p.alloc) * (flt(item.amount) / total_si)
            incoming_map[inc_acc] = incoming_map.get(inc_acc, 0.0) + amount

    # 5. Bentuk list dict untuk render
    incoming = [
        {"income_account": acc, "total": total}
        for acc, total in incoming_map.items()
    ]
    # Urutkan descending
    incoming.sort(key=lambda x: x["total"], reverse=True)

    # 6. Uang Keluar (GL Entry seperti sebelumnya)
    outgoing = frappe.db.sql("""
        SELECT gle.against AS expense_account,
               SUM(gle.credit) AS total
        FROM `tabGL Entry` gle
        WHERE gle.account = %(account)s
          AND gle.posting_date BETWEEN %(from_date)s AND %(to_date)s
          AND gle.credit > 0
          AND gle.is_cancelled = 0
        GROUP BY gle.against
        ORDER BY total DESC
    """, args, as_dict=1)

    # 7. Hitung Uang Sisa
    total_in   = sum(d["total"] for d in incoming)
    total_out  = sum(d["total"] for d in outgoing)
    balance    = opening + total_in - total_out

    return {
        "opening": opening,
        "in":      incoming,
        "out":     outgoing,
        "balance": balance
    }
