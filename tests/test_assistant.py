import json
from datetime import datetime

import pytest

from jarvis.assistant import Assistant, Interruption, build_context, clean_reply
from jarvis.conversation import Conversation
from jarvis.llm import LLMError
from jarvis.services.discord_client import DiscordError
from jarvis.services.domownik_client import DomownikError
from jarvis.services.inbox import IncomingMessage
from jarvis.settings import Settings, SettingsStore
from jarvis.tools import ToolContext, build_tools

NOW = datetime(2025, 11, 3, 12, 0)  # poniedziałek


def call(name: str, args: dict, call_id: str = "c1") -> dict:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}


class FakeLLM:
    """Zwraca kolejne zaplanowane odpowiedzi i zapamiętuje zapytania."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def chat(self, messages, tools=None, **kwargs):
        self.requests.append({"messages": [dict(m) for m in messages], "tools": tools})
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


class FakeDiscord:
    def __init__(self, fail_for=()):
        self.sent = []
        self.fail_for = fail_for

    def send_message(self, channel_id, content):
        if channel_id in self.fail_for:
            raise DiscordError("brak dostępu")
        self.sent.append((channel_id, content))


@pytest.fixture
def env(tmp_path, bus, domownik, messenger, inbox):
    settings = SettingsStore(tmp_path / "settings.json")
    settings.update({"contacts": [
        {"name": "PIOTREK", "channel_id": "111111", "aliases": ["Piotr"]},
        {"name": "NATAN", "channel_id": "222222"},
    ]})
    conversation = Conversation(tmp_path / "conv.json", lambda: 12)
    ctx = ToolContext(
        settings=settings,
        bus=bus,
        domownik=domownik,
        discord=FakeDiscord(),
        messenger=messenger,
        inbox=inbox,
        conversation=conversation,
        open_url=lambda url: opened.append(url),
        http_get=lambda url: '..."videoId":"dQw4w9WgXcQ"...',
        run_command=lambda args: commands.append(args),
        clock=lambda: NOW,
    )
    opened: list[str] = []
    commands: list[list[str]] = []

    def make(*responses):
        llm = FakeLLM(*responses)
        return Assistant(llm, ctx, settings, bus, conversation, clock=lambda: NOW), llm

    return make, ctx, opened, commands


def test_plain_answer_is_cleaned_and_saved(env, recorder):
    make, ctx, _, _ = env
    assistant, llm = make({"content": "**Stolica** Polski to\n- Warszawa."})
    assert assistant.handle("jaka jest stolica polski") == "Stolica Polski to Warszawa."
    assert recorder.of("transcript") == [{"text": "jaka jest stolica polski", "source": "voice"}]
    assert recorder.of("reply")[0]["text"] == "Stolica Polski to Warszawa."
    assert ctx.conversation.messages()[-1] == {"role": "assistant", "content": "Stolica Polski to Warszawa."}
    assert llm.requests[0]["messages"][0]["role"] == "system"


def test_direct_tool_needs_single_llm_call(env):
    make, ctx, opened, _ = env
    assistant, llm = make({"tool_calls": [call("play_youtube", {"query": "despacito"})]})
    assert assistant.handle("puść despacito") == "Puszczam na YouTube: despacito."
    assert opened == ["https://www.youtube.com/watch?v=dQw4w9WgXcQ"]
    assert len(llm.requests) == 1


def test_discord_message_to_many_with_partial_failure(env):
    make, ctx, _, _ = env
    ctx.discord.fail_for = ("222222",)
    assistant, _ = make({"tool_calls": [call("send_message", {"recipients": ["PIOTREK", "NATAN", "ANNA"],
                                                                        "message": "Spóźnię się."})]})
    reply = assistant.handle("napisz do piotrka, natana i anny, że się spóźnię")
    assert ctx.discord.sent == [("111111", "Spóźnię się.")]
    assert reply.startswith("Wysłałem do: Piotrek: „Spóźnię się.”.")
    assert "Natan (brak dostępu)" in reply and "ANNA (nie ma takiego kontaktu)" in reply


def test_message_app_follows_last_incoming_message(env, spoken, recorder):
    make, ctx, _, _ = env
    contacts = [c.__dict__ for c in ctx.settings.get().contacts]
    ctx.settings.update({"contacts": [*contacts, {"name": "NATALIA", "channel_id": "333333",
                                                  "messenger": "https://www.messenger.com/e2ee/t/123456789/"}]})
    natalia = ctx.settings.get().contact_by_name("natalia")
    assistant, llm = make(
        {"tool_calls": [call("send_message", {"recipients": ["NATALIA"], "message": "Będę za 10 minut."})]},
        {"tool_calls": [call("send_message", {"recipients": ["NATALIA"], "message": "OK."})]},
        {"tool_calls": [call("send_message", {"recipients": ["PIOTREK"], "message": "Hej.", "app": "messenger"})]},
    )
    # bez wskazania komunikatora i bez rozmowy – pierwszy z kontaktu (Discord)
    assert assistant.handle("napisz natalii, że będę za 10 minut") == (
        "Wysłałem do: Natalia na Discordzie: „Będę za 10 minut.”."
    )
    assert ctx.discord.sent == [("333333", "Będę za 10 minut.")]

    ctx.inbox.receive("messenger", natalia, "Kupisz mleko?", read_aloud=True)
    assert spoken == ["Natalia pisze na Messengerze: Kupisz mleko?"]
    assert recorder.of("messenger.message") == [{"author": "Natalia", "content": "Kupisz mleko?", "contact": "NATALIA"}]
    assert assistant.handle("odpisz jej, że ok") == "Wysłałem do: Natalia na Messengerze: „OK.”."
    assert ctx.messenger.sent == [("e2ee/t/123456789", "OK.")]
    assert "od NATALIA (Messenger" in llm.requests[1]["messages"][-1]["content"]
    send_tool = next(t["function"] for t in llm.requests[1]["tools"] if t["function"]["name"] == "send_message")
    assert send_tool["parameters"]["properties"]["app"]["enum"] == ["discord", "messenger"]

    assert assistant.handle("napisz piotrkowi na messengerze hej") == (
        "Nie udało się wysłać do: Piotrek (brak Messengera w kontakcie)."
    )


def test_informational_tool_gets_second_round(env):
    make, ctx, _, _ = env
    ctx.domownik.agenda_data = {"days": [{"date": "2025-11-04", "weekday": "wtorek", "items": [
        {"title": "Odkurzanie", "assignees": ["leon"], "kto_label": "Leon", "done": False},
    ]}], "overdue": [], "grafik": {}}
    assistant, llm = make(
        {"content": "", "reasoning": "x", "tool_calls": [call("house_agenda", {"start_date": "2025-11-04"})]},
        {"content": "Jutro masz odkurzanie."},
    )
    assert assistant.handle("co mam jutro") == "Jutro masz odkurzanie."
    second = llm.requests[1]["messages"]
    assert second[-2]["tool_calls"][0]["function"]["name"] == "house_agenda"
    assert "reasoning" not in second[-2]
    assert second[-1] == {"role": "tool", "tool_call_id": "c1", "content": "wtorek 2025-11-04 – twoje: Odkurzanie"}


def test_add_chore_and_unreachable_domownik_is_spoken(env):
    make, ctx, _, _ = env
    assistant, _ = make(
        {"tool_calls": [call("chore_add", {"title": "Trening", "repeat": "tygodniowo", "weekdays": ["Wednesday"],
                                           "who": "ja"})]},
        {"tool_calls": [call("chore_add", {"title": "Dentysta 14:00", "start_date": "2025-11-07"})]},
    )
    reply = assistant.handle("dodaj trening w każdą środę")
    assert reply == "Dodałem do kalendarza: Trening, w każdą środę, dla ciebie."
    assert ctx.domownik.added[0]["repeat"] == {"type": "tygodniowo", "weekdays": [2]}
    assert ctx.domownik.added[0]["assignees"] == ["leon"]
    ctx.domownik.error = DomownikError("Domownik nie odpowiada – czy jego serwer jest uruchomiony?")
    assert assistant.handle("dodaj dentystę w piątek o 14").startswith("Domownik nie odpowiada")


def test_delete_chore_fuzzy_and_ambiguous(env):
    make, ctx, _, _ = env
    ctx.domownik.chores_data = [
        {"id": "a", "title": "Spotkanie z promotorem", "repeat_label": "jednorazowo"},
        {"id": "b", "title": "Podlać kwiaty w salonie", "repeat_label": "co 3 dni"},
        {"id": "c", "title": "Podlać kwiaty w sypialni", "repeat_label": "co 5 dni"},
    ]
    assistant, _ = make(
        {"tool_calls": [call("chore_delete", {"query": "promotor"})]},
        {"tool_calls": [call("chore_delete", {"query": "podlać kwiaty"})]},
    )
    assert assistant.handle("usuń promotora") == "Usunąłem z kalendarza: Spotkanie z promotorem."
    assert assistant.handle("usuń podlewanie kwiatów").startswith("Pasuje kilka obowiązków")
    assert ctx.domownik.deleted == ["a"]


def test_stay_silent_returns_none(env, recorder):
    make, ctx, _, _ = env
    assistant, _ = make({"tool_calls": [call("stay_silent", {})]})
    assert assistant.handle("dobra, cisza") is None
    assert recorder.of("reply") == []
    assert ctx.conversation.messages() == [{"role": "user", "content": "dobra, cisza"}]


def test_shutdown_uses_delay(env):
    make, ctx, _, commands = env
    assistant, _ = make({"tool_calls": [call("shutdown_computer", {"delay_seconds": 1})]})
    reply = assistant.handle("wyłącz komputer")
    assert "anuluj wyłączenie" in reply
    assert commands and ("10" in commands[0] or "+1" in commands[0])  # minimum 10 s


def test_llm_error_is_reported(env, recorder):
    make, _, _, _ = env
    assistant, _ = make(LLMError("Przekroczono limit zapytań."))
    assert assistant.handle("cześć") == "Przekroczono limit zapytań."
    assert recorder.of("notice")[0]["level"] == "error"


def test_unknown_tool_and_bad_json_do_not_crash(env):
    make, _, _, _ = env
    bad = {"id": "c2", "function": {"name": "search_web", "arguments": "{nie json"}}
    assistant, llm = make({"tool_calls": [call("hack", {}), bad]}, {"content": "Nie mogę tego zrobić."})
    assert assistant.handle("coś") == "Nie mogę tego zrobić."


def test_context_has_dates_and_interruption():
    incoming = IncomingMessage("discord", "PIOTREK", "Piotrek", "gramy?", NOW.timestamp() - 180)
    context = build_context(NOW, "text", Interruption("Rzym został założony"), incoming)
    assert "Ostatnia wiadomość do użytkownika: od PIOTREK (Discord, 3 min temu)." in context
    assert "gramy" not in context  # treść cudzej wiadomości nie trafia do modelu – słucha tylko użytkownika
    assert "Rzym został założony" in context
    assert "Teraz: poniedziałek 2025-11-03, godz. 12:00" in context
    assert "wtorek 2025-11-04 (jutro)" in context and "piątek 2025-11-07" in context
    assert "klawiaturze" in context


def test_system_prompt_is_static_and_context_goes_to_user_message(env):
    make, _, _, _ = env
    assistant, llm = make({"content": "a"}, {"content": "b"})
    assistant.handle("pierwsze")
    assistant.handle("drugie")
    first, second = (r["messages"] for r in llm.requests)
    assert first[0] == second[0]  # stały prefiks → cache po stronie Groq
    assert "Inne nazwy kontaktów: PIOTREK = Piotr." in first[0]["content"]
    assert second[-1]["content"].startswith("<kontekst>") and second[-1]["content"].endswith("\ndrugie")
    assert second[1] == {"role": "user", "content": "pierwsze"}  # w historii bez kontekstu


def test_tools_without_contacts_hide_discord():
    names = {t.name for t in build_tools(Settings())}
    assert "send_message" not in names
    assert {"play_youtube", "house_agenda", "chore_add", "shopping_update", "stay_silent"} <= names


def test_clean_reply_links():
    assert clean_reply("Zobacz [stronę](http://x.pl)  tutaj") == "Zobacz stronę tutaj"


def test_conversation_marks_interruption(tmp_path):
    conv = Conversation(tmp_path / "c.json", lambda: 12)
    conv.add("assistant", "stara odpowiedź")  # nie może zaczynać kontekstu
    conv.add("user", "opowiedz o Rzymie")
    conv.add("assistant", "Rzym został założony w 753 roku przed naszą erą i przez wieki...")
    conv.mark_interrupted("Rzym został założony")
    assert conv.messages() == [
        {"role": "user", "content": "opowiedz o Rzymie"},
        {"role": "assistant", "content": "Rzym został założony… [przerwano]"},
    ]
    assert Conversation(tmp_path / "c.json", lambda: 1).messages() == []
