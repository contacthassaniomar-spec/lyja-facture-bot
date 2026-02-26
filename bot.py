import os
import json
from pathlib import Path
from datetime import date
from decimal import Decimal

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputFile,
    ReplyKeyboardMarkup,
    KeyboardButton,
)
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

import db
from pdf_gen import draw_invoice_pdf

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"

# Telegram refuse les messages vides
PING = "⬇️"


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
    vat_notice = safe_get(
        company,
        "vat_notice",
        "mention_tva",
        "tva_notice",
        default="TVA non applicable, art. 293 B du CGI",
    )

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
    INVOICES_LIST,
) = range(15)


# ---------------- Bottom main keyboard (SEULEMENT 4 BOUTONS) ----------------
def bottom_main() -> ReplyKeyboardMarkup:
    keyboard = [[
        KeyboardButton("🏠 Menu"),
        KeyboardButton("👥 Clients"),
        KeyboardButton("🧾 Créer une facture"),
        KeyboardButton("🗂️ Mes factures"),
    ]]
    return ReplyKeyboardMarkup(keyboard, resize_keyboard=True, is_persistent=True)


# ---------------- UI message (1 seul message édité) ----------------
async def ui_show(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, keyboard: InlineKeyboardMarkup | None):
    text = text if (text and text.strip()) else "…"
    chat_id = update.effective_chat.id
    ui_id = context.user_data.get("ui_msg_id")

    if ui_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=ui_id,
                text=text,
                reply_markup=keyboard,
            )
            return
        except Exception:
            context.user_data.pop("ui_msg_id", None)

    msg = await update.effective_message.reply_text(text, reply_markup=keyboard)
    context.user_data["ui_msg_id"] = msg.message_id


# ---------------- Inline menus (au-dessus) ----------------
def main_menu_inline():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🧾 Créer une facture", callback_data="TOP::NEW_INV")],
        [InlineKeyboardButton("👥 Clients", callback_data="TOP::CLIENTS")],
        [InlineKeyboardButton("🗂️ Mes factures", callback_data="TOP::INVOICES")],
    ])


def clients_inline():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📋 Liste clients", callback_data="CLIENTS::LIST")],
        [InlineKeyboardButton("➕ Ajouter client", callback_data="CLIENTS::ADD")],
        [InlineKeyboardButton("📥 Import clients", callback_data="CLIENTS::IMPORT")],
        [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")],
    ])


def new_inv_inline():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Rechercher client", callback_data="INV::SEARCH_CLIENT")],
        [InlineKeyboardButton("📋 Liste clients", callback_data="INV::LIST_CLIENTS")],
        [InlineKeyboardButton("➕ Ajouter client", callback_data="INV::ADD_CLIENT")],
        [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")],
    ])


def invoices_inline():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔎 Rechercher client", callback_data="INVOICES::SEARCH_CLIENT")],
        [InlineKeyboardButton("📋 Liste clients", callback_data="INVOICES::LIST_CLIENTS")],
        [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")],
    ])


def presets_keyboard():
    presets = CFG.get("invoice", {}).get("description_presets", [])
    rows = [[InlineKeyboardButton(p, callback_data=f"PRESET::{p}")] for p in presets]
    rows.append([InlineKeyboardButton("✍️ Saisie manuelle", callback_data="PRESET::MANUAL")])
    rows.append([InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")])
    return InlineKeyboardMarkup(rows)


def client_to_btn(c, prefix="CLIENTSEL::"):
    label = c.get("name") or c.get("nom") or "Client"
    if c.get("city"):
        label += f" — {c['city']}"
    return InlineKeyboardButton(label[:60], callback_data=f"{prefix}{c['id']}")


def invoice_to_btn(inv: dict):
    num = inv.get("number", "FACTURE")
    issue = (inv.get("issue_date") or "")[:10]
    total = float(inv.get("total_ttc") or 0.0)
    label = f"{num} • {issue} • {total:,.2f} €".replace(",", " ").replace(".", ",")
    return InlineKeyboardButton(label[:60], callback_data=f"INVFILE::{inv['id']}")


# ---------------- Navigation helpers ----------------
async def go_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["screen"] = "MENU"
    await update.effective_message.reply_text(PING, reply_markup=bottom_main())
    await ui_show(update, context, "🏠 Menu :", main_menu_inline())
    return MENU


# ---------------- Start ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not admin_allowed(update.effective_user.id):
        await update.message.reply_text("Accès refusé.")
        return ConversationHandler.END

    db.init_db()
    context.user_data.clear()
    await update.message.reply_text("✅ Bot Facture en ligne.\nUtilise le menu en bas 👇", reply_markup=bottom_main())
    return await go_menu(update, context)


# ---------------- Bottom main router (4 boutons seulement) ----------------
async def bottom_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()

    if txt == "🏠 Menu":
        return await go_menu(update, context)

    if txt == "👥 Clients":
        context.user_data["screen"] = "CLIENTS"
        await ui_show(update, context, "👥 Clients :", clients_inline())
        return CLIENTS_MENU

    if txt == "🧾 Créer une facture":
        context.user_data["screen"] = "NEW_INV"
        context.user_data.pop("client_id", None)
        context.user_data.pop("client", None)
        context.user_data.pop("new_client", None)
        await ui_show(update, context, "🧾 Nouvelle facture — choisis une option :", new_inv_inline())
        return MENU

    if txt == "🗂️ Mes factures":
        context.user_data["screen"] = "INVOICES"
        await ui_show(update, context, "🗂️ Mes factures — choisis une option :", invoices_inline())
        return INVOICES_CLIENT_PICK

    return MENU


# ---------------- Top inline handlers ----------------
async def back_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.callback_query.answer()
    return await go_menu(update, context)


async def top_menu_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "TOP::CLIENTS":
        context.user_data["screen"] = "CLIENTS"
        await ui_show(update, context, "👥 Clients :", clients_inline())
        return CLIENTS_MENU

    if q.data == "TOP::NEW_INV":
        context.user_data["screen"] = "NEW_INV"
        await ui_show(update, context, "🧾 Nouvelle facture — choisis une option :", new_inv_inline())
        return MENU

    if q.data == "TOP::INVOICES":
        context.user_data["screen"] = "INVOICES"
        await ui_show(update, context, "🗂️ Mes factures — choisis une option :", invoices_inline())
        return INVOICES_CLIENT_PICK

    return MENU


# ---------------- CLIENTS section (inline) ----------------
async def clients_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "CLIENTS::LIST":
        clients = db.list_clients(200)
        if not clients:
            await ui_show(update, context, "Aucun client enregistré.", clients_inline())
            return CLIENTS_MENU

        kb = [[client_to_btn(c, prefix="CLVIEW::")] for c in clients[:40]]
        kb.append([InlineKeyboardButton("⬅️ Retour", callback_data="TOP::CLIENTS")])
        kb.append([InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")])
        await ui_show(update, context, "📋 Liste clients :", InlineKeyboardMarkup(kb))
        return CLIENTS_MENU

    if q.data == "CLIENTS::ADD":
        await ui_show(update, context, "➕ Nouveau client\nNom du client ? (réponds dans le chat)", InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
        ]))
        return CLIENT_ADD_NAME

    if q.data == "CLIENTS::IMPORT":
        await ui_show(update, context,
                      "📥 Import clients\n\n"
                      "Colle tes clients (1 par ligne) au format :\n"
                      "NOM | ADRESSE | CP | VILLE | SIRET | TVA\n\n"
                      "Si TVA n’existe pas, mets '-'.\n\n"
                      "➡️ Colle maintenant ton bloc (réponds dans le chat).",
                      InlineKeyboardMarkup([[InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]]))
        return IMPORT_CLIENTS

    return CLIENTS_MENU


# ---------------- NEW INVOICE section (inline) ----------------
async def inv_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "INV::SEARCH_CLIENT":
        context.user_data["pending_search_mode"] = "NEW_INV"
        await ui_show(update, context, "🔎 Recherche client\nTape le nom / email / tel :", InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
        ]))
        return CLIENT_SEARCH_FOR_INV

    if q.data == "INV::LIST_CLIENTS":
        clients = db.list_clients(200)
        if not clients:
            await ui_show(update, context, "Aucun client enregistré.", new_inv_inline())
            return MENU

        kb = [[client_to_btn(c, prefix="INVCLIENTSEL::")] for c in clients[:40]]
        kb.append([InlineKeyboardButton("⬅️ Retour", callback_data="TOP::NEW_INV")])
        kb.append([InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")])
        await ui_show(update, context, "📋 Choisis un client :", InlineKeyboardMarkup(kb))
        return MENU

    if q.data == "INV::ADD_CLIENT":
        await ui_show(update, context, "➕ Nouveau client\nNom du client ? (réponds dans le chat)", InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
        ]))
        return CLIENT_ADD_NAME

    return MENU


async def client_search_for_inv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    results = db.search_clients(query, 20)
    if not results:
        await update.message.reply_text("Aucun résultat. Réessaie.", reply_markup=bottom_main())
        return CLIENT_SEARCH_FOR_INV

    kb = [[client_to_btn(c, prefix="INVCLIENTSEL::")] for c in results]
    kb.append([InlineKeyboardButton("⬅️ Retour", callback_data="TOP::NEW_INV")])
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")])
    await ui_show(update, context, "Résultats :", InlineKeyboardMarkup(kb))
    return MENU


async def client_select_for_inv(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    cid = int(q.data.split("::")[1])
    client = db.get_client(cid)

    context.user_data["client_id"] = cid
    context.user_data["client"] = client

    await ui_show(update, context, "🧾 Facture — choisis une description :", presets_keyboard())
    return INV_DESC


# ---------------- Add client flow ----------------
async def add_client_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = (update.message.text or "").strip()
    if not name:
        await update.message.reply_text("Nom vide. Réessaie.", reply_markup=bottom_main())
        return CLIENT_ADD_NAME
    context.user_data["new_client"] = {"name": name}
    await ui_show(update, context, "Adresse ligne 1 ? (réponds dans le chat)", InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
    ]))
    return CLIENT_ADD_ADDR


async def add_client_addr(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["new_client"]["address1"] = (update.message.text or "").strip()
    await ui_show(update, context, "Code postal + Ville ? (ex: 13015 Marseille)", InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
    ]))
    return CLIENT_ADD_CITYZIP


async def add_client_cityzip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    txt = (update.message.text or "").strip()
    parts = txt.split()
    context.user_data["new_client"]["zip"] = parts[0] if parts else ""
    context.user_data["new_client"]["city"] = " ".join(parts[1:]) if len(parts) > 1 else ""
    await ui_show(update, context, "SIRET du client ? (ou '-' si rien)", InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
    ]))
    return CLIENT_ADD_SIRET


async def add_client_siret(update: Update, context: ContextTypes.DEFAULT_TYPE):
    siret = (update.message.text or "").strip()
    if siret == "-":
        siret = ""
    context.user_data["new_client"]["siret"] = siret
    await ui_show(update, context, "TVA du client ? (ou '-' si rien)", InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
    ]))
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
        tva=tva,
    )
    client = db.get_client(cid)
    db.client_folder(client)

    context.user_data["client_id"] = cid
    context.user_data["client"] = client

    await ui_show(update, context, f"✅ Client ajouté: {client.get('name')}\n\n🧾 Maintenant choisis une description :", presets_keyboard())
    return INV_DESC


# ---------------- Invoice flow ----------------
async def desc_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    _, val = q.data.split("::", 1)

    if val == "MANUAL":
        await ui_show(update, context, "Tape la description (réponds dans le chat) :", InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
        ]))
        return INV_DESC

    context.user_data["description"] = val
    await ui_show(update, context, "💶 Montant à facturer (TTC – TVA non applicable) :", InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
    ]))
    return INV_PRICE


async def desc_manual(update: Update, context: ContextTypes.DEFAULT_TYPE):
    desc = (update.message.text or "").strip()
    if not desc:
        await update.message.reply_text("Description vide. Réessaie.", reply_markup=bottom_main())
        return INV_DESC
    context.user_data["description"] = desc
    await ui_show(update, context, "💶 Montant à facturer (TTC – TVA non applicable) :", InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
    ]))
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
        await update.message.reply_text("Montant invalide. Exemple: 1700 ou 1700,00", reply_markup=bottom_main())
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
        [InlineKeyboardButton("✅ Générer PDF", callback_data="INVCONF::GO")],
        [InlineKeyboardButton("✏️ Modifier numéro", callback_data="INVCONF::FORCE")],
        [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")],
    ])
    await ui_show(update, context, recap_message(context), kb)
    return INV_CONFIRM


async def inv_confirm_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "INVCONF::FORCE":
        await ui_show(update, context, "Tape le numéro (ex: 31 ou FACTURE-2026-031)", InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
        ]))
        return INV_FORCE_NUMBER

    if q.data != "INVCONF::GO":
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

    if not pdf_path.exists() or pdf_path.stat().st_size < 800:
        await ui_show(update, context, "❌ PDF invalide. Vérifie reportlab + logo_path.", InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
        ]))
        return MENU

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
        pdf_path=str(pdf_path),
    )

    await ui_show(update, context, "✅ Facture générée. Envoi du PDF…", InlineKeyboardMarkup([
        [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
    ]))

    with open(pdf_path, "rb") as f:
        await q.message.reply_document(document=InputFile(f, filename=f"{number}.pdf"))

    return await go_menu(update, context)


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
            await update.message.reply_text("Numéro invalide. Exemple: 31 ou FACTURE-2026-031", reply_markup=bottom_main())
            return INV_FORCE_NUMBER

    context.user_data["number"] = number
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Générer PDF", callback_data="INVCONF::GO")],
        [InlineKeyboardButton("✏️ Modifier numéro", callback_data="INVCONF::FORCE")],
        [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")],
    ])
    await ui_show(update, context, recap_message(context), kb)
    return INV_CONFIRM


# ---------------- Import clients ----------------
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
            tva=tva,
        )
        client = db.get_client(cid)
        db.client_folder(client)
        ok += 1

    await ui_show(update, context, f"✅ Import terminé\nAjoutés: {ok}\nIgnorés: {bad}", clients_inline())
    return CLIENTS_MENU


# ---------------- Invoices section ----------------
async def invoices_actions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "INVOICES::SEARCH_CLIENT":
        context.user_data["pending_search_mode"] = "INVOICES"
        await ui_show(update, context, "🔎 Recherche client (Mes factures)\nTape le nom / email / tel :", InlineKeyboardMarkup([
            [InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")]
        ]))
        return INVOICES_CLIENT_PICK

    if q.data == "INVOICES::LIST_CLIENTS":
        clients = db.list_clients(200)
        if not clients:
            await ui_show(update, context, "Aucun client enregistré.", invoices_inline())
            return INVOICES_CLIENT_PICK

        kb = [[client_to_btn(c, prefix="INVCL::")] for c in clients[:40]]
        kb.append([InlineKeyboardButton("⬅️ Retour", callback_data="TOP::INVOICES")])
        kb.append([InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")])
        await ui_show(update, context, "🗂️ Choisis un client :", InlineKeyboardMarkup(kb))
        return INVOICES_CLIENT_PICK

    return INVOICES_CLIENT_PICK


async def invoices_search_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.message.text or "").strip()
    results = db.search_clients(query, 20)
    if not results:
        await update.message.reply_text("Aucun résultat. Réessaie.", reply_markup=bottom_main())
        return INVOICES_CLIENT_PICK

    kb = [[client_to_btn(c, prefix="INVCL::")] for c in results]
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")])
    await ui_show(update, context, "Résultats :", InlineKeyboardMarkup(kb))
    return INVOICES_CLIENT_PICK


async def invoices_client_pick(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    client_id = int(q.data.split("::")[1])
    client = db.get_client(client_id)

    invs = db.list_invoices_for_client(client_id, limit=50)
    if not invs:
        await ui_show(update, context, f"🗂️ {client.get('name')} — aucune facture.", invoices_inline())
        return INVOICES_CLIENT_PICK

    kb = [[invoice_to_btn(inv)] for inv in invs[:40]]
    kb.append([InlineKeyboardButton("🏠 Menu", callback_data="BACK::MENU")])
    await ui_show(update, context, f"🗂️ Factures — {client.get('name')} :", InlineKeyboardMarkup(kb))
    return INVOICES_LIST


async def invoice_open(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    inv_id = int(q.data.split("::")[1])
    inv = db.get_invoice(inv_id)
    if not inv:
        await ui_show(update, context, "Facture introuvable.", invoices_inline())
        return INVOICES_LIST

    p = Path(inv.get("pdf_path", ""))
    if not p.exists():
        await ui_show(update, context, f"PDF introuvable : {p}", invoices_inline())
        return INVOICES_LIST

    filename = f"{inv.get('number','FACTURE')}.pdf"
    with open(p, "rb") as f:
        await q.message.reply_document(document=InputFile(f, filename=filename))

    return INVOICES_LIST


async def unknown(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Commande inconnue. Tape /start", reply_markup=bottom_main())


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
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                CallbackQueryHandler(top_menu_click, pattern=r"^TOP::"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
                CallbackQueryHandler(inv_actions, pattern=r"^INV::"),
                CallbackQueryHandler(clients_actions, pattern=r"^CLIENTS::"),
                CallbackQueryHandler(invoices_actions, pattern=r"^INVOICES::"),
                CallbackQueryHandler(client_select_for_inv, pattern=r"^INVCLIENTSEL::"),
            ],

            CLIENTS_MENU: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                CallbackQueryHandler(clients_actions, pattern=r"^CLIENTS::"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],

            CLIENT_SEARCH_FOR_INV: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, client_search_for_inv),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],

            CLIENT_ADD_NAME: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_name),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
            CLIENT_ADD_ADDR: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_addr),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
            CLIENT_ADD_CITYZIP: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_cityzip),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
            CLIENT_ADD_SIRET: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_siret),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
            CLIENT_ADD_TVA: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_client_tva),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],

            IMPORT_CLIENTS: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, import_clients),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],

            INV_DESC: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                CallbackQueryHandler(desc_pick, pattern=r"^PRESET::"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, desc_manual),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
            INV_PRICE: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, price_step),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
            INV_CONFIRM: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                CallbackQueryHandler(inv_confirm_click, pattern=r"^INVCONF::"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
            INV_FORCE_NUMBER: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                MessageHandler(filters.TEXT & ~filters.COMMAND, force_number),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],

            INVOICES_CLIENT_PICK: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                CallbackQueryHandler(invoices_actions, pattern=r"^INVOICES::"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, invoices_search_text),
                CallbackQueryHandler(invoices_client_pick, pattern=r"^INVCL::"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],

            INVOICES_LIST: [
                MessageHandler(filters.Regex(r"^(🏠 Menu|👥 Clients|🧾 Créer une facture|🗂️ Mes factures)$"), bottom_router),
                CallbackQueryHandler(invoice_open, pattern=r"^INVFILE::"),
                CallbackQueryHandler(back_menu, pattern=r"^BACK::MENU$"),
            ],
        },
        fallbacks=[CommandHandler("start", start)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(MessageHandler(filters.COMMAND, unknown))

    app.run_polling()


if __name__ == "__main__":
    main()
