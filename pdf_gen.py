from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.colors import black, HexColor
from pathlib import Path
from datetime import date


def draw_invoice_pdf(pdf_path, entreprise, client, invoice, logo_path: Path | None = None):
    c = canvas.Canvas(str(pdf_path), pagesize=A4)
    largeur, hauteur = A4

    margin_left = 20 * mm
    margin_top = hauteur - 20 * mm

    # =====================
    # LOGO
    # =====================
    if logo_path and logo_path.exists():
        c.drawImage(
            str(logo_path),
            largeur - 60 * mm,
            hauteur - 40 * mm,
            width=40 * mm,
            preserveAspectRatio=True,
            mask='auto'
        )

    # =====================
    # ENTREPRISE
    # =====================
    y = margin_top
    c.setFont("Helvetica-Bold", 12)
    c.drawString(margin_left, y, entreprise.get("name", ""))

    c.setFont("Helvetica", 10)
    y -= 5 * mm
    c.drawString(margin_left, y, entreprise.get("address", ""))

    y -= 5 * mm
    c.drawString(
        margin_left,
        y,
        f"{entreprise.get('zip', '')} {entreprise.get('city', '')}"
    )

    y -= 5 * mm
    c.drawString(margin_left, y, f"SIRET {entreprise.get('siret', '')}")

    if entreprise.get("tva"):
        y -= 5 * mm
        c.drawString(margin_left, y, f"TVA {entreprise.get('tva')}")

    # =====================
    # TITRE FACTURE
    # =====================
    c.setFont("Helvetica-Bold", 18)
    c.drawCentredString(largeur / 2, hauteur - 60 * mm, "FACTURE")

    c.setFont("Helvetica", 10)
    c.drawCentredString(
        largeur / 2,
        hauteur - 68 * mm,
        f"{invoice['number']}"
    )

    # =====================
    # INFOS FACTURE
    # =====================
    info_y = hauteur - 85 * mm
    c.setFont("Helvetica", 10)
    c.drawRightString(largeur - margin_left, info_y, f"Date de facturation : {invoice['issue_date']}")
    info_y -= 5 * mm
    c.drawRightString(largeur - margin_left, info_y, f"Échéance : {invoice['due']}")
    info_y -= 5 * mm
    c.drawRightString(largeur - margin_left, info_y, f"Type d’opération : {invoice['operation_type']}")

    # =====================
    # CLIENT
    # =====================
    client_y = hauteur - 105 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawString(margin_left, client_y, client.get("name", ""))

    c.setFont("Helvetica", 10)
    client_y -= 5 * mm
    c.drawString(margin_left, client_y, client.get("address1", ""))

    client_y -= 5 * mm
    c.drawString(
        margin_left,
        client_y,
        f"{client.get('zip_code', '')} {client.get('city', '')}"
    )

    if client.get("siret"):
        client_y -= 5 * mm
        c.drawString(margin_left, client_y, f"SIRET {client.get('siret')}")

    # =====================
    # TABLE HEADER
    # =====================
    table_y = hauteur - 135 * mm
    c.setFont("Helvetica-Bold", 10)

    c.drawString(margin_left, table_y, "Description")
    c.drawRightString(largeur - 90 * mm, table_y, "Qté")
    c.drawRightString(largeur - 70 * mm, table_y, "Unité")
    c.drawRightString(largeur - 40 * mm, table_y, "Prix")
    c.drawRightString(largeur - margin_left, table_y, "Total")

    c.line(margin_left, table_y - 2, largeur - margin_left, table_y - 2)

    # =====================
    # LIGNE FACTURE
    # =====================
    line_y = table_y - 10 * mm
    c.setFont("Helvetica", 10)

    c.drawString(margin_left, line_y, invoice["description"])
    c.drawRightString(largeur - 90 * mm, line_y, str(invoice["qty"]))
    c.drawRightString(largeur - 70 * mm, line_y, invoice["unit"])
    c.drawRightString(largeur - 40 * mm, line_y, f"{invoice['unit_price']:.2f} €")
    c.drawRightString(largeur - margin_left, line_y, f"{invoice['total_ht']:.2f} €")

    # =====================
    # TOTALS
    # =====================
    total_y = line_y - 20 * mm
    c.setFont("Helvetica-Bold", 11)

    c.drawRightString(largeur - 40 * mm, total_y, "Total TTC :")
    c.drawRightString(largeur - margin_left, total_y, f"{invoice['total_ttc']:.2f} €")

    total_y -= 6 * mm
    c.setFont("Helvetica", 9)
    c.drawRightString(
        largeur - margin_left,
        total_y,
        "TVA non applicable, art. 293B du CGI"
    )

    # =====================
    # FOOTER
    # =====================
    c.setFont("Helvetica", 8)
    c.setFillColor(HexColor("#555555"))
    c.drawCentredString(
        largeur / 2,
        15 * mm,
        "Merci pour votre confiance"
    )

    c.save()
