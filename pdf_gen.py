from pathlib import Path
from datetime import date

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.utils import ImageReader


def _get(d: dict, *keys, default=""):
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _fmt_money(x: float) -> str:
    try:
        return f"{float(x):,.2f} €".replace(",", "X").replace(".", ",").replace("X", " ")
    except Exception:
        return "0,00 €"


def draw_invoice_pdf(pdf_path: Path, company: dict, client: dict, invoice: dict, logo_path: Path | None = None):
    pdf_path = Path(pdf_path)
    pdf_path.parent.mkdir(parents=True, exist_ok=True)

    W, H = A4
    c = canvas.Canvas(str(pdf_path), pagesize=A4)

    # --- Style ---
    left_band_w = 18 * mm
    margin = 18 * mm
    gray = colors.HexColor("#333333")
    light = colors.HexColor("#F2F2F2")

    # --- Left band ---
    c.setFillColor(colors.HexColor("#111111"))
    c.rect(0, 0, left_band_w, H, fill=1, stroke=0)

    # --- Header title ---
    title = _get(invoice, "title", default="FACTURE")
    c.setFillColor(gray)
    c.setFont("Helvetica-Bold", 24)
    c.drawString(left_band_w + margin, H - 28 * mm, title)

    # --- Dates / infos facture (à droite) ---
    issue_date = _get(invoice, "issue_date", default=date.today())
    if isinstance(issue_date, date):
        issue_str = issue_date.strftime("%d/%m/%Y")
    else:
        issue_str = str(issue_date)

    due = _get(invoice, "due", default="À réception")
    op_type = _get(invoice, "operation_type", default="Prestation de services")

    c.setFont("Helvetica", 11)
    x_right = W - margin - 75 * mm
    y0 = H - 40 * mm

    c.drawString(x_right, y0, f"Date de facturation: {issue_str}")
    c.drawString(x_right, y0 - 8 * mm, f"Échéance: {due}")

    # ✅ Type d’opération sous TES infos
    c.setFont("Helvetica-Bold", 11)
    c.drawString(x_right, y0 - 16 * mm, f"Type d’opération: {op_type}")
    c.setFont("Helvetica", 11)

    # --- Logo (si présent) ---
    if logo_path:
        try:
            lp = Path(logo_path)
            if lp.exists():
                img = ImageReader(str(lp))
                c.drawImage(
                    img,
                    left_band_w + margin,
                    H - 55 * mm,
                    width=35 * mm,
                    height=18 * mm,
                    mask="auto"
                )
        except Exception:
            pass

    # --- Company block (TES infos) ---
    comp_brand = _get(company, "brand", default="")
    comp_legal = _get(company, "legal_name", default="")
    comp_name = comp_brand or comp_legal or "Société"

    comp_addr = _get(company, "address1", default="")
    comp_zip = _get(company, "zip", default="")
    comp_city = _get(company, "city", default="")
    comp_country = _get(company, "country", default="")
    comp_phone = _get(company, "phone", default="")
    comp_email = _get(company, "email", default="")
    comp_siret = _get(company, "siret", default="")
    comp_vat_notice = _get(company, "vat_notice", default="TVA non applicable, art. 293 B du CGI")

    x = left_band_w + margin
    y = H - 68 * mm

    c.setFont("Helvetica-Bold", 12)
    c.drawString(x, y, comp_name)

    c.setFont("Helvetica", 11)
    yy = y - 6 * mm

    # Optionnel : afficher le legal_name sous le brand si différent
    if comp_brand and comp_legal and comp_legal != comp_brand:
        c.drawString(x, yy, comp_legal)
        yy -= 6 * mm

    if comp_addr:
        c.drawString(x, yy, comp_addr); yy -= 6 * mm

    line_city = " ".join([p for p in [str(comp_zip).strip(), str(comp_city).strip()] if p])
    if line_city:
        c.drawString(x, yy, line_city); yy -= 6 * mm

    if comp_country:
        c.drawString(x, yy, comp_country); yy -= 6 * mm

    if comp_phone:
        c.drawString(x, yy, f"Tél: {comp_phone}"); yy -= 6 * mm
    if comp_email:
        c.drawString(x, yy, comp_email); yy -= 6 * mm

    # ✅ SIRET + TVA notice sous TES infos
    if comp_siret:
        c.drawString(x, yy, f"Numéro de SIRET {comp_siret}"); yy -= 6 * mm
    if comp_vat_notice:
        c.drawString(x, yy, comp_vat_notice); yy -= 6 * mm

    # --- Client block ---
    c.setFillColor(light)
    box_y = H - 105 * mm
    c.rect(left_band_w + margin, box_y - 35 * mm, W - (left_band_w + 2 * margin), 35 * mm, fill=1, stroke=0)
    c.setFillColor(gray)

    cx = left_band_w + margin + 6 * mm
    cy = box_y - 10 * mm

    client_name = _get(client, "name", "nom", default="Client")
    client_addr = _get(client, "address1", "adresse", default="")
    client_zip = _get(client, "zip_code", "zip", "cp", default="")
    client_city = _get(client, "city", "ville", default="")
    client_siret = _get(client, "siret", default="")

    c.setFont("Helvetica-Bold", 12)
    c.drawString(cx, cy, client_name)

    c.setFont("Helvetica", 11)
    cy -= 7 * mm
    if client_addr:
        c.drawString(cx, cy, client_addr); cy -= 6 * mm
    line_city = " ".join([p for p in [str(client_zip).strip(), str(client_city).strip()] if p])
    if line_city:
        c.drawString(cx, cy, line_city); cy -= 6 * mm
    if client_siret:
        c.drawString(cx, cy, f"SIRET client: {client_siret}"); cy -= 6 * mm

    # --- Table (1 ligne) ---
    table_x = left_band_w + margin
    table_y = H - 155 * mm
    table_w = W - (left_band_w + 2 * margin)
    row_h = 10 * mm

    # header
    c.setFillColor(colors.HexColor("#222222"))
    c.rect(table_x, table_y, table_w, row_h, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 10)

    c.drawString(table_x + 4 * mm, table_y + 3 * mm, "Désignation")
    c.drawString(table_x + table_w - 55 * mm, table_y + 3 * mm, "Qté")
    c.drawString(table_x + table_w - 35 * mm, table_y + 3 * mm, "PU")
    c.drawString(table_x + table_w - 18 * mm, table_y + 3 * mm, "Total")

    # row
    c.setFillColor(colors.white)
    c.rect(table_x, table_y - row_h, table_w, row_h, fill=1, stroke=1)
    c.setFillColor(gray)
    c.setFont("Helvetica", 10)

    desc = _get(invoice, "description", default="")
    qty = float(_get(invoice, "qty", default=1))
    unit_price = float(_get(invoice, "unit_price", default=0))
    total_ttc = float(_get(invoice, "total_ttc", default=qty * unit_price))

    c.drawString(table_x + 4 * mm, table_y - row_h + 3 * mm, desc[:80])
    c.drawRightString(table_x + table_w - 50 * mm, table_y - row_h + 3 * mm, f"{qty:g}")
    c.drawRightString(table_x + table_w - 30 * mm, table_y - row_h + 3 * mm, _fmt_money(unit_price))
    c.drawRightString(table_x + table_w - 4 * mm, table_y - row_h + 3 * mm, _fmt_money(total_ttc))

    # --- Totals (TTC only) ---
    totals_y = table_y - 30 * mm
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(table_x + table_w, totals_y, f"TOTAL TTC (TVA non applicable) : {_fmt_money(total_ttc)}")

    # --- Footer ---
    c.setFont("Helvetica", 9)
    footer = comp_vat_notice or "TVA non applicable, art. 293 B du CGI"
    c.drawString(left_band_w + margin, 15 * mm, footer)

    c.showPage()
    c.save()
