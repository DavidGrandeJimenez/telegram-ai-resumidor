import os
import asyncio
import json

from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from telethon import TelegramClient

from google import genai


load_dotenv()


API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
CHATS_EXCLUIDOS = [
    8989055191,
    -1001644369540,
    -1001398583554,
    -1001105737654,
    -1001892971987,
    -1001383179613,
    -1001586310879,
    -1002373171224,
    -4289901982,
    777000,
    93372553,
    -1001245852070
]


telegram_client = TelegramClient("mi_sesion_telegram", API_ID, API_HASH)


gemini_client = genai.Client(api_key=GEMINI_API_KEY)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola. Usa /resumen para resumir los mensajes sin leer."
    )


async def resumen(update: Update, context: ContextTypes.DEFAULT_TYPE):
    dialogs = await telegram_client.get_dialogs(limit=20)

    botones = []

    for dialog in dialogs:
        if dialog.id in CHATS_EXCLUIDOS:
            continue

        botones.append([
            InlineKeyboardButton(
                dialog.name,
                callback_data=f"chat_{dialog.id}"
            )
        ])

    teclado = InlineKeyboardMarkup(botones)

    await update.message.reply_text("¿Qué chat quieres resumir?", reply_markup=teclado)


def generar_resumen(texto):
    respuesta = gemini_client.models.generate_content(
        model="gemini-3.6-flash",
        contents=(
            "Analiza la siguiente conversación de Telegram y "
            "genera un resumen en español.\n\n"

            "Debes identificar tres elementos:\n\n"

            "1. TEMAS PRINCIPALES\n"
            "Identifica los asuntos principales tratados.\n\n"

            "2. DECISIONES Y PROPUESTAS\n"
            "Identifica decisiones que realmente se hayan "
            "tomado durante la conversación. "
            "incluído propuestas, y recomendaciones. \n\n"

            "3. PREGUNTAS Y RESPUESTAS\n"
            "Identifica las preguntas relevantes que aparecen en la "
            "conversación y exponla sintetizadamente.\n"
            "Para cada pregunta, busca si existe una respuesta "
            "posterior, anterior o indirecta dentro de la conversación.\n"
            "Una respuesta indirecta es válida si permite responder "
            "razonablemente a la pregunta aunque nadie haya escrito "
            "literalmente una respuesta directa.\n"
            "Si no existe ninguna respuesta directa ni indirecta, "
            "indica claramente que no se ha respondido.\n\n"

            "No inventes información.\n"
            "No deduzcas respuestas que no estén suficientemente "
            "respaldadas por la conversación.\n"
            "No incluyas acciones pendientes.\n\n"

            "Devuelve EXCLUSIVAMENTE un JSON válido con esta estructura:\n"
            "{\n"
            '  "temas_principales": ["tema 1", "tema 2"],\n'
            '  "decisiones": ["decisión 1", "decisión 2"],\n'
            '  "preguntas_y_respuestas": [\n'
            '    {\n'
            '      "pregunta": "Pregunta realizada",\n'
            '      "respuesta": "Respuesta encontrada o '
            'No se ha respondido."\n'
            '    }\n'
            '  ]\n'
            "}\n\n"

            "Si no hay información para una categoría, "
            "devuelve una lista vacía.\n\n"

            "No incluyas Markdown.\n"
            "No incluyas texto antes ni después del JSON.\n\n"

            "CONVERSACIÓN:\n"
            + texto
        ),
        config={
            "response_mime_type": "application/json"
        }
    )

    return respuesta.text


async def seleccionar_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    chat_id = int(query.data.replace("chat_", ""))

    dialogs = await telegram_client.get_dialogs(limit=20)

    chat = None

    for dialog in dialogs:
        if dialog.id == chat_id:
            chat = dialog
            break

    if chat is None:
        await query.edit_message_text("No he podido encontrar ese chat.")
        return

    if chat.unread_count == 0:
        await query.edit_message_text(f"{chat.name}\n\nNo tienes mensajes sin leer.")
        return

    mensajes = []

    async for mensaje in telegram_client.iter_messages(
        chat.entity, limit=chat.unread_count
    ):
        if mensaje.text:
            mensajes.append(mensaje)

    mensajes.reverse()

    texto = ""

    for mensaje in mensajes:
        texto += mensaje.text + "\n\n"

    await query.edit_message_text("Estoy preparando el resumen...")

    resumen_json = await asyncio.to_thread(generar_resumen, texto)


    datos = json.loads(resumen_json)

    mensaje = f"📝 RESUMEN DE {chat.name}\n\n"

    mensaje += "🔹 TEMAS PRINCIPALES\n\n"

    for tema in datos["temas_principales"]:
        mensaje += f"• {tema}\n"

    mensaje += "\n🔹 DECISIONES\n\n"

    for decision in datos["decisiones"]:
        mensaje += f"• {decision}\n"

    mensaje += "\n🔹 PREGUNTAS Y RESPUESTAS\n\n"

    for elemento in datos["preguntas_y_respuestas"]:
        mensaje += f"❓ {elemento['pregunta']}\n"
        mensaje += f"💬 {elemento['respuesta']}\n\n"

    await query.edit_message_text(mensaje)


async def main():
    await telegram_client.start()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CommandHandler("resumen", resumen))

    app.add_handler(CallbackQueryHandler(seleccionar_chat))

    print("Bot iniciado...")

    await app.initialize()
    await app.start()
    await app.updater.start_polling()

    try:
        while True:
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        pass

    await app.updater.stop()
    await app.stop()
    await app.shutdown()

    await telegram_client.disconnect()


if __name__ == "__main__":
    asyncio.run(main())
