from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import HexColor, black, grey
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
import os

PURPLE = HexColor("#6A1B9A")
LIGHT_GREY = HexColor("#F5F5F5")


def safe(d, *keys, default=""):
    """Retourne la première clé trouvée (évite KeyError)."""
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k]:
            return str(d[k])
    return default


def draw_invoice_pdf(path, company, client, invoice, logo_path=None):
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4

    # Bande verticale gauche
    c.setFillColor(PURPLE)
    c.rect(0, 0, 18 * mm, h, stroke=0, fill=1)

    # Logo
    if logo_path and os.path.exists(logo_path):
        try:
            c.drawImage(
                logo_path,
                25 * mm,
                h - 40 * mm,
                width=40 * mm,
                preserveAspectRatio=True,
                mask="auto",
            )
        except Exception:
            pass

    # Titre
    c.setFont("Helvetica-Bold", 16)
    c.setFillColor(black)
    c.drawRightString(w - 20 * mm, h - 25 * mm, "FACTURE")

    c.setFont("Helvetica", 9)
    c.drawRightString(
        w - 20 * mm,
        h - 32 * mm,
        f"N° {invoice.get('number', '')}",
    )

    # Bloc entreprise
    y = h - 60 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(25 * mm, y, safe(company, "brand", "legal_name"))

    c.setFont("Helvetica", 9)
    c.drawString(25 * mm, y - 5 * mm, safe(company, "address1"))
    c.drawString(
        25 * mm,
        y - 10 * mm,
        f"{safe(company,'zip')} {safe(company,'city')}",
    )
    c.drawString(25 * mm, y - 15 * mm, safe(company, "country"))
    c.drawString(25 * mm, y - 20 * mm, f"Tél : {safe(company,'phone')}")
    c.drawString(25 * mm, y - 25 * mm, safe(company, "email"))
    c.drawString(25 * mm, y - 30 * mm, f"SIRET : {safe(company,'siret')}")

    # Bloc client
    y2 = y - 45 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawString(25 * mm, y2, "Facturé à :")

    c.setFont("Helvetica", 9)
    c.drawString(25 * mm, y2 - 5 * mm, safe(client, "name", "nom"))
    c.drawString(25 * mm, y2 - 10 * mm, safe(client, "address1", "address"))
    c.drawString(
        25 * mm,
        y2 - 15 * mm,
        f"{safe(client,'zip','zip_code','code postal')} {safe(client,'city')}",
    )

    if safe(client, "siret"):
        c.drawString(25 * mm, y2 - 20 * mm, f"SIRET : {safe(client,'siret')}")

    # Infos facture
    info_y = y2
    c.drawRightString(
        w - 20 * mm, info_y, f"Date : {invoice.get('issue_date')}"
    )
    c.drawRightString(
        w - 20 * mm,
        info_y - 5 * mm,
        f"Échéance : {invoice.get('due')}",
    )
    c.drawRightString(
        w - 20 * mm,
        info_y - 10 * mm,
        invoice.get("operation_type", ""),
    )

    # Tableau
    table_y = y2 - 40 * mm
    c.setFillColor(LIGHT_GREY)
    c.rect(25 * mm, table_y, w - 45 * mm, 10 * mm, fill=1, stroke=0)

    c.setFillColor(black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(27 * mm, table_y + 3 * mm, "Description")
    c.drawRightString(w - 95 * mm, table_y + 3 * mm, "Qté")
    c.drawRightString(w - 65 * mm, table_y + 3 * mm, "PU")
    c.drawRightString(w - 40 * mm, table_y + 3 * mm, "Montant")

    # Ligne
    row_y = table_y - 8 * mm
    c.setFont("Helvetica", 9)
    c.drawString(27 * mm, row_y, invoice.get("description", ""))
    c.drawRightString(w - 95 * mm, row_y, str(invoice.get("qty", 1)))
    c.drawRightString(
        w - 65 * mm,
        row_y,
        f"{invoice.get('unit_price',0):,.2f} €".replace(",", " "),
    )
    c.drawRightString(
        w - 40 * mm,
        row_y,
        f"{invoice.get('total_ttc',0):,.2f} €".replace(",", " "),
    )

    # Totaux
    total_y = row_y - 20 * mm
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(
        w - 40 * mm,
        total_y,
        f"TOTAL TTC : {invoice.get('total_ttc',0):,.2f} €".replace(",", " "),
    )

    # TVA notice
    if company.get("vat_notice"):
        c.setFont("Helvetica", 8)
        c.drawString(25 * mm, 25 * mm, company["vat_notice"])

    c.showPage()
    c.save()
