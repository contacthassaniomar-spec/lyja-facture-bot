import os
import json
from pathlib import Path
from datetime import date
from decimal import Decimal

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputFile
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    ConversationHandler, ContextTypes, filters
)

import db
from pdf_gen import draw_invoice_pdf

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"


def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


CFG = load_config()


def get_logo_path() -> Path:
    p = CFG.get("pdf", {}).get("logo_path", "assets/logo.png")
    return (BASE_DIR / p).resolve()


def admin_allowed(user_id: int) -> bool:
    if not CFG.get("bot", {}).get("admin_only", False):
        return True
    admin_id = os.getenv("OWNER_TELEGRAM_ID", "")
    return admin_id.isdigit() and int(admin_id) == int(user_id)


def money_to_float(text: str) -> float:
    t = (text or "").strip().replace("€", "").replace(" ", "").replace(",", ".")
    return float(Decimal(t))


def safe_get(d: dict, *keys, default=""):
    if not isinstance(d, dict):
        return default
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    return default


def normalize_company_for_pdf(company: dict) -> dict:
    brand = safe_get(company, "brand", "enseigne", default="")
    legal = safe_get(company, "legal_name", "raison_sociale", "nom", default=brand)
    address1 = safe_get(company, "address1", "adresse", "address", default="")
    zip_ = safe_get(company, "zip", "zip_code", "code_postal", "code postal", default="")
    city = safe_get(company, "city", "ville", default="")
    country = safe_get(company, "country", "pays", default="France")
    phone = safe_get(company, "phone", "tel", "telephone", default="")
    email = safe_get(company, "email", default="")
    siret = safe_get(company, "siret", default="")
    tva = safe_get(company, "tva", "vat", "vat_number", default="")
    vat_notice = safe_get(company, "vat_notice", "mention_tva", "tva_notice", default="TVA non applicable, art. 293 B du CGI")

    return {
        "brand": brand,
        "legal_name": legal,
        "address1": address1,
        "zip": zip_,
        "city": city,
        "country": country,
        "phone": phone,
        "email": email,
        "siret": siret,
        "tva": tva,
        "vat_notice": vat_notice,

        # variantes
        "nom": legal,
        "enseigne": brand,
        "adresse": address1,
        "zip_code": zip_,
        "code_postal": zip_,
        "code postal": zip_,
        "ville": city,
        "pays": country,
        "telephone": phone,
    }


def normalize_client_for_pdf(client: dict) -> dict:
    name = safe_get(client, "name", "nom", default="Client")
    address1 = safe_get(client, "address1", "adresse", "address", default="")
    zip_ = safe_get(client, "zip", "zip_code", "code_postal", "code postal", default="")
    city = safe_get(client, "city", "ville", default="")
    country = safe_get(client, "country", "pays", default="France")
    siret = safe_get(client, "siret", default="")
    tva = safe_get(client, "tva", "vat", default="")

    return {
        "id": client.get("id"),
        "name": name,
        "address1": address1,
        "zip": zip_,
        "city": city,
        "country": country,
        "siret": siret,
        "tva": tva,

        "nom": name,
        "adresse": address1,
        "zip_code": zip_,
        "code_postal": zip_,
        "code postal": zip_,
        "ville": city,
        "pays": country,
    }


# ---------------- States ----------------
(
    MENU,
    CLIENTS_MENU,
    CLIENT_CHOOSE_FOR_INV,
    CLIENT_SEARCH_FOR_INV,
    CLIENT_ADD_NAME,
    CLIENT_ADD_ADDR,
    CLIENT_ADD_CITYZIP,
    CLIENT_ADD_SIRET,
    CLIENT_ADD_TVA,
    INV_DESC,
    INV_PRICE,
    INV_CONFIRM,
    INV_FORCE_NUMBER,
    IMPORT_CLIENTS,

    INVOICES_CLIENT_PICK,
    INVOICES_LIST
) = range(16)


# ---------------- Keyboards ----------------
def main_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧾 Créer une facture", callback_data="MENU::NEW_INV")],
        [InlineKeyboardButton("👥 Clients", callback_data="MENU::CLIENTS")],
        [InlineKeyboardButton("🗂️ Mes factures", callback_data="MENU::INVOICES")],
    ])


def clients_menu_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("👥 Voir la liste", callback_data="CLIENTS::LIST")],
        [InlineKeyboardButton("➕ Ajouter un client", callback_data="CLIENTS::ADD")],
        [InlineKeyboardButton("📥 Import clients", callback_data="CLIENTS::IMPORT")],
        [InlineKeyboardButton("⬅️ Retour menu", callback_data="BACK::MENU")],
    ])


def presets_keyboard():
    presets = CFG.get("invoice", {}).get("description_presets", [])
    rows = [[InlineKeyboardButton(p, callback_data=f"PRESET::{p}")] for p in presets]
    rows.append([InlineKeyboardButton("✍️ Saisie manuelle", callback_data="PRESET::MANUAL")])
    rows.append([InlineKeyboardButton("⬅️ Retour menu", callback_data="BACK::MENU")])
    return InlineKeyboardMarkup(rows)


def client_to_btn(c, prefix="CLIENT::"):
    label = c.get("name") or c.get("nom") or "Client"
    if c.get("city"):
        label += f" — {c['city']}"
    return InlineKeyboardButton(label[:60], callback_data=f"{prefix}{c['id']}")


def invoice_to_btn(inv: dict):
    # ex: FACTURE-2026-002 • 26/02/2026 • 1 700,00 €
    num = inv.get("number", "FACTURE")
    issue = (inv.get("issue_date") or "")[:10]
    total = float(inv.get("total_ttc") or 0.0)
    label = f"{num} • {issue} • {total:,.2f} €".replace(",", " ").replace(".", ",")
    return InlineKeyboardButton(label[:60], callback_data=f"INVFILE::{inv['id']}")


# ---------------- Base navigation ----------------
async def go_menu(update: Update, text="🏠 Menu :", edit=False):
    if edit and update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=main_menu_keyboard())
    else:
        if update.effective_message:
            await update.effective_message.reply_text(text, reply_markup=main_menu_keyboard())
    return MENU


# ---------------- Handlers ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_allowed(update.effective_user.id):
        await update.message.reply_text("Accès refusé.")
        return ConversationHandler.END

    db.init_db()
    context.user_data.clear()
    await update.message.reply_text("✅ Bot Facture en ligne.\nChoisis une action :", reply_markup=main_menu_keyboard())
    return MENU


async def back_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await go_menu(update, edit=True)


# ---------- MENU ----------
async def menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    action = q.data

    if action == "MENU::CLIENTS":
        await q.edit_message_text("👥 Clients — choisis une action :", reply_markup=clients_menu_keyboard())
        return CLIENTS_MENU

    if action == "MENU::NEW_INV":
        context.user_data.clear()
        await q.edit_message_text(
            "🧾 Nouvelle facture — choisis le client :",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔎 Rechercher un client", callback_data="INVCLIENT::SEARCH")],
                [InlineKeyboardButton("📋 Choisir dans la liste", callback_data="INVCLIENT::LIST")],
                [InlineKeyboardButton("➕ Ajouter un client", callback_data="INVCLIENT::ADD")],
                [InlineKeyboardButton("⬅️ Retour menu", callback_data="BACK::MENU")],
            ])
        )
        return CLIENT_CHOOSE_FOR_INV

    if action == "MENU::INVOICES":
        # Mes factures -> choisir client
        clients = db.list_clients(200)
        if not clients:
            await q.edit_message_text("Aucun client enregistré.", reply_markup=main_menu_keyboard())
            return MENU

        kb = [[client_to_btn(c, prefix="INVCL::")] for c in clients[:40]]
        kb.append([InlineKeyboardButton("🔎 Rechercher", callback_data="INVCLMODE::SEARCH")])
        kb.append([InlineKeyboardButton("⬅️ Retour menu", callback_data="BACK::MENU")])
        await q.edit_message_text("🗂️ Mes factures — choisis un client :", reply_markup=InlineKeyboardMarkup(kb))
        return INVOICES_CLIENT_PICK

    return await go_menu(update, edit=True)


# ---------- CLIENTS MENU ----------
async def clients_menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "CLIENTS::LIST":
        clients = db.list_clients(200)
        if not clients:
            await q.edit_message_text("Aucun client enregistré.", reply_markup=clients_menu_keyboard())
            return CLIENTS_MENU
        kb = [[client_to_btn(c, prefix="CLVIEW::")] for c in clients[:40]]
        kb.append([InlineKeyboardButton("⬅️ Retour clients", callback_data="BACK::CLIENTS")])
        await q.edit_message_text("📋 Liste clients :", reply_markup=InlineKeyboardMarkup(kb))
        return CLIENTS_MENU

    if q.data == "CLIENTS::ADD":
        await q.edit_message_text("➕ Nouveau client\n\nNom du client ? (ex: HOCIPHONE)")
        return CLIENT_ADD_NAME

    if q.data == "CLIENTS::IMPORT":
        await q.edit_message_text(
            "📥 Import clients\n\n"
            "Colle tes clients (1 par ligne) au format :\n"
            "NOM | ADRESSE | CP | VILLE | SIRET | TVA\n\n"
            "Si TVA n’existe pas, mets '-'.\n\n"
            "Exemple :\n"
            "HOCIPHONE | 160 chemin... | 13015 | Marseille | 4097... | -\n\n"
            "➡️ Colle maintenant ton bloc."
        )
        return IMPORT_CLIENTS

    if q.data == "BACK::MENU":
        return await go_menu(update, edit=True)

    return CLIENTS_MENU


async def back_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    await update.callback_query.edit_message_text("👥 Clients — choisis une action :", reply_markup=clients_menu_keyboard())
    return CLIENTS_MENU


# ---------- CHOIX CLIENT POUR FACTURE ----------
async def inv_client_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "INVCLIENT::SEARCH":
        await q.edit_message_text("🔎 Recherche client\nTape le nom / email / tel :")
        return CLIENT_SEARCH_FOR_INV

    if q.data == "INVCLIENT::LIST":
        clients = db.list_clients(200)
        if not clients:
            await q.edit_message_text("Aucun client enregistré.", reply_markup=main_menu_keyboard())
            return MENU
        kb = [[client_to_btn(c, prefix="INVCLIENTSEL::")] for c in clients[:40]]
        kb.append([InlineKeyboardButton("⬅️ Retour menu", callback_data="BACK::MENU")])
        await q.edit_message_text("📋 Choisis un client :", reply_markup=InlineKeyboardMarkup(kb))
        return CLIENT_CHOOSE_FOR_INV

    if q.data == "INVCLIENT::ADD":
        await q.edit_message_text("➕ Nouveau client\nNom du client ?")
        return CLIENT_ADD_NAME

    if q.data == "BACK::MENU":
        return await go_menu(update, edit=True)

    return CLIENT_CHOOSE_FOR_INV


async def client_search_for_inv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    results = db.search_clients(query, 20)
    if not results:
        await update.message.reply_text("Aucun résultat. Réessaie.")
        return CLIENT_SEARCH_FOR_INV

    kb = [[client_to_btn(c, prefix="INVCLIENTSEL::")] for c in results]
    kb.append([InlineKeyboardButton("⬅️ Retour menu", callback_data="BACK::MENU")])
    await update.message.reply_text("Résultats :", reply_markup=InlineKeyboardMarkup(kb))
    return CLIENT_CHOOSE_FOR_INV


async def client_select_for_inv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.split("::")[1])
    client = db.get_client(cid)
    context.user_data["client_id"] = cid
    context.user_data["client"] = client

    await q.edit_message_text("🧾 Facture — choisis une description :", reply_markup=presets_keyboard())
    return INV_DESC


# ---------- AJOUT CLIENT (utilisé par Clients et par Facture) ----------
async def add_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("Nom vide. Réessaie.")
        return CLIENT_ADD_NAME
    context.user_data["new_client"] = {"name": name}
    await update.message.reply_text("Adresse ligne 1 ?")
    return CLIENT_ADD_ADDR


async def add_client_addr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_client"]["address1"] = (update.message.text or "").strip()
    await update.message.reply_text("Code postal + Ville ? (ex: 13015 Marseille)")
    return CLIENT_ADD_CITYZIP


async def add_client_cityzip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    parts = txt.split()
    context.user_data["new_client"]["zip"] = parts[0] if parts else ""
    context.user_data["new_client"]["city"] = " ".join(parts[1:]) if len(parts) > 1 else ""
    await update.message.reply_text("SIRET du client ? (ou '-' si rien)")
    return CLIENT_ADD_SIRET


async def add_client_siret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    siret = (update.message.text or "").strip()
    if siret == "-":
        siret = ""
    context.user_data["new_client"]["siret"] = siret
    await update.message.reply_text("TVA du client ? (ou '-' si rien)")
    return CLIENT_ADD_TVA


async def add_client_tva(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tva = (update.message.text or "").strip()
    if tva == "-":
        tva = ""

    nc = context.user_data["new_client"]
    cid = db.add_client(
        name=nc["name"],
        address1=nc.get("address1", ""),
        zip_code=nc.get("zip", ""),
        city=nc.get("city", ""),
        country="France",
        siret=nc.get("siret", ""),
        tva=tva
    )
    client = db.get_client(cid)
    db.client_folder(client)

    # IMPORTANT : si on venait du flux “Créer une facture”, on continue direct.
    context.user_data["client_id"] = cid
    context.user_data["client"] = client

    await update.message.reply_text(f"✅ Client ajouté: {client.get('name')}\n\n🧾 Maintenant choisis une description :", reply_markup=presets_keyboard())
    return INV_DESC


# ---------- DESCRIPTION ----------
async def desc_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, val = q.data.split("::", 1)

    if val == "MANUAL":
        await q.edit_message_text("Tape la description (ex: Prestation de services)")
        return INV_DESC

    context.user_data["description"] = val
    await q.edit_message_text("💶 Montant à facturer (TTC – TVA non applicable)")
    return INV_PRICE


async def desc_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = (update.message.text or "").strip()
    if not desc:
        await update.message.reply_text("Description vide. Réessaie.")
        return INV_DESC
    context.user_data["description"] = desc
    await update.message.reply_text("💶 Montant à facturer (TTC – TVA non applicable)")
    return INV_PRICE


def recap_message(context) -> str:
    client = context.user_data["client"]
    price = context.user_data["unit_price"]
    number = context.user_data["number"]
    desc = context.user_data["description"]

    msg = (
        f"📌 Récapitulatif\n"
        f"• Client : {client.get('name')}\n"
        f"• Description : {desc}\n"
        f"• Montant TTC : {price:.2f} € (TVA non applicable)\n"
        f"• Numéro : {number}\n\n"
        f"✅ Confirmer ?"
    ).replace(".", ",")
    return msg


async def price_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        price = money_to_float(update.message.text)
    except Exception:
        await update.message.reply_text("Montant invalide. Exemple: 1700 ou 1700,00")
        return INV_PRICE

    context.user_data["unit_price"] = price
    context.user_data["qty"] = float(CFG.get("invoice", {}).get("qty_default", 1))
    context.user_data["unit"] = CFG.get("invoice", {}).get("unit_default", "u")
    context.user_data["tax_rate"] = 0.0

    prefix = CFG.get("invoice", {}).get("number_prefix", "FACTURE")
    use_year = bool(CFG.get("invoice", {}).get("use_year", True))
    number = db.next_invoice_number(prefix, date.today(), use_year=use_year)
    context.user_data["number"] = number

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Générer PDF", callback_data="INV::CONFIRM")],
        [InlineKeyboardButton("✏️ Modifier numéro", callback_data="INV::FORCE_NUMBER")],
        [InlineKeyboardButton("⬅️ Retour menu", callback_data="BACK::MENU")],
    ])

    await update.message.reply_text(recap_message(context), reply_markup=kb)
    return INV_CONFIRM


async def inv_confirm_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "INV::FORCE_NUMBER":
        await q.edit_message_text(
            "Tape le numéro:\n"
            "- soit juste le chiffre (ex: 31)\n"
            "- soit le format complet (ex: FACTURE-2026-031)\n"
        )
        return INV_FORCE_NUMBER

    if q.data != "INV::CONFIRM":
        return INV_CONFIRM

    client = context.user_data["client"]
    company = CFG.get("company", {})

    number = context.user_data["number"]
    issue = date.today()
    due = CFG.get("invoice", {}).get("due_default", "À la réception de la facture")
    op = CFG.get("invoice", {}).get("operation_type_default", "Prestation de services")
    desc = context.user_data["description"]
    qty = context.user_data["qty"]
    unit = context.user_data["unit"]
    unit_price = context.user_data["unit_price"]
    tax_rate = context.user_data["tax_rate"]

    total_ttc = float(qty) * float(unit_price)
    total_ht = total_ttc
    total_tva = 0.0

    folder = db.client_folder(client) / str(issue.year)
    folder.mkdir(parents=True, exist_ok=True)
    pdf_path = folder / f"{number}.pdf"

    invoice_doc = {
        "title": f"{CFG.get('invoice', {}).get('number_prefix', 'FACTURE')} - {number}",
        "number": number,
        "issue_date": issue,
        "due": due,
        "operation_type": op,
        "description": desc,
        "qty": qty,
        "unit": unit,
        "unit_price": unit_price,
        "tax_rate": tax_rate,
        "total_ht": total_ht,
        "total_tva": total_tva,
        "total_ttc": total_ttc,
    }

    logo = get_logo_path()
    company_pdf = normalize_company_for_pdf(company)
    client_pdf = normalize_client_for_pdf(client)

    draw_invoice_pdf(pdf_path, company_pdf, client_pdf, invoice_doc, str(logo))

    # Vérif taille (évite "52 octets")
    try:
        size = pdf_path.stat().st_size
    except FileNotFoundError:
        size = 0

    if size < 800:
        await q.edit_message_text(
            f"❌ PDF invalide (taille: {size} octets).\n"
            "➡️ Vérifie : reportlab dans requirements.txt + logo_path."
        )
        return await go_menu(update)

    db.save_invoice(
        client_id=client["id"],
        number=number,
        issue_date=issue,
        due=due,
        operation_type=op,
        description=desc,
        qty=qty,
        unit=unit,
        unit_price=unit_price,
        tax_rate=tax_rate,
        total_ht=total_ht,
        total_tva=total_tva,
        total_ttc=total_ttc,
        pdf_path=str(pdf_path)
    )

    await q.edit_message_text("✅ Facture générée. Envoi du PDF…")
    with open(pdf_path, "rb") as f:
        await q.message.reply_document(document=InputFile(f, filename=f"{number}.pdf"))

    return await go_menu(update)


async def force_number(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    prefix = CFG.get("invoice", {}).get("number_prefix", "FACTURE")
    year = date.today().year

    if txt.upper().startswith(prefix.upper()):
        number = txt
    else:
        try:
            n = int(txt)
            number = f"{prefix}-{year}-{n:03d}"
        except Exception:
            await update.message.reply_text("Numéro invalide. Exemple: 31 ou FACTURE-2026-031")
            return INV_FORCE_NUMBER

    context.user_data["number"] = number

    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Générer PDF", callback_data="INV::CONFIRM")],
        [InlineKeyboardButton("✏️ Modifier numéro", callback_data="INV::FORCE_NUMBER")],
        [InlineKeyboardButton("⬅️ Retour menu", callback_data="BACK::MENU")],
    ])
    await update.message.reply_text(recap_message(context), reply_markup=kb)
    return INV_CONFIRM


# ---------- IMPORT ----------
async def import_clients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    lines = [l.strip() for l in txt.splitlines() if l.strip()]
    ok, bad = 0, 0

    for line in lines:
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            bad += 1
            continue

        name = parts[0]
        address1 = parts[1]
        zip_code = parts[2]
        city = parts[3]
        siret = parts[4] if len(parts) > 4 else ""
        tva = parts[5] if len(parts) > 5 else ""

        if siret == "-":
            siret = ""
        if tva == "-":
            tva = ""

        cid = db.add_client(
            name=name,
            address1=address1,
            zip_code=zip_code,
            city=city,
            country="France",
            siret=siret,
            tva=tva
        )
        client = db.get_client(cid)
        db.client_folder(client)
        ok += 1

    await update.message.reply_text(f"✅ Import terminé\nAjoutés: {ok}\nIgnorés: {bad}")
    return await go_menu(update)


# ---------- MES FACTURES ----------
async def invoices_client_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "INVCLMODE::SEARCH":
        await q.edit_message_text("🔎 Recherche client (Mes factures)\nTape le nom / email / tel :")
        return INVOICES_CLIENT_PICK

    if q.data.startswith("INVCL::"):
        client_id = int(q.data.split("::")[1])
        client = db.get_client(client_id)
        context.user_data["inv_client_id"] = client_id
        context.user_data["inv_client"] = client

        invs = db.list_invoices_for_client(client_id, limit=50)
        if not invs:
            await q.edit_message_text(
                f"🗂️ {client.get('name')} — aucune facture.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Retour", callback_data="MENU::INVOICES")]])
            )
            return INVOICES_CLIENT_PICK

        kb = [[invoice_to_btn(inv)] for inv in invs[:40]]
        kb.append([InlineKeyboardButton("⬅️ Retour clients", callback_data="MENU::INVOICES")])
        await q.edit_message_text(f"🗂️ Factures — {client.get('name')} :", reply_markup=InlineKeyboardMarkup(kb))
        return INVOICES_LIST

    if q.data == "BACK::MENU":
        return await go_menu(update, edit=True)

    # si l’utilisateur envoie du texte ici (recherche) on ignore dans ce handler
    return INVOICES_CLIENT_PICK


async def invoices_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    results = db.search_clients(query, 20)
    if not results:
        await update.message.reply_text("Aucun résultat. Réessaie.")
        return INVOICES_CLIENT_PICK

    kb = [[client_to_btn(c, prefix="INVCL::")] for c in results]
    kb.append([InlineKeyboardButton("⬅️ Retour menu", callback_data="BACK::MENU")])
    await update.message.reply_text("Résultats :", reply_markup=InlineKeyboardMarkup(kb))
    return INVOICES_CLIENT_PICK


async def invoice_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "MENU::INVOICES":
        # revenir à la liste clients
        return await menu_click(update, context)

    if not q.data.startswith("INVFILE::"):
        return INVOICES_LIST

    inv_id = int(q.data.split("::")[1])
    inv = db.get_invoice(inv_id)
    if not inv:
        await q.edit_message_text("Facture introuvable.")
        return await go_menu(update)

    pdf_path = inv.get("pdf_path", "")
    if not pdf_path or not Path(pdf_path).exists():
        await q.edit_message_text("PDF introuvable (chemin manquant).")
        return await go_menu(update)

    await q.message.reply_document(document=InputFile(str(pdf_path)), filename=f"{inv.get('number','FACTURE')}.pdf")
    return INVOICES_LIST


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Commande inconnue. Tape /start")


def main():
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BOT_TOKEN manquant (Railway Variables).")

    db.init_db()

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [
                CallbackQueryHandler(menu_click, pattern=r"^MENU::"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],

            CLIENTS_MENU: [
                CallbackQueryHandler(clients_menu_click, pattern=r"^(CLIENTS::|BACK::MENU$)"),
                CallbackQueryHandler(back_clients, pattern=r"^BACK::CLIENTS$"),
            ],

            CLIENT_CHOOSE_FOR_INV: [
                CallbackQueryHandler(inv_client_mode, pattern=r"^(INVCLIENT::|BACK::MENU$)"),
                CallbackQueryHandler(client_select_for_inv, pattern=r"^INVCLIENTSEL::"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
            CLIENT_SEARCH_FOR_INV: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, client_search_for_inv)
            ],

            CLIENT_ADD_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_name)],
            CLIENT_ADD_ADDR: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_addr)],
            CLIENT_ADD_CITYZIP: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_cityzip)],
            CLIENT_ADD_SIRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_siret)],
            CLIENT_ADD_TVA: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_tva)],

            INV_DESC: [
                CallbackQueryHandler(desc_pick, pattern=r"^PRESET::"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, desc_manual),
            ],
            INV_PRICE: [MessageHandler(filters.TEXT & ~filters.COMMAND, price_step)],
            INV_CONFIRM: [
                CallbackQueryHandler(inv_confirm_click, pattern=r"^INV::"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
            INV_FORCE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, force_number)],

            IMPORT_CLIENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, import_clients)],

            INVOICES_CLIENT_PICK: [
                CallbackQueryHandler(invoices_client_pick, pattern=r"^(INVCL::|INVCLMODE::|BACK::MENU$)"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, invoices_search_text),
                CallbackQueryHandler(menu_click, pattern=r"^MENU::INVOICES$"),
            ],
            INVOICES_LIST: [
                CallbackQueryHandler(invoice_open, pattern=r"^(INVFILE::|MENU::INVOICES$)"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True
    )

    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    # ⚠️ Si tu vois "telegram.error.Conflict", c'est 2 instances du bot en même temps.
    app.run_polling()


if __name__ == "__main__":
    main()
