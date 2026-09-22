import os
import asyncio
import json
import traceback
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from telethon import TelegramClient
from telethon.tl import functions
from telethon.sessions import StringSession

import time
from openai import OpenAI

load_dotenv()

# Lista ampliada de modelos gratuitos en OpenRouter con rotación automática por saturación
MODELOS_OPENROUTER = [
"openrouter/free"
]

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

MAX_TOKENS_IA = 10000
IA_ACTIVA = True

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

openrouter_client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)


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

def consultar_ia(prompt):
    respuesta_texto = None

    # Recorre la lista de modelos gratuitos de OpenRouter uno a uno si fallan o se saturan
    for modelo in MODELOS_OPENROUTER:
        try:
            print(f"Intentando con OpenRouter ({modelo})...")
            completion = openrouter_client.chat.completions.create(
                model=modelo,
                messages=[{"role": "user", "content": prompt}],
                response_format={"type": "json_object"}
            )
            respuesta_texto = completion.choices[0].message.content
            if respuesta_texto:
                print(f"¡Éxito con el modelo {modelo}!")
                break
        except Exception as e:
            print(f"El modelo {modelo} falló o está saturado: {e}. Probando siguiente...")
            time.sleep(1)

    return respuesta_texto

def generar_resumen_parcial(texto):
  prompt = (
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
      "    {\n"
      '      "pregunta": "Pregunta",\n'
      '      "respuesta": "Respuesta o No se ha respondido en esta parte."\n'
      "    }\n"
      "  ]\n"
      "}\n\n"
      "CONVERSACIÓN:\n" + texto
  )

  respuesta_texto = consultar_ia(prompt)

  if respuesta_texto is None:
    return {
        "resumen": (
            "⚠️ Todos los modelos gratuitos de OpenRouter están experimentando alta demanda. Inténtalo de nuevo."
        ),
        "temas_principales": [],
        "decisiones": [],
        "preguntas_y_respuestas": [],
    }

  try:
    return json.loads(respuesta_texto)
  except json.JSONDecodeError:
    return {
        "resumen": respuesta_texto,
        "temas_principales": [],
        "decisiones": [],
        "preguntas_y_respuestas": [],
    }
    
def generar_resumen_final(resumenes_parciales):
  texto_resumenes = "\n\n--- SIGUIENTE BLOQUE ---\n\n".join(
      json.dumps(r, ensure_ascii=False) if isinstance(r, dict) else str(r)
      for r in resumenes_parciales
  )

  prompt = (
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
      "    {\n"
      '      "pregunta": "Pregunta",\n'
      '      "respuesta": "Respuesta o No se ha respondido."\n'
      "    }\n"
      "  ]\n"
      "}\n\n"
      "ANÁLISIS PARCIALES:\n" + texto_resumenes
  )

  respuesta_texto = consultar_ia(prompt)

  if respuesta_texto is None:
    return {
        "resumen": (
            "⚠️ Todos los modelos gratuitos de OpenRouter están experimentando alta demanda. Inténtalo de nuevo."
        ),
        "temas_principales": [],
        "decisiones": [],
        "preguntas_y_respuestas": [],
    }

  try:
    return json.loads(respuesta_texto)
  except json.JSONDecodeError:
    return {
        "resumen": respuesta_texto,
        "temas_principales": [],
        "decisiones": [],
        "preguntas_y_respuestas": [],
    }

def generar_resumen_inteligente(texto):
    tokens_estimados = estimar_tokens(texto)

    if tokens_estimados <= MAX_TOKENS_IA:
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
  prompt = (
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
      "    {\n"
      '      "pregunta": "Pregunta realizada",\n'
      '      "respuesta": "Respuesta encontrada o No se ha respondido."\n'
      "    }\n"
      "  ]\n"
      "}\n\n"
      "Si no hay información para una categoría, "
      "devuelve una lista vacía.\n\n"
      "No incluyas Markdown.\n"
      "No incluyas texto antes ni después del JSON.\n\n"
      "CONVERSACIÓN:\n" + texto
  )

  respuesta_texto = consultar_ia(prompt)

  if respuesta_texto is None:
    return {
        "temas_principales": [],
        "decisiones": [
            "⚠️ Todos los modelos gratuitos de OpenRouter están experimentando alta demanda. Inténtalo de nuevo."
        ],
        "preguntas_y_respuestas": [],
    }

  try:
    return json.loads(respuesta_texto)
  except json.JSONDecodeError:
    return {
        "temas_principales": [],
        "decisiones": [respuesta_texto],
        "preguntas_y_respuestas": [],
    }

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

        ultimo_id = resultado.messages[-1].id

        if ultimo_id == offset_id:
            break

        offset_id = ultimo_id

        if len(resultado.messages) < 100:
            break

    mensajes_unicos = {
        mensaje.id: mensaje
        for mensaje in mensajes
    }

    mensajes = list(mensajes_unicos.values())
    mensajes.sort(key=lambda mensaje: mensaje.id)

    return mensajes

async def seleccionar_chat(update, context):
    query = update.callback_query
    await query.answer()

    if query.data.startswith("topic:"):
        partes = query.data.split(":")

        chat_id = int(partes[1])
        topic_id = int(partes[2])

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

    mensajes = []

    async for mensaje in telegram_client.iter_messages(
        chat.entity,
        limit=chat.unread_count
    ):
        mensajes.append(mensaje)
    
    mensajes.reverse()
    mensajes = filtrar_mensajes(mensajes)

    texto = ""

    for cadaMensaje in mensajes:
        texto += cadaMensaje.message.strip() + "\n\n"

    await query.edit_message_text(
        "Estoy preparando el resumen..."
    )

    if not IA_ACTIVA:
        await query.edit_message_text(
            "⚠️ Los sistemas de IA están desactivados temporalmente.\n\n"
            "La conversación se ha obtenido correctamente."
        )
        return

    resumen_json = await asyncio.to_thread(
        generar_resumen_inteligente,
        texto
    )

    datos = resumen_json

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

    LIMITE_TELEGRAM = 4000 # Margen de seguridad por debajo de los 4096

    if len(mensaje) <= LIMITE_TELEGRAM:
        await query.edit_message_text(mensaje)
    else:
        # Divide el mensaje en partes según el límite
        fragmentos = [mensaje[i:i + LIMITE_TELEGRAM] for i in range(0, len(mensaje), LIMITE_TELEGRAM)]
        
        # El primer fragmento edita el texto previo de "Estoy preparando el resumen..."
        await query.edit_message_text(fragmentos[0])
        
        # Los siguientes fragmentos se envían como mensajes nuevos
        for fragmento in fragmentos[1:]:
            await context.bot.send_message(
                chat_id=update.effective_chat.id, 
                text=fragmento
            )


async def main():
    await telegram_client.connect()

    app = Application.builder().token(BOT_TOKEN).build()

    app.add_error_handler(error_handler)

    app.add_handler(CommandHandler("start", start))

    app.add_handler(CommandHandler("resumen", resumen))

    app.add_handler(CallbackQueryHandler(seleccionar_chat))

    print("Bot iniciado con soporte multimodelo gratuito de OpenRouter...")

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
