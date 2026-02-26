import json
import os
import re
from datetime import date

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ConversationHandler,
    MessageHandler,
    filters,
)

import db
from pdf import build_invoice_pdf


MENU = 0
CLIENT_CHOOSE = 10
CLIENT_SEARCH = 11
CLIENT_NEW_NAME = 12
CLIENT_NEW_ADDRESS1 = 13
CLIENT_NEW_ZIPCITY = 14
CLIENT_NEW_SIRET = 15

INVOICE_DESC = 20
INVOICE_DESC_FREE = 21
INVOICE_AMOUNT = 22
INVOICE_NUMBER_CONFIRM = 23
INVOICE_NUMBER_EDIT = 24


def load_cfg() -> dict:
    with open("config.json", "r", encoding="utf-8") as f:
        return json.load(f)


def is_admin(cfg: dict, user_id: int) -> bool:
    admins = cfg.get("bot", {}).get("admin_telegram_user_ids", []) or []
    if not admins:
        return True
    return int(user_id) in set(int(x) for x in admins)


def main_menu_kb() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [["🧾 Créer une facture"], ["👤 Clients"], ["⚙️ Paramètres"]],
        resize_keyboard=True,
    )


async def start(update, context):
    await update.message.reply_text("Bienvenue 👋\nChoisis une action :", reply_markup=main_menu_kb())
    return MENU


async def menu_router(update, context):
    txt = (update.message.text or "").strip()

    if "Créer" in txt or "facture" in txt.lower():
        context.user_data.clear()
        await update.message.reply_text(
            "Pour créer une facture, choisis d'abord le client :",
            reply_markup=InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("🔎 Rechercher", callback_data="client:search")],
                    [InlineKeyboardButton("➕ Ajouter un client", callback_data="client:new")],
                ]
            ),
        )
        return CLIENT_CHOOSE

    if "Clients" in txt:
        await update.message.reply_text(
            "👤 Clients\n- Tape un mot-clé (nom/email/tel) pour rechercher\n- Ou écris /cancel pour revenir."
        )
        return CLIENT_SEARCH

    if "Param" in txt:
        cfg = load_cfg()
        if not is_admin(cfg, update.effective_user.id):
            await update.message.reply_text("Accès refusé.", reply_markup=main_menu_kb())
            return MENU

        today = date.today()
        next_seq = db.get_next_invoice_seq(today)
        prefix = cfg.get("invoice", {}).get("number_prefix", "FACTURE")
        digits = int(cfg.get("invoice", {}).get("number_digits", 3))
        preview = db.invoice_number_from_seq(prefix, today, next_seq, digits=digits)

        await update.message.reply_text(
            "⚙️ Paramètres\n\n"
            f"Prochain numéro (auto) : *{preview}*\n\n"
            "➡️ Pour changer le prochain numéro, envoie :\n"
            "`/setnext 26`\n\n"
            "(Ça définit le prochain compteur de l'année en cours.)",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=main_menu_kb(),
        )
        return MENU

    await update.message.reply_text("Choisis via le menu 🙂", reply_markup=main_menu_kb())
    return MENU


async def setnext(update, context):
    cfg = load_cfg()
    if not is_admin(cfg, update.effective_user.id):
        await update.message.reply_text("Accès refusé.")
        return

    if not context.args:
        await update.message.reply_text("Utilisation: /setnext 26")
        return

    raw = " ".join(context.args).strip()
    try:
        seq = int(re.sub(r"\D", "", raw))
    except Exception:
        seq = 0
    if seq <= 0:
        await update.message.reply_text("Je n'ai pas compris. Exemple: /setnext 26")
        return

    db.set_next_invoice_seq(date.today(), seq)

    prefix = cfg.get("invoice", {}).get("number_prefix", "FACTURE")
    digits = int(cfg.get("invoice", {}).get("number_digits", 3))
    preview = db.invoice_number_from_seq(prefix, date.today(), seq, digits=digits)
    await update.message.reply_text(f"✅ OK. Prochain numéro = *{preview}*", parse_mode=ParseMode.MARKDOWN)


async def client_choose_cb(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "client:search":
        await q.edit_message_text("Tape le nom / email / tel du client :")
        return CLIENT_SEARCH

    if data == "client:new":
        await q.edit_message_text("Nom du client (Entreprise) :")
        return CLIENT_NEW_NAME

    if data.startswith("client:pick:"):
        client_id = int(data.split(":")[-1])
        context.user_data["client_id"] = client_id
        client = db.get_client(client_id)
        last = db.get_client_last_desc(client_id)

        await q.edit_message_text(
            f"✅ Client choisi: *{client['name']}*\n\nMaintenant, choisis une description :",
            parse_mode=ParseMode.MARKDOWN,
            reply_markup=description_kb(load_cfg(), last_first=last),
        )
        return INVOICE_DESC

    await q.edit_message_text("Action inconnue.")
    return MENU


async def client_search(update, context):
    q = (update.message.text or "").strip()
    items = db.list_clients(limit=10, q=q)
    if not items:
        await update.message.reply_text("Aucun résultat. Réessaie.")
        return CLIENT_SEARCH

    kb = []
    for c in items:
        label = c["name"]
        if c.get("email"):
            label += f" • {c['email']}"
        kb.append([InlineKeyboardButton(label[:60], callback_data=f"client:pick:{c['id']}")])

    kb.append([InlineKeyboardButton("➕ Ajouter un client", callback_data="client:new")])
    await update.message.reply_text("Choisis le client :", reply_markup=InlineKeyboardMarkup(kb))
    return CLIENT_CHOOSE


async def client_new_name(update, context):
    context.user_data["new_client"] = {"name": (update.message.text or "").strip()}
    await update.message.reply_text("Adresse ligne 1 (ex: 1 rue ... ) :")
    return CLIENT_NEW_ADDRESS1


async def client_new_address1(update, context):
    context.user_data["new_client"]["address1"] = (update.message.text or "").strip()
    await update.message.reply_text("Code postal + Ville (ex: 13013 Marseille) :")
    return CLIENT_NEW_ZIPCITY


async def client_new_zipcity(update, context):
    raw = (update.message.text or "").strip()
    m = re.match(r"^(\d{4,5})\s+(.+)$", raw)
    if not m:
        await update.message.reply_text("Format attendu: 13013 Marseille")
        return CLIENT_NEW_ZIPCITY
    context.user_data["new_client"]["zip"] = m.group(1)
    context.user_data["new_client"]["city"] = m.group(2).strip()
    await update.message.reply_text("SIRET (ou '-' si tu n'as pas) :")
    return CLIENT_NEW_SIRET


async def client_new_siret(update, context):
    s = (update.message.text or "").strip()
    if s != "-":
        context.user_data["new_client"]["siret"] = s
    cid = db.upsert_client(context.user_data["new_client"])
    context.user_data["client_id"] = cid
    client = db.get_client(cid)

    await update.message.reply_text(
        f"✅ Client ajouté: *{client['name']}*\n\nChoisis une description :",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=description_kb(load_cfg(), last_first=None),
    )
    return INVOICE_DESC


def description_kb(cfg: dict, last_first: str | None) -> InlineKeyboardMarkup:
    presets = (cfg.get("descriptions", {}).get("presets") or [])
    options = []
    if last_first:
        options.append(last_first)
    for p in presets:
        if p and p not in options:
            options.append(p)
    options = options[:8]

    kb = []
    for opt in options:
        kb.append([InlineKeyboardButton(opt[:60], callback_data=f"desc:pick:{opt}")])
    kb.append([InlineKeyboardButton("✍️ Saisie libre", callback_data="desc:free")])
    return InlineKeyboardMarkup(kb)


async def invoice_desc_cb(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "desc:free":
        await q.edit_message_text("OK. Envoie la description (ex: Prestation de services) :")
        return INVOICE_DESC_FREE

    if data.startswith("desc:pick:"):
        desc = data.split("desc:pick:", 1)[1]
        context.user_data["invoice_desc"] = desc
        db.add_description(desc)
        db.set_client_last_desc(int(context.user_data["client_id"]), desc)

        await q.edit_message_text(
            f"✅ Description: *{desc}*\n\nMontant TTC ? (ex: 738 ou 738,00)",
            parse_mode=ParseMode.MARKDOWN,
        )
        return INVOICE_AMOUNT

    await q.edit_message_text("Action inconnue.")
    return MENU


async def invoice_desc_free(update, context):
    desc = (update.message.text or "").strip()
    if len(desc) < 2:
        await update.message.reply_text("Description trop courte. Réessaie :")
        return INVOICE_DESC_FREE
    context.user_data["invoice_desc"] = desc
    db.add_description(desc)
    db.set_client_last_desc(int(context.user_data["client_id"]), desc)

    await update.message.reply_text("Montant TTC ? (ex: 738 ou 738,00)")
    return INVOICE_AMOUNT


def _parse_amount(text: str) -> float | None:
    t = (text or "").strip().replace("€", "").replace(" ", "")
    t = t.replace(",", ".")
    try:
        v = float(t)
        if v <= 0:
            return None
        return v
    except Exception:
        return None


async def invoice_amount(update, context):
    amount_ttc = _parse_amount(update.message.text)
    if amount_ttc is None:
        await update.message.reply_text("Montant invalide. Exemple: 738,00")
        return INVOICE_AMOUNT

    context.user_data["amount_ttc"] = float(amount_ttc)

    cfg = load_cfg()
    inv_cfg = cfg.get("invoice", {})
    prefix = inv_cfg.get("number_prefix", "FACTURE")
    digits = int(inv_cfg.get("number_digits", 3))

    issue = date.today()
    next_seq = db.get_next_invoice_seq(issue)
    suggested = db.invoice_number_from_seq(prefix, issue, next_seq, digits=digits)

    context.user_data["issue_date"] = issue
    context.user_data["suggested_number"] = suggested
    context.user_data["suggested_seq"] = next_seq

    await update.message.reply_text(
        "Numéro de facture :\n"
        f"➡️ *{suggested}*\n\n"
        "Tu veux le garder ou le modifier ?",
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("✅ Valider", callback_data="num:ok")],
                [InlineKeyboardButton("✏️ Modifier", callback_data="num:edit")],
            ]
        ),
    )
    return INVOICE_NUMBER_CONFIRM


async def invoice_number_cb(update, context):
    q = update.callback_query
    await q.answer()
    data = q.data

    if data == "num:edit":
        await q.edit_message_text(
            "Envoie le numéro souhaité :\n"
            "- soit juste le numéro (ex: 26)\n"
            "- soit le format complet (ex: FACTURE-2026-026)"
        )
        return INVOICE_NUMBER_EDIT

    if data == "num:ok":
        number = context.user_data["suggested_number"]
        seq = int(context.user_data["suggested_seq"])
        issue = context.user_data["issue_date"]

        db.set_next_invoice_seq(issue, seq + 1)
        await q.edit_message_text("OK. Je génère la facture…")
        await _finalize_invoice(update, context, number=number)
        return MENU

    await q.edit_message_text("Action inconnue")
    return MENU


async def invoice_number_edit(update, context):
    raw = (update.message.text or "").strip()

    cfg = load_cfg()
    inv_cfg = cfg.get("invoice", {})
    prefix = inv_cfg.get("number_prefix", "FACTURE")
    digits = int(inv_cfg.get("number_digits", 3))
    issue: date = context.user_data["issue_date"]

    if re.fullmatch(r"\d{1,6}", raw):
        seq = int(raw)
        number = db.invoice_number_from_seq(prefix, issue, seq, digits=digits)
        db.set_next_invoice_seq(issue, seq + 1)
    else:
        number = raw
        m = re.search(r"(\d{1,6})\s*$", raw)
        if m:
            try:
                db.set_next_invoice_seq(issue, int(m.group(1)) + 1)
            except Exception:
                pass

    await update.message.reply_text("OK. Je génère la facture…")
    await _finalize_invoice(update, context, number=number)
    return MENU


async def _finalize_invoice(update, context, number: str):
    cfg = load_cfg()
    seller = cfg.get("seller", {})
    inv_cfg = cfg.get("invoice", {})
    issue: date = context.user_data.get("issue_date") or date.today()

    amount_ttc = float(context.user_data["amount_ttc"])
    vat_rate = 0.0
    total_ht = amount_ttc
    total_vat = 0.0
    total_ttc = amount_ttc

    invoice = {
        "number": number,
        "issue_date": issue.strftime("%d/%m/%Y"),
        "due_text": inv_cfg.get("due_default", "À la réception de la facture"),
        "operation_type": inv_cfg.get("operation_type_default", "Prestation de services"),
        "description": context.user_data["invoice_desc"],
        "qty": float(inv_cfg.get("qty_default", 1)),
        "unit": inv_cfg.get("unit_default", "u"),
        "unit_price": float(amount_ttc),
        "vat_rate": vat_rate,
        "total_ht": total_ht,
        "total_vat": total_vat,
        "total_ttc": total_ttc,
        "currency": inv_cfg.get("currency", "EUR"),
    }

    client_id = int(context.user_data["client_id"])
    client = db.get_client(client_id)

    try:
        db.create_invoice(
            {
                **invoice,
                "issue_date": issue.isoformat(),
                "client_id": client_id,
            }
        )
    except Exception as e:
        await update.effective_chat.send_message(
            "⚠️ Erreur en enregistrant la facture.\n"
            "Vérifie le numéro (il existe peut-être déjà) et réessaie.\n\n"
            f"Détail: {e}"
        )
        return

    out_dir = os.path.join("data", "pdf")
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, f"{number}.pdf")

    build_invoice_pdf(
        out_path=pdf_path,
        cfg=cfg,
        invoice=invoice,
        seller=seller,
        client=client,
    )

    caption = (
        f"🧾 *Facture créée*\n"
        f"- N°: `{number}`\n"
        f"- Client: *{client['name']}*\n"
        f"- Total: *{amount_ttc:.2f} €*\n"
    )

    await update.effective_chat.send_document(
        document=open(pdf_path, "rb"),
        filename=f"{number}.pdf",
        caption=caption,
        parse_mode=ParseMode.MARKDOWN,
        reply_markup=main_menu_kb(),
    )


async def cancel(update, context):
    await update.message.reply_text("OK. Retour menu.", reply_markup=main_menu_kb())
    return MENU


def build_app() -> Application:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN manquant. Mets la variable Railway BOT_TOKEN.")

    db.init_db()
    cfg = load_cfg()
    db.seed_descriptions(cfg.get("descriptions", {}).get("presets") or [])

    app = Application.builder().token(token).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MENU: [MessageHandler(filters.TEXT & ~filters.COMMAND, menu_router)],
            CLIENT_CHOOSE: [CallbackQueryHandler(client_choose_cb)],
            CLIENT_SEARCH: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_search)],
            CLIENT_NEW_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_new_name)],
            CLIENT_NEW_ADDRESS1: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_new_address1)],
            CLIENT_NEW_ZIPCITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_new_zipcity)],
            CLIENT_NEW_SIRET: [MessageHandler(filters.TEXT & ~filters.COMMAND, client_new_siret)],
            INVOICE_DESC: [CallbackQueryHandler(invoice_desc_cb)],
            INVOICE_DESC_FREE: [MessageHandler(filters.TEXT & ~filters.COMMAND, invoice_desc_free)],
            INVOICE_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, invoice_amount)],
            INVOICE_NUMBER_CONFIRM: [CallbackQueryHandler(invoice_number_cb)],
            INVOICE_NUMBER_EDIT: [MessageHandler(filters.TEXT & ~filters.COMMAND, invoice_number_edit)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        allow_reentry=True,
    )

    app.add_handler(conv)
    app.add_handler(CommandHandler("setnext", setnext))
    return app


if __name__ == "__main__":
    app = build_app()
    print("Bot lancé…")
    app.run_polling(close_loop=False)
