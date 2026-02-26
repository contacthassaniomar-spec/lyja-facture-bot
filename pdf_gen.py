# pdf_gen.py
from __future__ import annotations

from pathlib import Path
from datetime import date
from typing import Dict, Any

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle


def _fmt_money(v: float) -> str:
    # format français: 1100,00 €
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", " ")
    return f"{s} €"


def _safe(d: Dict[str, Any], *keys: str, default: str = "") -> str:
    for k in keys:
        v = d.get(k)
        if v is not None and str(v).strip() != "":
            return str(v)
    return default


def draw_invoice_pdf(
    out_path: Path,
    company: Dict[str, Any],
    client: Dict[str, Any],
    inv: Dict[str, Any],
    logo_path: Path | None = None,
):
    """
    Génère une facture PDF A4.
    - company: dict depuis config.json "company"
    - client: dict depuis db
    - inv: dict facture (number, issue_date, due, operation_type, description, qty, unit, unit_price, total_ht, total_tva, total_ttc...)
    - logo_path: Path vers assets/logo.png
    """
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    c = canvas.Canvas(str(out_path), pagesize=A4)
    W, H = A4

    # --- Thème / couleurs ---
    # Tu peux changer ici si tu veux une autre esthétique
    BAND_COLOR = colors.HexColor("#6D28D9")      # violet (bande gauche)
    ACCENT = colors.HexColor("#111827")          # quasi noir
    LIGHT_BG = colors.HexColor("#F3F4F6")        # gris clair
    MID_GREY = colors.HexColor("#6B7280")

    margin = 18 * mm
    band_w = 18 * mm

    # Fond blanc
    c.setFillColor(colors.white)
    c.rect(0, 0, W, H, stroke=0, fill=1)

    # Bande gauche colorée
    c.setFillColor(BAND_COLOR)
    c.rect(0, 0, band_w, H, stroke=0, fill=1)

    # --- Header ---
    top_y = H - margin

    # Logo (en haut à gauche dans la zone blanche, à côté de la bande)
    logo_drawn = False
    if logo_path:
        try:
            lp = Path(logo_path)
            if lp.exists():
                # zone logo
                x = band_w + margin
                y = H - margin - 22 * mm
                c.drawImage(str(lp), x, y, width=35 * mm, height=18 * mm, mask="auto", preserveAspectRatio=True)
                logo_drawn = True
        except Exception:
            logo_drawn = False

    # Nom de marque / société
    brand = _safe(company, "brand", "legal_name", "name", default="Société")
    legal_name = _safe(company, "legal_name", "brand", "name", default=brand)

    # Titre FACTURE (droite)
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 26)
    c.drawRightString(W - margin, top_y, "FACTURE")

    # Numéro (droite)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(W - margin, top_y - 10 * mm, f"N° {inv.get('number', '')}")

    # Ligne fine
    c.setStrokeColor(colors.HexColor("#E5E7EB"))
    c.setLineWidth(1)
    c.line(band_w + margin, top_y - 14 * mm, W - margin, top_y - 14 * mm)

    # Bloc société (gauche)
    left_x = band_w + margin
    y0 = top_y - (28 * mm if logo_drawn else 18 * mm)

    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left_x, y0, brand)

    c.setFont("Helvetica", 10)
    addr1 = _safe(company, "address1", default="")
    zip_ = _safe(company, "zip", default="")
    city = _safe(company, "city", default="")
    country = _safe(company, "country", default="")

    phone = _safe(company, "phone", default="")
    email = _safe(company, "email", default="")

    line_y = y0 - 6 * mm
    if legal_name and legal_name != brand:
        c.drawString(left_x, line_y, legal_name)
        line_y -= 5 * mm
    if addr1:
        c.drawString(left_x, line_y, addr1)
        line_y -= 5 * mm
    if zip_ or city:
        c.drawString(left_x, line_y, f"{zip_} {city}".strip())
        line_y -= 5 * mm
    if country:
        c.drawString(left_x, line_y, country)
        line_y -= 5 * mm
    if phone:
        c.drawString(left_x, line_y, phone)
        line_y -= 5 * mm
    if email:
        c.drawString(left_x, line_y, email)
        line_y -= 5 * mm

    # Identifiants
    siret = _safe(company, "siret", default="")
    tva = _safe(company, "tva", default="")
    if siret:
        c.setFillColor(MID_GREY)
        c.drawString(left_x, line_y, f"SIRET : {siret}")
        line_y -= 5 * mm
    if tva:
        c.setFillColor(MID_GREY)
        c.drawString(left_x, line_y, f"TVA : {tva}")
        line_y -= 5 * mm

    # Bloc infos facture (droite)
    issue_date = inv.get("issue_date")
    if isinstance(issue_date, date):
        issue_str = issue_date.strftime("%d/%m/%Y")
    else:
        issue_str = str(issue_date or "")

    due = inv.get("due", "")
    op = inv.get("operation_type", "")

    box_w = 80 * mm
    box_h = 34 * mm
    box_x = W - margin - box_w
    box_y = top_y - 55 * mm

    c.setFillColor(LIGHT_BG)
    c.roundRect(box_x, box_y, box_w, box_h, 6, stroke=0, fill=1)

    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(box_x + 8 * mm, box_y + box_h - 10 * mm, "Date de facturation")
    c.setFont("Helvetica", 10)
    c.drawRightString(box_x + box_w - 8 * mm, box_y + box_h - 10 * mm, issue_str)

    c.setFont("Helvetica-Bold", 10)
    c.drawString(box_x + 8 * mm, box_y + box_h - 18 * mm, "Échéance")
    c.setFont("Helvetica", 10)
    c.drawRightString(box_x + box_w - 8 * mm, box_y + box_h - 18 * mm, str(due))

    c.setFont("Helvetica-Bold", 10)
    c.drawString(box_x + 8 * mm, box_y + box_h - 26 * mm, "Type d’opération")
    c.setFont("Helvetica", 10)
    c.drawRightString(box_x + box_w - 8 * mm, box_y + box_h - 26 * mm, str(op))

    # --- Bloc client ---
    client_name = _safe(client, "name", "nom", default="Client")
    client_addr = _safe(client, "address1", "adresse", default="")
    client_zip = _safe(client, "zip_code", "zip", default="")
    client_city = _safe(client, "city", default="")
    client_siret = _safe(client, "siret", default="")

    block_y = box_y - 18 * mm

    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 12)
    c.drawString(left_x, block_y, "Facturé à")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(left_x, block_y - 7 * mm, client_name)

    c.setFont("Helvetica", 10)
    yy = block_y - 12 * mm
    if client_addr:
        c.drawString(left_x, yy, client_addr)
        yy -= 5 * mm
    if client_zip or client_city:
        c.drawString(left_x, yy, f"{client_zip} {client_city}".strip())
        yy -= 5 * mm
    if client_siret:
        c.setFillColor(MID_GREY)
        c.drawString(left_x, yy, f"SIRET : {client_siret}")
        yy -= 5 * mm

    # --- Table lignes ---
    desc = str(inv.get("description", "")).strip()
    qty = float(inv.get("qty", 1) or 1)
    unit = str(inv.get("unit", "u"))
    unit_price = float(inv.get("unit_price", 0.0) or 0.0)
    tax_rate = float(inv.get("tax_rate", 0.0) or 0.0)

    total_ht = float(inv.get("total_ht", qty * unit_price) or 0.0)
    total_tva = float(inv.get("total_tva", 0.0) or 0.0)
    total_ttc = float(inv.get("total_ttc", total_ht + total_tva) or 0.0)

    table_data = [
        ["Description", "Qté", "PU", "TVA", "Montant"],
        [desc, f"{qty:g} {unit}", _fmt_money(unit_price), f"{tax_rate:.2f} %".replace(".", ","), _fmt_money(total_ttc)],
    ]

    table = Table(table_data, colWidths=[86*mm, 18*mm, 26*mm, 16*mm, 28*mm])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("ALIGN", (0, 0), (0, -1), "LEFT"),
        ("FONTSIZE", (0, 1), (-1, -1), 10),
        ("BACKGROUND", (0, 1), (-1, 1), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))

    table_y = block_y - 58 * mm
    table.wrapOn(c, W - 2 * margin, 120 * mm)
    table.drawOn(c, left_x, table_y)

    # --- Totaux (droite) ---
    totals_w = 80 * mm
    totals_h = 30 * mm
    totals_x = W - margin - totals_w
    totals_y = table_y - 36 * mm

    c.setFillColor(LIGHT_BG)
    c.roundRect(totals_x, totals_y, totals_w, totals_h, 6, stroke=0, fill=1)

    c.setFillColor(ACCENT)
    c.setFont("Helvetica", 10)
    c.drawString(totals_x + 8 * mm, totals_y + totals_h - 10 * mm, "Total HT")
    c.drawRightString(totals_x + totals_w - 8 * mm, totals_y + totals_h - 10 * mm, _fmt_money(total_ht))

    c.setFont("Helvetica", 10)
    c.drawString(totals_x + 8 * mm, totals_y + totals_h - 18 * mm, "TVA")
    c.drawRightString(totals_x + totals_w - 8 * mm, totals_y + totals_h - 18 * mm, _fmt_money(total_tva))

    c.setFont("Helvetica-Bold", 11)
    c.drawString(totals_x + 8 * mm, totals_y + totals_h - 27 * mm, "Total TTC")
    c.drawRightString(totals_x + totals_w - 8 * mm, totals_y + totals_h - 27 * mm, _fmt_money(total_ttc))

    # --- Mention TVA ---
    vat_notice = _safe(company, "vat_notice", default="")
    if vat_notice:
        c.setFillColor(MID_GREY)
        c.setFont("Helvetica", 9)
        c.drawString(left_x, totals_y + 4 * mm, vat_notice)

    # --- Footer ---
    c.setStrokeColor(colors.HexColor("#E5E7EB"))
    c.setLineWidth(1)
    c.line(band_w + margin, 18 * mm, W - margin, 18 * mm)

    footer = f"{brand} — {addr1} {zip_} {city}".strip()
    c.setFillColor(MID_GREY)
    c.setFont("Helvetica", 8.5)
    c.drawString(left_x, 12 * mm, footer)

    if siret:
        c.drawRightString(W - margin, 12 * mm, f"SIRET : {siret}")

    c.showPage()
    c.save()
