import os
from dotenv import load_dotenv
from telethon import TelegramClient

load_dotenv()

api_id = int(os.getenv("API_ID"))
api_hash = os.getenv("API_HASH")

client = TelegramClient("mi_sesion_telegram", api_id, api_hash)


async def main():
    dialogs = await client.get_dialogs(limit=20)

    for i, dialog in enumerate(dialogs, start=1):
        print(f"{i}. {dialog.name} | ID: {dialog.id}")

    print("\nEscribe el número del chat que quieres analizar:")
    numero = int(input("> "))

    chat = dialogs[numero - 1]

    print(f"\nChat seleccionado: {chat.name}")
    print(f"ID: {chat.id}")
    print(f"Mensajes no leídos según Telegram: {chat.unread_count}")

    if chat.unread_count == 0:
        print("\nNo tienes mensajes sin leer.")
        return

    print("\nMensajes sin leer:\n")

    mensajes = []

    async for mensaje in client.iter_messages(
        chat.entity,
        limit=chat.unread_count
    ):
        if mensaje.text:
            mensajes.append(mensaje)

    mensajes.reverse()

    for mensaje in mensajes:
        print(mensaje.text)


with client:
    client.loop.run_until_complete(main())
