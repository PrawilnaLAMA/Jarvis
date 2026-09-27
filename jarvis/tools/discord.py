"""Wysyłanie wiadomości na Discordzie do kontaktów z ustawień."""

from typing import Any

from jarvis.services.discord_client import DiscordError
from jarvis.settings import Settings
from jarvis.tools.base import Tool, ToolContext, ToolError, params

MESSAGE_RULES = (
    "Treść jak od użytkownika: krótko, naturalnie, zawsze do jednej osoby (liczba pojedyncza, nawet przy kilku "
    "odbiorcach), bez imion, emotek i podpisu. Np. „zapytaj adama i natana czy chcą zagrać” → „Chcesz zagrać?”"
)


def send_discord_message(ctx: ToolContext, args: dict[str, Any]) -> str:
    settings = ctx.settings.get()
    message = str(args.get("message", "")).strip()
    recipients = [str(r) for r in args.get("recipients") or []]
    if not message:
        raise ToolError("Nie wiem, co mam napisać.")
    if not recipients:
        raise ToolError("Nie wiem, do kogo mam napisać.")

    sent, failed = [], []
    for name in recipients:
        contact = settings.contact_by_name(name)
        if not contact:
            failed.append(f"{name} (nie ma takiego kontaktu)")
            continue
        try:
            ctx.discord.send_message(contact.channel_id, message)
            sent.append(contact.display_name)
        except DiscordError as e:
            failed.append(f"{contact.display_name} ({e})")

    parts = []
    if sent:
        parts.append(f"Wysłałem do: {', '.join(sent)}: „{message}”.")
    if failed:
        parts.append(f"Nie udało się wysłać do: {', '.join(failed)}.")
    return " ".join(parts)


def tools(settings: Settings) -> list[Tool]:
    if not settings.contacts:
        return []
    names = [c.name for c in settings.contacts]
    return [
        Tool(
            "send_discord_message",
            "Wysyła wiadomość na Discordzie do jednego lub kilku kontaktów.",
            params(
                {
                    "recipients": {"type": "array", "items": {"type": "string", "enum": names}, "minItems": 1},
                    "message": {"type": "string", "description": MESSAGE_RULES},
                },
                ["recipients", "message"],
            ),
            send_discord_message,
        )
    ]
