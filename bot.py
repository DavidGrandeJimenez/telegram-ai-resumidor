import os
import asyncio
import json
import traceback
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram import InlineKeyboardButton
from telegram import InlineKeyboardMarkup

from telethon import TelegramClient
from telethon.tl import functions
from telethon.sessions import StringSession

from google import genai


load_dotenv()


API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
MAX_TOKENS_GEMINI = 10000
GEMINI_ACTIVO = True
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

telegram_session = os.getenv("TELEGRAM_SESSION")

telegram_client = TelegramClient(
    StringSession(telegram_session),
    API_ID,
    API_HASH
)


gemini_client = genai.Client(api_key=GEMINI_API_KEY)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Hola. Usa /resumen para resumir los mensajes sin leer."
    )

async def enviar_error_telegram(update, error):
    try:
        mensaje = (
            "🚨 ERROR EN EL BOT\n\n"
            f"Tipo: {type(error).__name__}\n"
            f"Mensaje: {str(error)}\n\n"
            "Detalles:\n"
            f"{traceback.format_exc()}"
        )

        # Telegram limita el tamaño de los mensajes
        if len(mensaje) > 4000:
            mensaje = mensaje[:4000]

        if update and update.effective_chat:
            await update.effective_chat.send_message(mensaje)

    except Exception as error_envio:
        print(f"No se pudo enviar el error a Telegram: {error_envio}")

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

def dividir_texto(texto, max_tokens=15000):
    max_caracteres = max_tokens * 4

    bloques = []
    bloque_actual = ""
    
    mensajes = texto.split("\n\n")

    for mensaje in mensajes:
        if not mensaje.strip():
            continue

        if len(bloque_actual) + len(mensaje) + 2 <= max_caracteres:
            bloque_actual += mensaje + "\n\n"
        else:
            if bloque_actual:
                bloques.append(bloque_actual.strip())

            bloque_actual = mensaje + "\n\n"

    if bloque_actual:
        bloques.append(bloque_actual.strip())

    return bloques
def generar_resumen_parcial(texto):
    respuesta = gemini_client.models.generate_content(
        model="gemini-3.6-flash",
        contents=(
            "Analiza esta parte de una conversación de Telegram.\n\n"

            "Extrae toda la información relevante que pueda ser "
            "necesaria para construir posteriormente un resumen "
            "completo de la conversación.\n\n"

            "Identifica:\n"
            "- Resumen de esta parte.\n"
            "- Temas principales.\n"
            "- Decisiones realmente tomadas.\n"
            "- Preguntas y sus respuestas, directas o indirectas.\n\n"

            "No inventes información.\n"
            "Si una pregunta no tiene respuesta en esta parte, "
            "indica que no se ha respondido en esta parte.\n\n"

            "Devuelve EXCLUSIVAMENTE un JSON válido con esta estructura:\n"
            "{\n"
            '  "resumen": "Resumen de esta parte",\n'
            '  "temas_principales": ["tema 1"],\n'
            '  "decisiones": ["decisión 1"],\n'
            '  "preguntas_y_respuestas": [\n'
            '    {\n'
            '      "pregunta": "Pregunta",\n'
            '      "respuesta": "Respuesta o '
            'No se ha respondido en esta parte."\n'
            '    }\n'
            '  ]\n'
            "}\n\n"

            "CONVERSACIÓN:\n"
            + texto
        ),
        config={
            "response_mime_type": "application/json"
        }
    )

    return respuesta.text
def generar_resumen_final(resumenes_parciales):
    texto_resumenes = "\n\n--- SIGUIENTE BLOQUE ---\n\n".join(
        resumenes_parciales
    )

    respuesta = gemini_client.models.generate_content(
        model="gemini-3.6-flash",
        contents=(
            "Has recibido varios análisis parciales de una conversación "
            "de Telegram.\n\n"

            "Combina todos los análisis en un único resumen final "
            "coherente y sin duplicaciones.\n\n"

            "Debes:\n"
            "- Crear un resumen general de toda la conversación.\n"
            "- Unificar los temas principales.\n"
            "- Identificar únicamente las decisiones realmente tomadas.\n"
            "- Unificar preguntas repetidas.\n"
            "- Relacionar preguntas con sus respuestas aunque la pregunta "
            "y la respuesta aparezcan en bloques diferentes.\n"
            "- Si una pregunta no tiene respuesta en ningún bloque, "
            "indicar que no se ha respondido.\n\n"

            "No inventes información.\n"
            "No incluyas acciones pendientes.\n\n"

            "Devuelve EXCLUSIVAMENTE un JSON válido con esta estructura:\n"
            "{\n"
            '  "resumen": "Resumen general",\n'
            '  "temas_principales": ["tema 1", "tema 2"],\n'
            '  "decisiones": ["decisión 1"],\n'
            '  "preguntas_y_respuestas": [\n'
            '    {\n'
            '      "pregunta": "Pregunta",\n'
            '      "respuesta": "Respuesta o No se ha respondido."\n'
            '    }\n'
            '  ]\n'
            "}\n\n"

            "ANÁLISIS PARCIALES:\n"
            + texto_resumenes
        ),
        config={
            "response_mime_type": "application/json"
        }
    )

    return respuesta.text
def generar_resumen_inteligente(texto):
    tokens_estimados = estimar_tokens(texto)

    if tokens_estimados <= MAX_TOKENS_GEMINI:
        return generar_resumen(texto)

    bloques = dividir_texto(texto)

    print(
        f"Conversación demasiado grande: "
        f"{tokens_estimados} tokens estimados."
    )

    print(
        f"Se dividirá en {len(bloques)} bloques."
    )

    resumenes_parciales = []

    for i, bloque in enumerate(bloques, start=1):
        print(
            f"Procesando bloque {i}/{len(bloques)}..."
        )

        resumen_parcial = generar_resumen_parcial(bloque)

        resumenes_parciales.append(resumen_parcial)

    print("Generando resumen final...")

    return generar_resumen_final(resumenes_parciales)

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

def filtrar_mensajes(messages):
    mensajes_filtrados = []

    for message in messages:
        if not message.message:
            continue

        texto = message.message.strip()

        if not texto:
            continue

        mensajes_filtrados.append(message)

    return mensajes_filtrados

def estimar_tokens(texto):
    return max(1, len(texto) // 4)

async def diagnosticar_chat(chat):
    print("\n========== DIAGNÓSTICO DEL CHAT ==========")

    print(f"Nombre: {chat.name}")
    print(f"ID: {chat.id}")
    print(f"Tipo: {type(chat.entity).__name__}")

    print(f"Unread count: {chat.unread_count}")

    entity = chat.entity

    print(f"Entity ID: {getattr(entity, 'id', None)}")
    print(f"Username: {getattr(entity, 'username', None)}")
    print(f"Title: {getattr(entity, 'title', None)}")
    print(f"Megagroup: {getattr(entity, 'megagroup', None)}")
    print(f"Broadcast: {getattr(entity, 'broadcast', None)}")

    print("\nAtributos relacionados con topics/discusiones:")

    atributos = [
        "forum",
        "linked_chat_id",
        "discussion",
        "megagroup",
        "broadcast"
    ]

    for atributo in atributos:
        print(
            f"{atributo}: "
            f"{getattr(entity, atributo, None)}"
        )

    print("==========================================\n")

async def obtener_topics(chat):
    resultado = await telegram_client(
        functions.messages.GetForumTopicsRequest(
            peer=chat.entity,
            q="",
            offset_date=None,
            offset_id=0,
            offset_topic=0,
            limit=100
        )
    )

    return resultado.topics

async def error_handler(update, context):
    error = context.error

    print("ERROR:")
    traceback.print_exception(
        type(error),
        error,
        error.__traceback__
    )

    await enviar_error_telegram(update, error)

async def obtener_mensajes_topic(chat, topic_id):

    mensajes = []
    offset_id = 0

    while True:

        resultado = await telegram_client(
            functions.messages.GetRepliesRequest(
                peer=chat.entity,
                msg_id=topic_id,
                offset_id=offset_id,
                offset_date=None,
                add_offset=0,
                limit=100,
                max_id=0,
                min_id=0,
                hash=0
            )
        )

        nuevos = [
            mensaje
            for mensaje in resultado.messages
            if mensaje.message
        ]

        if not nuevos:
            break

        mensajes.extend(nuevos)

        print(
            f"Mensajes recuperados del Topic: "
            f"{len(mensajes)}"
        )

        # El último mensaje de este bloque
        # será nuestro nuevo punto de paginación
        ultimo_id = resultado.messages[-1].id

        if ultimo_id == offset_id:
            break

        offset_id = ultimo_id

        # Si hemos recibido menos de 100,
        # probablemente hemos llegado al final
        if len(resultado.messages) < 100:
            break

    # Evitar duplicados por seguridad
    mensajes_unicos = {
        mensaje.id: mensaje
        for mensaje in mensajes
    }

    mensajes = list(mensajes_unicos.values())

    mensajes.sort(key=lambda mensaje: mensaje.id)

    return mensajes


async def diagnosticar_topic(chat, topic_id):
    print("\n========== DIAGNÓSTICO DEL TOPIC ==========")
    print(f"Chat ID: {chat.id}")
    print(f"Topic ID: {topic_id}")

    try:
        resultado = await telegram_client(
            functions.messages.GetRepliesRequest(
                peer=chat.entity,
                msg_id=topic_id,
                offset_id=0,
                offset_date=None,
                add_offset=0,
                limit=100,
                max_id=0,
                min_id=0,
                hash=0
            )
        )

        print(f"Mensajes recibidos: {len(resultado.messages)}")
        print(f"Total indicado por Telegram: {getattr(resultado, 'count', 'desconocido')}")

        for mensaje in resultado.messages:
            print(
                f"ID: {mensaje.id} | "
                f"Texto: {(mensaje.message or '')[:100]}"
            )

    except Exception as e:
        print(f"ERROR: {type(e).__name__}: {e}")

    print("===========================================\n")

async def seleccionar_chat(update, context):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("topic:"):
        partes = query.data.split(":")

        chat_id = int(partes[1])
        topic_id = int(partes[2])

        print(f"Topic seleccionado: {topic_id}")
        print(f"Chat seleccionado: {chat_id}")

        chat = None

        dialogs = await telegram_client.get_dialogs(limit=20)

        for dialog in dialogs:
            if dialog.id == chat_id:
                chat = dialog
                break

        if chat is None:
            await query.edit_message_text(
                "No he podido encontrar ese chat."
            )
            return

        await query.edit_message_text(
            "🔎 Probando acceso al Topic..."
        )

        mensajes = await obtener_mensajes_topic(chat, topic_id)

        print(f"Mensajes obtenidos del Topic: {len(mensajes)}")

        caracteres = sum(
            len(mensaje.message)
            for mensaje in mensajes
        )

        print(f"Caracteres: {caracteres}")

        await query.edit_message_text(
            f"✅ Topic encontrado\n\n"
            f"Chat: {chat.name}\n"
            f"Topic ID: {topic_id}\n\n"
            "Mira el resultado en la terminal."
        )

        return

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

    await diagnosticar_chat(chat)

    if getattr(chat.entity, "forum", False):
        topics = await obtener_topics(chat)

        botones = []

        for topic in topics:
            botones.append(
                [
                    InlineKeyboardButton(
                        topic.title,
                        callback_data=f"topic:{chat.id}:{topic.id}"
                    )
                ]
            )

        if not botones:
            await query.edit_message_text(
                f"{chat.name}\n\nNo he encontrado ningún tema."
            )
            return

        botones.append(
            [
                InlineKeyboardButton(
                    "⬅️ Volver",
                    callback_data="volver_chats"
                )
            ]
        )

        await query.edit_message_text(
            f"📂 {chat.name}\n\n"
            "Este grupo utiliza temas.\n"
            "Selecciona el tema que quieres resumir:",
            reply_markup=InlineKeyboardMarkup(botones)
        )

        return

    if chat.unread_count == 0:
        await query.edit_message_text(f"{chat.name}\n\nNo tienes mensajes sin leer.")
        return

    print(f"Unread count: {chat.unread_count}")

    mensajes = []

    async for mensaje in telegram_client.iter_messages(
        chat.entity,
        limit=chat.unread_count
    ):
        mensajes.append(mensaje)
    print(f"Mensajes obtenidos antes del filtro: {len(mensajes)}")
    
    mensajes.reverse()

    mensajes = filtrar_mensajes(mensajes)

    texto = ""

    for cadaMensaje in mensajes:
        texto += cadaMensaje.message.strip() + "\n\n"

    tokens_estimados = estimar_tokens(texto)
   
    print(
        f"Mensajes sin leer: {chat.unread_count} | "
        f"Mensajes con texto: {len(mensajes)} | "
        f"Caracteres enviados: {len(texto)} | "
        f"Tokens estimados: {tokens_estimados}"
    )

    await query.edit_message_text(
        "Estoy preparando el resumen..."
    )

    if not GEMINI_ACTIVO:
        await query.edit_message_text(
            "⚠️ Gemini está desactivado temporalmente.\n\n"
            "La conversación se ha obtenido correctamente."
        )
        return

    resumen_json = await asyncio.to_thread(
        generar_resumen_inteligente,
        texto
    )

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
    await telegram_client.connect()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_error_handler(error_handler)

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
