# your_app/your_app/api/payment_upload.py
import base64
import frappe
from frappe.utils import nowdate
from frappe import _
from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

def _attach_file(*, doctype: str, name: str, file_name: str, content_b64: str = None, file_url: str = None, is_private: int = 1):
    """Buat File record dan attach ke dokumen."""
    if not (content_b64 or file_url):
        frappe.throw(_("Wajib kirim salah satu: content_b64 atau file_url"))

    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name or "attachment",
        "is_private": is_private,
        "attached_to_doctype": doctype,
        "attached_to_name": name,
    })

    if content_b64:
        try:
            file_doc.content = base64.b64decode(content_b64)
        except Exception:
            frappe.throw(_("Gagal decode base64 untuk file"))
    else:
        file_doc.file_url = file_url

    file_doc.insert(ignore_permissions=True)
    return file_doc

def _create_pe_from_si(si_name: str, amount: float = None, mode_of_payment: str = None,
                       reference_no: str = None, reference_date: str = None):
    """Gunakan helper ERPNext untuk bikin Payment Entry dari Sales Invoice."""
    si = frappe.get_doc("Sales Invoice", si_name)
    pe = get_payment_entry("Sales Invoice", si_name)

    # Override nilai jika pengguna kirim amount
    if amount:
        # batasi maksimal outstanding
        outstanding = max(0, float(si.outstanding_amount))
        pe.paid_amount = min(float(amount), outstanding)
        pe.received_amount = pe.paid_amount

    if mode_of_payment:
        pe.mode_of_payment = mode_of_payment

    if reference_no:
        pe.reference_no = reference_no

    pe.reference_date = reference_date or nowdate()

    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe

def _create_on_account_pe(customer: str, amount: float, mode_of_payment: str = None,
                          reference_no: str = None, reference_date: str = None, company: str = None):
    """Bikin Payment Entry tanpa referensi invoice (on-account)."""
    if not (customer and amount):
        frappe.throw(_("Customer dan amount wajib diisi untuk on-account payment"))

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive"
    pe.party_type = "Customer"
    pe.party = customer
    pe.company = company or frappe.defaults.get_user_default("Company")
    pe.paid_amount = float(amount)
    pe.received_amount = float(amount)
    pe.mode_of_payment = mode_of_payment or None
    pe.reference_no = reference_no or None
    pe.reference_date = reference_date or nowdate()

    # akun kas/bank akan diisi otomatis oleh ERPNext jika MOP terkonfigurasi,
    # tapi aman juga di-biarkan lalu diedit via UI kalau perlu.
    pe.insert(ignore_permissions=True)
    pe.submit()
    return pe

@frappe.whitelist(methods=["POST"], allow_guest=True)
def upload_payment_and_create_entry():
    logger = frappe.logger("payment_upload", allow_site=True)
    """
    Body JSON (pilih salah satu skenario):

    1) Berdasarkan Sales Invoice (disarankan)
    {
      "sales_invoice": "SINV-0001",
      "amount": 1000000,              // optional, default = outstanding
      "mode_of_payment": "Bank Transfer", // optional
      "reference_no": "TRX-123",      // optional
      "reference_date": "2025-08-22", // optional (YYYY-MM-DD)
      "file_name": "bukti-transfer.pdf",
      "content_b64": "<base64 string>", // atau gunakan "file_url": "/files/bukti.pdf"
      "is_private": 1                  // optional, default 1
    }

    2) Tanpa Sales Invoice (on-account):
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
    frappe.set_user("payment@sopwer.id")  # Pastikan user admin untuk akses penuh
    data = frappe.local.form_dict or frappe._dict()
    # Izinkan JSON body
    if frappe.request and frappe.request.data:
        try:
            data.update(frappe.parse_json(frappe.request.data))
        except Exception:
            # jika bukan JSON, ignore
            pass

    sales_invoice = data.get("sales_invoice")
    file_name = data.get("file_name") or "attachment"
    content_b64 = data.get("content_b64")
    file_url = data.get("file_url")
    is_private = int(data.get("is_private") or 1)

    amount = data.get("amount")
    mode_of_payment = data.get("mode_of_payment")
    reference_no = data.get("reference_no")
    reference_date = data.get("reference_date")
    company = data.get("company")
    customer = data.get("customer")
    logger.info(f"Proses Data: {data}")
    try:
        frappe.db.begin()

        if sales_invoice:
            # 1) Buat PE dari SI
            pe = _create_pe_from_si(
                sales_invoice,
                amount=amount,
                mode_of_payment=mode_of_payment,
                reference_no=reference_no,
                reference_date=reference_date,
            )
            # Attach ke Payment Entry
            if content_b64 or file_url:
                _attach_file(
                    doctype="Payment Entry",
                    name=pe.name,
                    file_name=file_name,
                    content_b64=content_b64,
                    file_url=file_url,
                    is_private=is_private,
                )
            # Opsional: juga tempelkan ke SI untuk jejak
            if content_b64 or file_url:
                _attach_file(
                    doctype="Sales Invoice",
                    name=sales_invoice,
                    file_name=f"{pe.name}-{file_name}",
                    content_b64=content_b64,
                    file_url=file_url,
                    is_private=is_private,
                )

            frappe.db.commit()
            return {
                "ok": True,
                "payment_entry": pe.name,
                "linked_sales_invoice": sales_invoice,
                "message": _("Payment Entry berhasil dibuat dari Sales Invoice dan file terlampir.")
            }

        else:
            # 2) On-account (tanpa SI)
            pe = _create_on_account_pe(
                customer=customer,
                amount=amount,
                mode_of_payment=mode_of_payment,
                reference_no=reference_no,
                reference_date=reference_date,
                company=company,
            )
            if content_b64 or file_url:
                _attach_file(
                    doctype="Payment Entry",
                    name=pe.name,
                    file_name=file_name,
                    content_b64=content_b64,
                    file_url=file_url,
                    is_private=is_private,
                )

            frappe.db.commit()
            return {
                "ok": True,
                "payment_entry": pe.name,
                "message": _("Payment Entry on-account berhasil dibuat dan file terlampir.")
            }

    except Exception as e:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "upload_payment_and_create_entry")
        frappe.throw(_("Gagal membuat Payment Entry: {0}").format(str(e)))
