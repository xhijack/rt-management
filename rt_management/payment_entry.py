# your_app/your_app/api/payment_upload.py
import base64
import frappe
from frappe.utils import nowdate, flt, getdate
from frappe import _
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

FILE_SIZE_LIMIT_MB = 15  # batasi ukuran file multipart/base64 agar aman

def _bytes_len(b: bytes) -> int:
    try:
        return len(b) if isinstance(b, (bytes, bytearray)) else 0
    except Exception:
        return 0

def _safe_amount(v):
    """Terima str/int/float/None -> float/None"""
    if v is None or v == "":
        return None
    try:
        return flt(v)
    except Exception:
        frappe.throw(_("Nilai amount tidak valid"))

def _safe_date(v):
    """Terima YYYY-MM-DD/None -> str tanggal valid (YYYY-MM-DD)"""
    if not v:
        return nowdate()
    try:
        return str(getdate(v))
    except Exception:
        frappe.throw(_("Format reference_date tidak valid, gunakan YYYY-MM-DD"))

def _merge_payload():
    """
    Gabungkan payload dari:
    - form-urlencoded / multipart: frappe.local.form_dict
    - JSON body: frappe.request.data
    - files (multipart): frappe.request.files
    """
    data = frappe._dict()

    # 1) form fields
    if frappe.local.form_dict:
        data.update(frappe.local.form_dict)

    # 2) JSON body
    if getattr(frappe, "request", None) and frappe.request.data:
        # Hanya parse JSON jika content-type JSON atau jika form_dict kosong
        ct = (frappe.get_request_header("Content-Type") or "").lower()
        if "application/json" in ct or not data:
            try:
                data.update(frappe.parse_json(frappe.request.data))
            except Exception:
                # biarkan; mungkin memang bukan JSON
                pass

    # 3) files (multipart)
    files = {}
    try:
        if getattr(frappe, "request", None) and getattr(frappe.request, "files", None):
            for key in frappe.request.files:
                files[key] = frappe.request.files[key]
    except Exception:
        pass

    return data, files

def _attach_file(
    *,
    doctype: str,
    name: str,
    file_name: str,
    content_b64: str = None,
    file_url: str = None,
    is_private: int = 1,
    fileobj=None,
):
    """Buat File dan attach ke dokumen. Mendukung:
       - content_b64 (base64)
       - file_url
       - fileobj (werkzeug FileStorage dari multipart)
    """
    if not (content_b64 or file_url or fileobj):
        frappe.throw(_("Wajib kirim salah satu: content_b64, file_url, atau multipart file."))

    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name or "attachment",
        "is_private": is_private,
        "attached_to_doctype": doctype,
        "attached_to_name": name,
    })

    if fileobj:
        blob = fileobj.read()
        if _bytes_len(blob) > FILE_SIZE_LIMIT_MB * 1024 * 1024:
            frappe.throw(_("Ukuran file melebihi {0} MB").format(FILE_SIZE_LIMIT_MB))
        file_doc.content = blob

    elif content_b64:
        try:
            blob = base64.b64decode(content_b64, validate=True)
        except Exception:
            frappe.throw(_("Gagal decode base64 untuk file"))
        if _bytes_len(blob) > FILE_SIZE_LIMIT_MB * 1024 * 1024:
            frappe.throw(_("Ukuran file (base64) melebihi {0} MB").format(FILE_SIZE_LIMIT_MB))
        file_doc.content = blob

    else:
        # file_url
        file_doc.file_url = file_url

    file_doc.insert(ignore_permissions=True)
    return file_doc

def _create_pe_from_si(
    si_name: str,
    amount=None,
    mode_of_payment: str = None,
    reference_no: str = None,
    reference_date: str = None,
):
    """Buat Payment Entry dari Sales Invoice dengan helper bawaan ERPNext."""
    si = frappe.get_doc("Sales Invoice", si_name)
    outstanding = flt(si.outstanding_amount)
    if outstanding <= 0 and (amount is None or flt(amount) <= 0):
        frappe.throw(_("Sales Invoice tidak memiliki outstanding."))

    pe = get_payment_entry("Sales Invoice", si_name)

    # amount: jika None -> gunakan outstanding; jika ada -> clamp ke outstanding
    if amount is None:
        pe.paid_amount = outstanding
    else:
        pe.paid_amount = min(flt(amount), max(0.0, outstanding))

    pe.received_amount = pe.paid_amount

    if mode_of_payment:
        pe.mode_of_payment = mode_of_payment

    if reference_no:
        pe.reference_no = reference_no

    pe.reference_date = _safe_date(reference_date)

    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe

def _create_on_account_pe(
    customer: str,
    amount,
    mode_of_payment: str = None,
    reference_no: str = None,
    reference_date: str = None,
    company: str = None,
):
    """Buat Payment Entry tanpa referensi invoice (on-account)."""
    amt = _safe_amount(amount)
    if not customer or amt is None or amt <= 0:
        frappe.throw(_("Customer dan amount (>0) wajib diisi untuk on-account payment"))

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = customer
    pe.company = company or frappe.defaults.get_user_default("Company")
    pe.paid_amount = amt
    pe.received_amount = amt
    if mode_of_payment:
        pe.mode_of_payment = mode_of_payment
    if reference_no:
        pe.reference_no = reference_no
    pe.reference_date = _safe_date(reference_date)

    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe

@frappe.whitelist(methods=["POST"], allow_guest=True)
def upload_payment_and_create_entry():
    """
    Mendukung:
    - JSON: application/json
    - Form URL Encoded: application/x-www-form-urlencoded
    - Multipart form-data (dengan file langsung, field key: 'file' / 'attachment' / dll)

    Body contoh:
    1) Via Sales Invoice
    {
      "sales_invoice": "SINV-0001",
      "amount": 1000000,                 // optional, default = outstanding
      "mode_of_payment": "Bank Transfer",
      "reference_no": "TRX-123",         // optional
      "reference_date": "2025-08-22",    // optional (YYYY-MM-DD)
      "file_name": "bukti-transfer.pdf",
      "content_b64": "<base64 string>",  // atau gunakan "file_url": "/files/bukti.pdf"
      "is_private": 1                     // optional, default 1
    }

    2) On-account (tanpa SI)
    {
      "customer": "CUST-0001",
      "amount": 500000,
      "mode_of_payment": "Cash",
      "reference_no": "OR-123",
      "company": "SOPWER",
      "file_name": "bukti.jpg",
      "content_b64": "<base64>"
    }
    """
    # ⚠️ Lebih aman pakai auth API key/secret daripada set_user. Biarkan jika memang sengaja.
    frappe.set_user("payment@sopwer.id")

    logger = frappe.logger("payment_upload", allow_site=True, file_count=5)

    data, files = _merge_payload()

    # Ambil generic fields
    sales_invoice = data.get("sales_invoice")
    file_name = (data.get("file_name") or "attachment").strip()
    content_b64 = data.get("content_b64")
    file_url = data.get("file_url")
    is_private = int(data.get("is_private") or 1)

    amount = _safe_amount(data.get("amount"))
    mode_of_payment = (data.get("mode_of_payment") or "").strip() or None
    reference_no = (data.get("reference_no") or "").strip() or None
    reference_date = data.get("reference_date")
    company = (data.get("company") or "").strip() or None
    customer = (data.get("customer") or "").strip() or None

    # pilih fileobj dari multipart jika ada (kunci lazim: 'file' atau 'attachment')
    fileobj = None
    for key in ("file", "attachment", "upload", "bukti", "document"):
        if key in files:
            fileobj = files[key]
            if not file_name or file_name == "attachment":
                try:
                    file_name = files[key].filename or file_name
                except Exception:
                    pass
            break

    # Logging aman (tanpa base64 & tanpa isi file)
    try:
        log_stub = {
            "sales_invoice": sales_invoice,
            "customer": customer,
            "amount": amount,
            "mode_of_payment": mode_of_payment,
            "reference_no": reference_no,
            "reference_date": reference_date,
            "company": company,
            "has_content_b64": bool(content_b64),
            "has_file_url": bool(file_url),
            "has_multipart_file": bool(fileobj),
            "content_b64_length": len(content_b64) if isinstance(content_b64, str) else 0,
        }
        logger.info({"payload": log_stub})
    except Exception:
        pass

    try:
        frappe.db.begin()

        if sales_invoice:
            # 1) Payment Entry dari Sales Invoice
            pe = _create_pe_from_si(
                sales_invoice,
                amount=amount,
                mode_of_payment=mode_of_payment,
                reference_no=reference_no,
                reference_date=reference_date,
            )

            if content_b64 or file_url or fileobj:
                _attach_file(
                    doctype="Payment Entry",
                    name=pe.name,
                    file_name=file_name,
                    content_b64=content_b64,
                    file_url=file_url,
                    is_private=is_private,
                    fileobj=fileobj,
                )
                # opsional: tempel juga ke SI
                _attach_file(
                    doctype="Sales Invoice",
                    name=sales_invoice,
                    file_name=f"{pe.name}-{file_name}",
                    content_b64=content_b64,
                    file_url=file_url,
                    is_private=is_private,
                    fileobj=fileobj,
                )

            frappe.db.commit()
            return {
                "ok": True,
                "data": {
                    "payment_entry": pe.name,
                    "linked_sales_invoice": sales_invoice,
                    "message": _("Payment Entry berhasil dibuat dari Sales Invoice dan file terlampir.") if (content_b64 or file_url or fileobj) else _("Payment Entry berhasil dibuat dari Sales Invoice.")
                }
            }

        # 2) On-account
        pe = _create_on_account_pe(
            customer=customer,
            amount=amount,
            mode_of_payment=mode_of_payment,
            reference_no=reference_no,
            reference_date=reference_date,
            company=company,
        )

        if content_b64 or file_url or fileobj:
            _attach_file(
                doctype="Payment Entry",
                name=pe.name,
                file_name=file_name,
                content_b64=content_b64,
                file_url=file_url,
                is_private=is_private,
                fileobj=fileobj,
            )

        frappe.db.commit()
        return {
            "ok": True,
            "data": {
                "payment_entry": pe.name,
                "message": _("Payment Entry on-account berhasil dibuat dan file terlampir.") if (content_b64 or file_url or fileobj) else _("Payment Entry on-account berhasil dibuat.")
            }
        }

    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "upload_payment_and_create_entry")
        # Kembalikan error yang ramah
        frappe.throw(_("Gagal membuat Payment Entry. Periksa Error Log untuk detailnya."))
