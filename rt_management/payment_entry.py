# your_app/your_app/api/payment_upload.py
import base64
import frappe
from frappe.utils import nowdate, flt
from frappe import _
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

@frappe.whitelist(methods=["POST"], allow_guest=True)
def upload_payment_and_create_entry():
    frappe.set_user("payment@sopwer.id")
    """Payload yang didukung (POST body / JSON):
    {
      "sales_invoice": "FG202508007",   // jika ada → buat PE dari SI
      "customer": "Ahmad Dede",         // kalau tanpa SI, wajib
      "amount": 175000,                 // jika SI: default = outstanding; jika on-account: wajib > 0
      "mode_of_payment": "Bank Transfer",
      "reference_no": "123",
      "reference_date": "2025-08-23",
      "file_name": "Screenshot.png",
      "content_b64": "<base64>",
      "is_private": 1
    }
    """
    # opsional: pakai user khusus
    # frappe.set_user("payment@sopwer.id")

    # ---- ambil payload sederhana (form or json) ----
    data = frappe._dict()
    if frappe.local.form_dict:
        data.update(frappe.local.form_dict)
    if getattr(frappe, "request", None) and frappe.request.data:
        try:
            data.update(frappe.parse_json(frappe.request.data))
        except Exception:
            pass

    # ---- ambil field yang kita butuhkan ----
    si_name       = (data.get("sales_invoice") or "").strip()
    customer      = (data.get("customer") or "").strip()
    amount_raw    = data.get("amount")
    mop           = (data.get("mode_of_payment") or "").strip() or None
    ref_no        = (data.get("reference_no") or "").strip() or None
    ref_date      = (data.get("reference_date") or "") or nowdate()
    file_name     = (data.get("file_name") or "attachment").strip()
    content_b64   = data.get("content_b64") or None
    is_private    = int(data.get("is_private") or 1)

    amount = None if amount_raw in (None, "",) else flt(amount_raw)

    logger = frappe.logger("payment_upload", allow_site=True)
    logger.error({
        "si": si_name,
        "customer": customer,
        "amount": amount,
        "mop": mop,
        "ref_no": ref_no,
        "has_b64": bool(content_b64),
    })
    logger.error(frappe.request)

    try:
        frappe.db.begin()

        # ==== CASE 1: dari Sales Invoice ====
        if si_name:
            si = frappe.get_doc("Sales Invoice", si_name)
            outstanding = flt(si.outstanding_amount)
            if outstanding <= 0 and (amount is None or amount <= 0):
                frappe.throw(_("Sales Invoice tidak memiliki outstanding."))

            pe = get_payment_entry("Sales Invoice", si_name)

            # amount None → pakai outstanding; jika ada → clamp ke outstanding
            pe.paid_amount = outstanding if amount is None else min(amount, max(0.0, outstanding))
            pe.received_amount = pe.paid_amount

            if mop: pe.mode_of_payment = mop
            if ref_no: pe.reference_no = ref_no
            pe.reference_date = ref_date

            pe.insert(ignore_permissions=True)
            pe.submit()

            # attach bukti jika ada base64
            if content_b64:
                _attach_b64("Payment Entry", pe.name, file_name, content_b64, is_private)
                _attach_b64("Sales Invoice", si_name, f"{pe.name}-{file_name}", content_b64, is_private)

            frappe.db.commit()
            return {"ok": True, "payment_entry": pe.name, "linked_sales_invoice": si_name}

        # ==== CASE 2: on-account (tanpa SI) ====
        if not customer or amount is None or amount <= 0:
            frappe.throw(_("Customer dan amount (>0) wajib diisi untuk on-account payment"))

        pe = frappe.new_doc("Payment Entry")
        pe.payment_type = "Receive"
        pe.party_type = "Customer"
        pe.party = customer
        pe.paid_amount = amount
        pe.received_amount = amount
        if mop: pe.mode_of_payment = mop
        if ref_no: pe.reference_no = ref_no
        pe.reference_date = ref_date

        # opsional: biarkan company auto default; tambahkan jika perlu:
        # pe.company = data.get("company") or frappe.defaults.get_user_default("Company")

        pe.insert(ignore_permissions=True)
        pe.submit()

        if content_b64:
            _attach_b64("Payment Entry", pe.name, file_name, content_b64, is_private)

        frappe.db.commit()
        return {"ok": True, "payment_entry": pe.name}

    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "upload_payment_and_create_entry")
        frappe.throw(_("Gagal membuat Payment Entry. Cek Error Log untuk detailnya."))


def _attach_b64(doctype: str, name: str, file_name: str, content_b64: str, is_private: int = 1):
    """Attach file dari base64 (ringkas)."""
    try:
        blob = base64.b64decode(content_b64, validate=True)
    except Exception:
        frappe.throw(_("Gagal decode base64 untuk file"))
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name or "attachment",
        "is_private": is_private,
        "attached_to_doctype": doctype,
        "attached_to_name": name,
    })
    file_doc.content = blob
    file_doc.insert(ignore_permissions=True)
    return file_doc
