import pytest

from jarvis.audio.speakable import speakable


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Dodałem trening o 18:00.", "Dodałem trening o osiemnastej."),
        ("Spotkanie od 9:30 do 11:00.", "Spotkanie od dziewiątej 30 do jedenastej."),
        ("Umówię cię na 15:00.", "Umówię cię na piętnastą."),
        ("Jest 7:05.", "Jest siódma 5."),
        ("Pociąg o 23:40 i o 2:10.", "Pociąg o dwudziestej trzeciej 40 i o drugiej 10."),
        ("o 13:00, a potem o 21:00", "o trzynastej, a potem o dwudziestej pierwszej"),
        ("W 2026 r. powstanie hotel, np. pod wodą.", "W 2026 roku powstanie hotel, na przykład pod wodą."),
        ("Bez godzin.", "Bez godzin."),
    ],
)
def test_speakable(text, expected):
    assert speakable(text) == expected


def test_score_like_values_are_not_times():
    assert speakable("Wygrali 3:2.") == "Wygrali 3:2."
    assert speakable("Stan 10:15:30.") == "Stan 10:15:30."
