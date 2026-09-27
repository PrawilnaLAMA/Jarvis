import json
from datetime import datetime

import pytest

from jarvis.assistant import Assistant, Interruption, build_context, clean_reply
from jarvis.conversation import Conversation
from jarvis.llm import LLMError
from jarvis.services.calendar_store import CalendarStore
from jarvis.services.discord_client import DiscordError
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
def env(tmp_path, bus):
    settings = SettingsStore(tmp_path / "settings.json")
    settings.update({"contacts": [
        {"name": "PIOTREK", "channel_id": "111111", "aliases": ["Piotr"]},
        {"name": "NATAN", "channel_id": "222222"},
    ]})
    conversation = Conversation(tmp_path / "conv.json", lambda: 12)
    ctx = ToolContext(
        settings=settings,
        bus=bus,
        calendar=CalendarStore(tmp_path / "events.json", bus),
        discord=FakeDiscord(),
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
    assistant, _ = make({"tool_calls": [call("send_discord_message", {"recipients": ["PIOTREK", "NATAN", "ANNA"],
                                                                        "message": "Spóźnię się."})]})
    reply = assistant.handle("napisz do piotrka, natana i anny, że się spóźnię")
    assert ctx.discord.sent == [("111111", "Spóźnię się.")]
    assert reply.startswith("Wysłałem do: Piotrek: „Spóźnię się.”.")
    assert "Natan (brak dostępu)" in reply and "ANNA (nie ma takiego kontaktu)" in reply


def test_informational_tool_gets_second_round(env):
    make, ctx, _, _ = env
    ctx.calendar.add({"desc": "Fryzjer", "date": "2025-11-04", "start": "15:00"})
    assistant, llm = make(
        {"content": "", "reasoning": "x", "tool_calls": [call("list_calendar_events", {"start_date": "2025-11-04"})]},
        {"content": "Jutro o piętnastej masz fryzjera."},
    )
    assert assistant.handle("co mam jutro") == "Jutro o piętnastej masz fryzjera."
    second = llm.requests[1]["messages"]
    assert second[-2]["tool_calls"][0]["function"]["name"] == "list_calendar_events"
    assert "reasoning" not in second[-2]
    assert second[-1] == {"role": "tool", "tool_call_id": "c1", "content": "Wydarzenia:\n- Fryzjer jutro o 15:00"}


def test_add_event_and_tool_error_is_spoken(env):
    make, ctx, _, _ = env
    assistant, _ = make(
        {"tool_calls": [call("add_calendar_event", {"desc": "trening", "days": ["Wednesday"], "start": "18:00"})]},
        {"tool_calls": [call("add_calendar_event", {"desc": "bez daty"})]},
    )
    reply = assistant.handle("dodaj trening w każdą środę o 18")
    assert reply == "Dodałem do kalendarza: trening co tydzień: środa o 18:00."
    assert assistant.handle("dodaj coś").startswith("Nie dodałem wydarzenia. Podaj datę")
    assert len(ctx.calendar.all_events()) == 1


def test_delete_event_fuzzy_and_ambiguous(env):
    make, ctx, _, _ = env
    ctx.calendar.add({"desc": "spotkanie z promotorem", "date": "2025-11-06"})
    ctx.calendar.add({"desc": "trening", "date": "2025-11-06"})
    ctx.calendar.add({"desc": "trening", "date": "2025-11-07"})
    assistant, _ = make(
        {"tool_calls": [call("delete_calendar_event", {"query": "promotor"})]},
        {"tool_calls": [call("delete_calendar_event", {"query": "trening"})]},
    )
    assert assistant.handle("usuń promotora") == "Usunąłem z kalendarza: spotkanie z promotorem w czwartek."
    assert assistant.handle("usuń trening").startswith("Pasuje kilka wydarzeń")
    assert len(ctx.calendar.all_events()) == 2


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
    context = build_context(NOW, "text", Interruption("Rzym został założony"))
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
    assert "send_discord_message" not in names
    assert {"play_youtube", "add_calendar_event", "stay_silent"} <= names


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
