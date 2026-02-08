import os
import time
import sqlite3
import logging
import asyncio
import random
import base64
import io

from telegram import InputMediaVideo
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from dotenv import load_dotenv
import mercadopago
from fastapi import FastAPI, Request
import uvicorn

# ================= CONFIG =================
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID") or 0)

START_VIDEO_URL_1 = "https://files.catbox.moe/4abfa3.mp4"
START_VIDEO_URL_2 = "https://files.catbox.moe/yu3i0y.mp4"

PRE_PAYMENT_VIDEO_URL = "https://files.catbox.moe/p3tfer.mp4"
ABANDON_VIDEO_URL = "https://files.catbox.moe/hotdya.mp4"

PREVIEW_VIDEO_1 = "https://files.catbox.moe/978wjh.mp4"
PREVIEW_VIDEO_2 = "https://files.catbox.moe/zqtrmi.mp4"
PREVIEW_VIDEO_3 = "https://files.catbox.moe/5ynxw8.mp4"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mp = mercadopago.SDK(MP_ACCESS_TOKEN)

DB_PATH = "payments.db"

# ================= DATABASE =================
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS payments (
            payment_id TEXT PRIMARY KEY,
            user_id TEXT,
            plan TEXT,
            amount REAL,
            status TEXT,
            created_at INTEGER
        )
    """)
    conn.commit()
    conn.close()

def save_payment(payment_id, user_id, plan, amount, status="pending"):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO payments
        VALUES (?, ?, ?, ?, ?, ?)
    """, (str(payment_id), str(user_id), plan, amount, status, int(time.time())))
    conn.commit()
    conn.close()

# ================= TEXTOS =================
MAIN_TEXT = """

🚀 Liberado na hora
🛠️ Suporte 24h
📦 Atualizações diárias
🔒 Compra 100% segura

🔞 Escolha seu plano especial abaixo: 👇
"""

START_COUNTER = 135920
STOP_COUNTER = 137500
counter_value = START_COUNTER

PLANS = {
    "mensal": {"label": "💳 Mensal — R$13", "amount": 13.00},
    "vitalicio": {"label": "🔥 Vitalício — R$16", "amount": 16.00},
}

PLANS["vitalicio_promo"] = {
    "label": "🔥 Vitalício Promo — R$12,50",
    "amount": 12.50
}

PROMO_CODES = {"THG100", "KLM100"}

awaiting_promo = {}
user_last_payment = {}
abandoned_tasks = {}

PREVIEW_BUTTON = InlineKeyboardButton("👀 Prévias", callback_data="preview")

# ================= PREVIEWS =================
async def send_previews(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.callback_query.message.chat_id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Quero entrar", callback_data="restart")]
    ])

    previas = [
        {
            "video": PREVIEW_VIDEO_1,
            "texto": "🔥 *Prévia 1*\n\nVeja um pouco do conteúdo exclusivo que te espera."
        },
        {
            "video": PREVIEW_VIDEO_2,
            "texto": "🔥 *Prévia 2*\n\nAtualizações diárias e acesso imediato."
        },
        {
            "video": PREVIEW_VIDEO_3,
            "texto": "🔥 *Prévia 3*\n\nÚltima chance de entrar hoje 👇"
        },
    ]

    for previa in previas:
        # Envia o vídeo
        await context.bot.send_video(
            chat_id=chat_id,
            video=previa["video"]
        )

        # Envia a mensagem com botão logo abaixo
        await context.bot.send_message(
            chat_id=chat_id,
            text=previa["texto"],
            parse_mode="Markdown",
            reply_markup=keyboard
        )

        await asyncio.sleep(1)

# ================= ABANDONO =================
async def abandoned_flow(context, chat_id):
    await asyncio.sleep(180)

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Quero entrar", callback_data="restart")]
    ])

    await context.bot.send_video(chat_id, ABANDON_VIDEO_URL)
    await context.bot.send_message(
        chat_id,
        "⏰ *Ei! Ainda dá tempo de entrar.*\n\nClique abaixo 👇",
        parse_mode="Markdown",
        reply_markup=keyboard
    )

# ================= START =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global counter_value
    counter_value = START_COUNTER

    uid = update.effective_user.id

    task = abandoned_tasks.pop(uid, None)
    if task:
        task.cancel()

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(PLANS["mensal"]["label"], callback_data="buy_mensal")],
        [InlineKeyboardButton(PLANS["vitalicio"]["label"], callback_data="buy_vitalicio")],
        [InlineKeyboardButton("🎟️ Código", callback_data="promo")],
        [PREVIEW_BUTTON],
    ])

    # 🔒 START VISUAL
    try:
        media = [
            InputMediaVideo(media=START_VIDEO_URL_1),
            InputMediaVideo(media=START_VIDEO_URL_2),
        ]

        await context.bot.send_media_group(
            chat_id=update.effective_chat.id,
            media=media
        )

    except Exception as e:
        logger.error(f"Erro ao enviar vídeos do start: {e}")

    # texto SEMPRE aparece
    await update.message.reply_text(MAIN_TEXT, reply_markup=keyboard)

    counter_msg = await update.message.reply_text(
        f"🔥🔞 *Membros Atuais 👥⬆:* {counter_value:,}".replace(",", "."),
        parse_mode="Markdown"
    )

    asyncio.create_task(
        counter_task(context, counter_msg.chat_id, counter_msg.message_id)
    )

    abandoned_tasks[uid] = asyncio.create_task(
        abandoned_flow(context, update.effective_chat.id)
    )

# ================= CONTADOR =================
async def counter_task(context, chat_id, message_id):
    global counter_value
    while counter_value < STOP_COUNTER:
        await asyncio.sleep(1.8)
        counter_value += random.randint(1, 3)
        if counter_value > STOP_COUNTER:
            counter_value = STOP_COUNTER
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=message_id,
                text=f"🔥🔞 *Membros Atuais 👥⬆:* {counter_value:,}".replace(",", "."),
                parse_mode="Markdown"
            )
        except:
            break

# ================= PAGAMENTO =================
async def process_payment(update, context, plan_key):
    user_id = update.effective_user.id
    awaiting_promo.pop(user_id, None)

    plan = PLANS[plan_key]
    msg = update.callback_query.message

    data = {
        "transaction_amount": plan["amount"],
        "description": f"{plan_key.upper()} user:{user_id}",
        "payment_method_id": "pix",
        "payer": {"email": f"user{user_id}@gmail.com"},
    }

    result = mp.payment().create(data)
    response = result.get("response", {})

    pix = response.get("point_of_interaction", {}).get("transaction_data", {})
    if not pix.get("qr_code"):
        await msg.reply_text("❌ Erro ao gerar o PIX. Tente novamente.")
        return

    payment_id = response["id"]
    qr = pix["qr_code"]
    qr_b64 = pix.get("qr_code_base64")

    save_payment(payment_id, user_id, plan_key, plan["amount"])
    user_last_payment[user_id] = payment_id

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 Já paguei", callback_data="check_payment")]
    ])

    await msg.edit_reply_markup(reply_markup=None)

    # 1️⃣ Envia o QR Code (imagem) SEM botão
    if qr_b64:
        img = io.BytesIO(base64.b64decode(qr_b64))
        img.name = "pix.png"  # importante
        await msg.reply_photo(photo=img)

    # 2️⃣ Envia o texto + botão em OUTRA mensagem
    await msg.reply_text(
        f"💰 {plan['label']}\n\n"
        f"🪙 PIX Copia e Cola:\n"
        f"{qr}\n\n"
        "✅ Após realizar o pagamento, clique no botão abaixo 👇",
        reply_markup=keyboard
    )


# ================= CHECK PAGAMENTO =================
async def check_payment_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    if uid not in user_last_payment:
        await update.callback_query.message.reply_text("✖ pagamento ainda não confirmado!")
        return

    payment_id = user_last_payment[uid]
    info = mp.payment().get(payment_id)
    status = info.get("response", {}).get("status")

    if status == "approved":
        task = abandoned_tasks.pop(uid, None)
        if task:
            task.cancel()

        invite = await context.bot.create_chat_invite_link(
            chat_id=GROUP_CHAT_ID,
            member_limit=1
        )

        await update.callback_query.message.reply_text(
            f"✔ Pagamento aprovado!\n<a href='{invite.invite_link}'>Entrar no grupo</a>",
            parse_mode="HTML",
            disable_web_page_preview=True
        )
    else:
        await update.callback_query.message.reply_text("⏳ Pagamento ainda em processamento...")


async def send_vip_offer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    msg = q.message

    text = (
        "🍀 *HOJE É O SEU DIA DE SORTE!*\n\n"
        "⚠️ Essa oferta NÃO aparece para todo mundo.\n\n"
        "Por algum motivo, *você foi selecionado agora* para receber o acesso\n"
        "🔥 *VIP VITALÍCIO* 🔥 com *DESCONTO EXCLUSIVO*.\n\n"
        "💎 De ~R$16,00~\n"
        "👉 *APENAS R$12,50* (pagamento único, acesso pra sempre)\n\n"
        "⏰ *ATENÇÃO:*\n"
        "Essa oferta expira em *5 minutos* e *nunca mais aparece* depois disso.\n\n"
        "Depois que o tempo acabar:\n"
        "❌ o valor volta ao normal\n"
        "❌ o desconto desaparece\n\n"
        "👇 Clique agora antes que seja tarde:"
    )

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔥 Quero o VIP Vitalício por R$12,50", callback_data="buy_vitalicio_promo")]
    ])

    await msg.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)
# ================= BUTTON =================
async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()

    if q.data == "buy_mensal":
        await process_payment(update, context, "mensal")

    elif q.data == "buy_vitalicio":
        await process_payment(update, context, "vitalicio")

    elif q.data == "check_payment":
        await check_payment_status(update, context)

    elif q.data == "promo":
        awaiting_promo[q.from_user.id] = True
        await q.message.reply_text("🎟️ Envie o código:")

    elif q.data == "preview":
        await send_previews(update, context)
   
    elif q.data == "restart":
        await send_vip_offer(update, context)

    elif q.data == "buy_vitalicio_promo":
        await process_payment(update, context, "vitalicio_promo")

# ================= PROMO =================
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id
    if awaiting_promo.get(uid) is not True:
        return

    awaiting_promo[uid] = False
    code = update.message.text.strip().upper()

    if code in PROMO_CODES:
        invite = await context.bot.create_chat_invite_link(GROUP_CHAT_ID, member_limit=1)
        await update.message.reply_text(invite.invite_link)
    else:
        await update.message.reply_text("❌ Código inválido.")

# ================= FASTAPI =================
app = FastAPI()

@app.post("/webhook/mp")
async def mp_webhook(request: Request):
    return {"status": "disabled"}

# ================= MAIN =================
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CallbackQueryHandler(button))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    application.run_polling()


if __name__ == "__main__":
    main()
