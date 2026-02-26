from pathlib import Path
from datetime import date
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader

def eur(x: float) -> str:
    return f"{x:,.2f} €".replace(",", " ").replace(".", ",")

def safe_str(v):
    return (v or "").strip()

def draw_invoice_pdf(
    out_path: Path,
    company: dict,
    client: dict,
    invoice: dict,
    logo_path: Path | None
):
    out_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out_path), pagesize=A4)
    W, H = A4

    left = 20 * mm
    right = W - 20 * mm
    top = H - 20 * mm

    # LOGO (top-left)
    y = top
    if logo_path and logo_path.exists():
        try:
            img = ImageReader(str(logo_path))
            c.drawImage(img, left, y - 18*mm, width=40*mm, height=18*mm, mask='auto')
        except:
            pass

    # TITLE (top-right)
    c.setFont("Helvetica-Bold", 18)
    c.drawRightString(right, y - 5*mm, f"{invoice['title']}")

    c.setFont("Helvetica", 9)
    c.drawRightString(right, y - 12*mm, f"Date de facturation: {invoice['issue_date'].strftime('%d/%m/%Y')}")
    c.drawRightString(right, y - 17*mm, f"Échéance: {invoice['due']}")
    c.drawRightString(right, y - 22*mm, f"Type d'opération: {invoice['operation_type']}")

    # COMPANY BLOCK (left)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(left, y - 30*mm, safe_str(company.get("legal_name") or company.get("brand")))
    c.setFont("Helvetica", 10)
    c.drawString(left, y - 35*mm, safe_str(company.get("address1")))
    c.drawString(left, y - 40*mm, f"{safe_str(company.get('zip'))} {safe_str(company.get('city'))}")
    if safe_str(company.get("phone")):
        c.drawString(left, y - 45*mm, safe_str(company.get("phone")))
    if safe_str(company.get("email")):
        c.drawString(left, y - 50*mm, safe_str(company.get("email")))

    # ✅ TVA line under YOUR block (not client's)
    c.setFont("Helvetica", 9)
    if safe_str(company.get("siret")):
        c.drawString(left, y - 58*mm, f"Numéro de SIRET {safe_str(company.get('siret'))}")
    if safe_str(company.get("vat_notice")):
        c.drawString(left, y - 63*mm, safe_str(company.get("vat_notice")))

    # CLIENT BLOCK (right)
    cx = right - 80*mm
    cy = y - 35*mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(cx, cy, safe_str(client["name"]))
    c.setFont("Helvetica", 11)
    if safe_str(client.get("address1")):
        c.drawString(cx, cy - 6*mm, safe_str(client.get("address1")))
    line2 = " ".join([safe_str(client.get("zip")), safe_str(client.get("city"))]).strip()
    if line2:
        c.drawString(cx, cy - 12*mm, line2)
    if safe_str(client.get("country")):
        c.drawString(cx, cy - 18*mm, safe_str(client.get("country")))

    # SIRET/TVA client (optional)
    c.setFont("Helvetica", 9)
    if safe_str(client.get("siret")):
        c.drawString(cx, cy - 26*mm, f"Numéro de SIRET {safe_str(client.get('siret'))}")
    if safe_str(client.get("tva")):
        c.drawString(cx, cy - 31*mm, f"Numéro de TVA {safe_str(client.get('tva'))}")

    # TABLE
    table_top = y - 80*mm
    c.setLineWidth(0.6)
    c.line(left, table_top, right, table_top)

    headers = ["No.", "Description", "Date", "Qté", "Unité", "Prix unitaire", "TVA", "Montant"]
    cols = [left, left+12*mm, left+95*mm, left+120*mm, left+132*mm, left+150*mm, left+172*mm, left+185*mm]
    c.setFont("Helvetica-Bold", 9)
    for i,hdr in enumerate(headers):
        c.drawString(cols[i], table_top - 6*mm, hdr)

    c.setFont("Helvetica", 9)
    row_y = table_top - 14*mm
    c.drawString(cols[0], row_y, "1")
    c.drawString(cols[1], row_y, safe_str(invoice["description"])[:60])
    c.drawString(cols[2], row_y, invoice["issue_date"].strftime("%d/%m/%Y"))
    c.drawRightString(cols[3]+10*mm, row_y, str(invoice["qty"]))
    c.drawString(cols[4], row_y, safe_str(invoice["unit"]))
    c.drawRightString(cols[5]+18*mm, row_y, eur(invoice["unit_price"]))
    c.drawRightString(cols[6]+10*mm, row_y, f"{invoice['tax_rate']:.2f} %".replace(".", ","))
    c.drawRightString(right, row_y, eur(invoice["total_ht"]))

    c.line(left, row_y - 4*mm, right, row_y - 4*mm)

    # TOTALS (bottom-right)
    totals_y = row_y - 20*mm
    c.setFont("Helvetica", 10)
    c.drawRightString(right - 25*mm, totals_y, "Total HT")
    c.drawRightString(right, totals_y, eur(invoice["total_ht"]))
    c.drawRightString(right - 25*mm, totals_y - 6*mm, f"TVA {invoice['tax_rate']:.2f} %".replace(".", ","))
    c.drawRightString(right, totals_y - 6*mm, eur(invoice["total_tva"]))
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(right - 25*mm, totals_y - 12*mm, "Total TTC")
    c.drawRightString(right, totals_y - 12*mm, eur(invoice["total_ttc"]))

    # FOOTER (bottom center) ✅ restores "bottom of page"
    footer_y = 15 * mm
    c.setFont("Helvetica", 8)
    footer_line = f"{safe_str(company.get('legal_name') or company.get('brand'))} — {safe_str(company.get('address1'))} — {safe_str(company.get('zip'))} {safe_str(company.get('city'))}"
    c.drawCentredString(W/2, footer_y + 6*mm, footer_line)
    if safe_str(company.get("siret")):
        c.drawCentredString(W/2, footer_y, f"Numéro de SIRET : {safe_str(company.get('siret'))}")

    c.showPage()
    c.save()
