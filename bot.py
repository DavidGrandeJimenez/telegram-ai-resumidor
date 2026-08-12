import os

from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from telethon import TelegramClient


load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")


client = TelegramClient(
    "mi_sesion_telegram",
    API_ID,
    API_HASH
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola. Usa /resumen para ver tus chats."
    )


async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dialogs = await client.get_dialogs(limit=20)

    botones = []

    for dialog in dialogs:
        nombre = dialog.name

        botones.append([
            InlineKeyboardButton(
                nombre,
                callback_data=f"chat_{dialog.id}"
            )
        ])

    teclado = InlineKeyboardMarkup(botones)

    await update.message.reply_text(
        "¿Qué chat quieres resumir?",
        reply_markup=teclado
    )


async def seleccionar_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    chat_id = int(query.data.replace("chat_", ""))

    dialogs = await client.get_dialogs(limit=20)

    chat = None

    for dialog in dialogs:
        if dialog.id == chat_id:
            chat = dialog
            break

    if chat is None:
        await query.edit_message_text(
            "No he podido encontrar ese chat."
        )
        return

    if chat.unread_count == 0:
        await query.edit_message_text(
            f"{chat.name}\n\n"
            "No tienes mensajes sin leer."
        )
        return

    mensajes = []

    async for mensaje in client.iter_messages(
        chat.entity,
        limit=chat.unread_count
    ):
        if mensaje.text:
            mensajes.append(mensaje)

    mensajes.reverse()

    texto = f"Mensajes sin leer en {chat.name}:\n\n"

    for mensaje in mensajes:
        texto += mensaje.text + "\n\n"

    await query.edit_message_text(texto)

async def iniciar_telethon():
    await client.start()


async def iniciar_bot():
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("resumen", resumen))
    app.add_handler(CallbackQueryHandler(seleccionar_chat))

    print("Bot iniciado...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    return app


async def main():
    await iniciar_telethon()

    app = await iniciar_bot()

    try:
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        pass

    await app.updater.stop()
    await app.stop()
    await app.shutdown()


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())