from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, black, grey
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
import os


PURPLE = HexColor("#6A1B9A")
LIGHT_GREY = HexColor("#F5F5F5")


def _get(d, *keys, default=""):
    """Récupère une valeur avec plusieurs noms possibles (anti KeyError)."""
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def _money(v):
    try:
        return f"{float(v):.2f} €"
    except:
        return "0.00 €"


def draw_invoice_pdf(path, company, client, inv, logo_path=None):
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4

    # ===== Bande gauche =====
    c.setFillColor(PURPLE)
    c.rect(0, 0, 15 * mm, height, fill=1, stroke=0)

    # ===== Logo =====
    try:
        if logo_path and os.path.exists(str(logo_path)):
            c.drawImage(
                str(logo_path),
                22 * mm,
                height - 35 * mm,
                width=40 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
    except:
        # si logo invalide, on ignore sans casser la facture
        pass

    # ===== Titre =====
    number = _get(inv, "number", "numero", default="FACTURE-XXXX")
    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 20)
    c.drawRightString(width - 20 * mm, height - 30 * mm, "FACTURE")

    c.setFont("Helvetica", 10)
    c.drawRightString(width - 20 * mm, height - 38 * mm, f"N° {number}")

    # ===== Bloc société =====
    brand = _get(company, "brand", "nom", "name", default="SOCIÉTÉ")
    legal_name = _get(company, "legal_name", "raison_sociale", default=brand)
    address1 = _get(company, "address1", "adresse", "address", default="")
    zip_ = _get(company, "zip", "zip_code", "cp", default="")
    city = _get(company, "city", "ville", default="")
    country = _get(company, "country", "pays", default="France")
    phone = _get(company, "phone", "tel", "telephone", default="")
    email = _get(company, "email", "mail", default="")
    siret = _get(company, "siret", default="")
    vat_notice = _get(company, "vat_notice", "tva_notice", default="TVA non applicable, art. 293 B du CGI")

    y = height - 55 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(22 * mm, y, brand)

    c.setFont("Helvetica", 9)
    lines = [
        legal_name,
        address1,
        f"{zip_} {city}".strip(),
        country,
        f"Tél : {phone}" if phone else "",
        email,
        f"SIRET : {siret}" if siret else "",
    ]
    for l in lines:
        if not l:
            continue
        y -= 4 * mm
        c.drawString(22 * mm, y, l)

    # ===== Bloc client =====
    client_name = _get(client, "name", "nom", default="CLIENT")
    client_addr = _get(client, "address1", "adresse", "address", default="")
    client_zip = _get(client, "zip_code", "zip", "cp", default="")
    client_city = _get(client, "city", "ville", default="")
    client_siret = _get(client, "siret", default="")

    y -= 8 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(22 * mm, y, "Facturé à")

    c.setFont("Helvetica", 9)
    y -= 4 * mm
    c.drawString(22 * mm, y, client_name)
    if client_addr:
        y -= 4 * mm
        c.drawString(22 * mm, y, client_addr)
    if (client_zip or client_city):
        y -= 4 * mm
        c.drawString(22 * mm, y, f"{client_zip} {client_city}".strip())
    if client_siret:
        y -= 4 * mm
        c.drawString(22 * mm, y, f"SIRET : {client_siret}")

    # ===== Bloc infos facture =====
    issue_date = _get(inv, "issue_date", "date", default=None)
    try:
        issue_str = issue_date.strftime("%d/%m/%Y")
    except:
        issue_str = ""

    due = _get(inv, "due", "echeance", default="")
    op = _get(inv, "operation_type", "type_operation", default="")

    box_x = width - 95 * mm
    box_y = height - 80 * mm
    c.setFillColor(LIGHT_GREY)
    c.rect(box_x, box_y, 75 * mm, 28 * mm, fill=1, stroke=0)

    c.setFillColor(black)
    c.setFont("Helvetica", 9)
    c.drawString(box_x + 5 * mm, box_y + 18 * mm, f"Date : {issue_str}")
    c.drawString(box_x + 5 * mm, box_y + 12 * mm, f"Échéance : {due}")
    c.drawString(box_x + 5 * mm, box_y + 6 * mm, f"Opération : {op}")

    # ===== Ligne prestation =====
    desc = _get(inv, "description", "libelle", default="")
    qty = _get(inv, "qty", "quantite", default=1)
    unit_price = _get(inv, "unit_price", "prix", default=0)
    total_ttc = _get(inv, "total_ttc", "ttc", default=0)

    table_y = box_y - 20 * mm
    c.setFont("Helvetica-Bold", 9)
    c.drawString(22 * mm, table_y, "Description")
    c.drawRightString(width - 70 * mm, table_y, "Qté")
    c.drawRightString(width - 45 * mm, table_y, "PU")
    c.drawRightString(width - 20 * mm, table_y, "Montant")
    c.line(22 * mm, table_y - 2 * mm, width - 20 * mm, table_y - 2 * mm)

    table_y -= 8 * mm
    c.setFont("Helvetica", 9)
    c.drawString(22 * mm, table_y, desc)
    c.drawRightString(width - 70 * mm, table_y, str(qty))
    c.drawRightString(width - 45 * mm, table_y, _money(unit_price))
    c.drawRightString(width - 20 * mm, table_y, _money(total_ttc))

    # ===== Total TTC =====
    totals_y = table_y - 20 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(width - 45 * mm, totals_y, "Total TTC")
    c.drawRightString(width - 20 * mm, totals_y, _money(total_ttc))

    # ===== TVA notice =====
    c.setFont("Helvetica", 8)
    c.setFillColor(grey)
    c.drawString(22 * mm, totals_y - 10 * mm, vat_notice)

    # ===== Pied de page =====
    c.setFont("Helvetica", 7)
    footer = f"{brand} — {address1} {zip_} {city} — SIRET {siret}".strip()
    c.drawCentredString(width / 2, 10 * mm, footer)

    c.showPage()
    c.save()
