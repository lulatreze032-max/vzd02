import os
import time
import sqlite3
import logging
import asyncio
import random
import base64
import io

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    ApplicationBuilder,
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

load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
MP_ACCESS_TOKEN = os.getenv("MP_ACCESS_TOKEN")
GROUP_CHAT_ID = int(os.getenv("GROUP_CHAT_ID") or 0)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

mp = mercadopago.SDK(MP_ACCESS_TOKEN)
DB_PATH = "payments.db"

# === BANCO DE DADOS ===
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS payments (
        payment_id TEXT PRIMARY KEY,
        user_id TEXT NOT NULL,
        amount REAL,
        status TEXT,
        created_at INTEGER
    )
    """)
    conn.commit()
    conn.close()

def save_payment(payment_id, user_id, amount, status="pending"):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    INSERT OR REPLACE INTO payments(payment_id, user_id, amount, status, created_at)
    VALUES (?, ?, ?, ?, ?)
    """, (str(payment_id), str(user_id), float(amount), status, int(time.time())))
    conn.commit()
    conn.close()

# === TEXTOS ===
MAIN_TEXT = """ 🜂 ⚛ Bem-vindo à irmandade mais foda do Brasil.
Aqui não existe Gados — só homens que Pegam Mulheres, Facil.💪
🔱 Aqui eu te ensino:
🔞 Como se comportar.
🔞 Como falar perto dela.
😈Oque Falar Pra Ela..
❤️‍🔥A psicologia por trás dos perfumes que acende desejos nas mentes femininas.
😈
E muito mais...

⚠️ Usando:
⚜ Psicologia Obscura
🌀 Manipulação Emocional 🚷
🧠 Neurolinguística
📘 Princípios de Persuasão
🏹 Elaboração de Elogios Subjetivos
⚠️ Temos Conteúdos proibidos em +24 países 
etc..
📲 2Mil Mensagens Prontas Baseadas em Psicologia e Manipulação, Faz ela responder na mesma hora.🔞

🔥Faça Qualquer Pessoa Comer Na sua mão. E Ficar Louca pra te dar,😈🔞

Para manter tudo funcionando e Ajudar nas Manutenções, cobramos apenas um valor simbólico de R$10.
Quem entra aqui não paga… investe em si mesmo🔞 """

START_COUNTER = 135920
STOP_COUNTER = 137500
counter_value = START_COUNTER

PLANS = {"vip": {"label": "🔥 Quero entrar!", "amount": 10.00}}
PROMO_CODES = {"THG100", "FLP100"}
awaiting_promo = {}
bot_app = None

# guardar último pagamento por usuário
user_last_payment = {}

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global counter_value
    counter_value = START_COUNTER

    keyboard = [
        [InlineKeyboardButton(PLANS["vip"]["label"], callback_data="buy_vip")],
        [InlineKeyboardButton("🎟️ Código Promocional", callback_data="promo")],
        [InlineKeyboardButton("🔄 Já paguei", callback_data="check_payment")]
    ]

    await update.message.reply_text(
        MAIN_TEXT,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    counter_msg = await update.message.reply_text(
        f"🔥🔞 *Membros Atuais👥⬆:* {counter_value:,}".replace(",", "."),
        parse_mode="Markdown"
    )

    asyncio.create_task(
        counter_task(context, counter_msg.chat_id, counter_msg.message_id)
    )

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
                text=f"🔥🔞 *Membros Atuais👥⬆:* {counter_value:,}".replace(",", "."),
                parse_mode="Markdown"
            )
        except:
            break

async def process_payment(update, context, plan_key):
    user_id = update.effective_user.id
    awaiting_promo.pop(user_id, None)  # <<< AQUI
    plan = PLANS.get(plan_key)

    amount = plan["amount"]
    label = plan["label"]
    user_id = update.effective_user.id

    data = {
        "transaction_amount": float(amount),
        "description": f"VIP {label} user:{user_id}",
        "payment_method_id": "pix",
        "payer": {"email": f"user{user_id}@gmail.com"},
    }

    result = mp.payment().create(data)
    response = result.get("response", {})

    pix = response.get("point_of_interaction", {}).get("transaction_data", {})

    if not pix.get("qr_code"):
        logger.error(f"PIX NÃO GERADO: {response}")
        await update.callback_query.message.reply_text(
            "❌ Erro ao gerar o PIX.\n"
            "O Mercado Pago não retornou o código.\n\n"
            "Tente novamente em alguns minutos."
        )
        return

    payment_id = response["id"]
    qr = pix["qr_code"]
    qr_b64 = pix.get("qr_code_base64")

    save_payment(payment_id, user_id, amount)
    user_last_payment[user_id] = payment_id

    try:
        target_chat = update.callback_query.message
    except:
        target_chat = update.message

    await target_chat.reply_text(
        f"""✅ *Falta só 1 passo*
Pague agora e receba o acesso 
vitalício automaticamente.

🔥 *{label}*
💰 *R$ {amount:.2f}*

🪙 *PIX Copia e Cola:*  
`{qr}`""",
        parse_mode="Markdown"
    )

    if qr_b64:
        img = io.BytesIO(base64.b64decode(qr_b64))
        await target_chat.reply_photo(img)

        await asyncio.sleep(10)
        await target_chat.reply_text(
            """✨ Seu link VIP aparece sozinho após o pagamento.
Se houver atraso, clique em *Já paguei* e o sistema libera seu acesso instantaneamente.""",
            parse_mode="Markdown"
        )

async def check_payment_status(update, context):
    uid = update.effective_user.id

    if uid not in user_last_payment:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("✅ Acesso Liberado! ENTRE", url=invite.invite_link)]]
        )
        await update.callback_query.message.reply_text(
            "❌ Você ainda não gerou um pagamento. Clique em *Quero entrar!* primeiro.",
            parse_mode="Markdown"
        )
        return

    payment_id = user_last_payment[uid]
    info = mp.payment().get(payment_id)
    status = info.get("response", {}).get("status")

    if status == "approved":
        invite = await bot_app.bot.create_chat_invite_link(
            GROUP_CHAT_ID,
            member_limit=1
        )
        await update.callback_query.message.reply_text(
            f"🎉 *Pagamento confirmado!*\nSeu acesso foi liberado!:\n{invite.invite_link}",
            parse_mode="Markdown"
        )
        return

    await update.callback_query.message.reply_text(
        f"⏳ Seu pagamento ainda está como: *{status}*\nTente novamente em alguns segundos.",
        parse_mode="Markdown"
    )

async def button(update: Update, context):
    q = update.callback_query
    await q.answer()

    if q.data == "promo":
        awaiting_promo[q.from_user.id] = True
        await q.message.reply_text("🎟️ Envie seu código promocional:")
        return

    if q.data == "buy_vip":
        await process_payment(update, context, "vip")
        return

    if q.data == "check_payment":
        await check_payment_status(update, context)
        return

async def handle_message(update: Update, context):
    uid = update.effective_user.id
    if awaiting_promo.get(uid) is not True:
        return


    awaiting_promo[uid] = False
    code = update.message.text.strip().upper()

    if code in PROMO_CODES:
        if code == "THG100":
            await update.message.reply_text("🔑 Código De Dono! exclusivo do Thiago reconhecido!")
        elif code == "FLP100":
            await update.message.reply_text("🔑 Código De Dono! exclusivo do Filipe reconhecido!")
        invite = await context.bot.create_chat_invite_link(GROUP_CHAT_ID, member_limit=1)
        await update.message.reply_text(invite.invite_link)
    else:
        await update.message.reply_text("❌ Código inválido.")

app = FastAPI()

@app.post("/webhook/mp")
async def mp_webhook(request: Request):
    return {"status": "disabled"}

def main():
    init_db()

    global bot_app
    bot_app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    bot_app.add_handler(CommandHandler("start", start))
    bot_app.add_handler(CallbackQueryHandler(button))
    bot_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    loop = asyncio.get_event_loop()
    loop.create_task(bot_app.run_polling())

    uvicorn.run(app, host="0.0.0.0", port=8000)

if __name__ == "__main__":
    main()
