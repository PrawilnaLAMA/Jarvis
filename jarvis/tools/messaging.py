"""Wysyłanie wiadomości do kontaktów z ustawień – na Discordzie albo na Messengerze."""

from typing import Any

from jarvis.services.discord_client import DiscordError
from jarvis.services.inbox import APP_GENITIVE, APP_LOCATIVE, APP_NAMES
from jarvis.services.messenger import MessengerError
from jarvis.settings import MESSAGING_APPS, Contact, Settings, messenger_thread
from jarvis.tools.base import Tool, ToolContext, ToolError, params

MESSAGE_RULES = (
    "Treść jak od użytkownika: krótko, naturalnie, zawsze do jednej osoby (liczba pojedyncza, nawet przy kilku "
    "odbiorcach), bez imion, emotek i podpisu. Np. „zapytaj adama i natana czy chcą zagrać” → „Chcesz zagrać?”"
)


def _choose_app(ctx: ToolContext, contact: Contact, wanted: str | None) -> str | None:
    """Komunikator: wskazany przez użytkownika, inaczej ten, którym kontakt ostatnio pisał, inaczej pierwszy."""
    if wanted:
        return wanted if wanted in contact.apps else None
    last = ctx.inbox.last_app_of(contact.name)
    return last if last in contact.apps else contact.apps[0] if contact.apps else None


def send_message(ctx: ToolContext, args: dict[str, Any]) -> str:
    settings = ctx.settings.get()
    message = str(args.get("message", "")).strip()
    recipients = [str(r) for r in args.get("recipients") or []]
    wanted = args.get("app") if args.get("app") in MESSAGING_APPS else None
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
        app = _choose_app(ctx, contact, wanted)
        if not app:
            failed.append(f"{contact.display_name} (brak {APP_GENITIVE[wanted or 'discord']} w kontakcie)")
            continue
        try:
            if app == "discord":
                ctx.discord.send_message(contact.channel_id.strip(), message)
            else:
                ctx.messenger.send(messenger_thread(contact.messenger), message)
        except (DiscordError, MessengerError) as e:
            failed.append(f"{contact.display_name} ({e})")
            continue
        # komunikator mówimy tylko, gdy kontakt ma kilka – inaczej to oczywiste
        sent.append(f"{contact.display_name} {APP_LOCATIVE[app]}" if len(contact.apps) > 1 else contact.display_name)

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
    apps = [app for app in MESSAGING_APPS if any(app in c.apps for c in settings.contacts)]
    properties: dict[str, Any] = {
        "recipients": {"type": "array", "items": {"type": "string", "enum": names}, "minItems": 1},
        "message": {"type": "string", "description": MESSAGE_RULES},
    }
    if len(apps) > 1:
        properties["app"] = {"type": "string", "enum": apps, "description": "tylko gdy użytkownik powiedział, gdzie"}
    return [
        Tool(
            "send_message",
            f"Wysyła wiadomość ({' albo '.join(APP_NAMES[a] for a in apps)}) do jednego lub kilku kontaktów.",
            params(properties, ["recipients", "message"]),
            send_message,
        )
    ]
