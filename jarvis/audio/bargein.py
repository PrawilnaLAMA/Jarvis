"""Wykrywanie, że użytkownik zaczął mówić, gdy Jarvis mówi przez głośniki (przerywanie).

Mikrofon słyszy też głos Jarvisa (echo), więc sama detekcja mowy nie wystarczy:
1. EchoGate uczy się, jak głośno echo dociera do mikrofonu (stosunek mikrofon/wyjście),
   i zgłasza kandydata, gdy mowa jest wyraźnie głośniejsza od spodziewanego echa.
   Jest celowo czuły – fałszywe alarmy odsiewa krok 2 kosztem chwilowego ściszenia.
2. DuckTest: Jarvis na chwilę się ścisza (-16 dB). Echo ścisza się razem z nim, a głos
   użytkownika nie – po ściszeniu porównujemy mikrofon z tym, ile echa powinno zostać.
   Wynik niejednoznaczny traktujemy jak echo (przy głośnym echu transkrypcja bywa halucynacją).
3. Transkrypcja po przerwaniu jest jeszcze porównywana z tym, co mówił Jarvis
   (transcript.is_echo) – na własne słowa nie odpowiadamy.

Przy bardzo głośnych głośnikach (echo głośniejsze od użytkownika) niezawodnie przerywa „Hej Jarvis”.
"""

from collections import deque
from dataclasses import dataclass, field

import numpy as np

DUCK_GAIN = 0.15  # ok. -16 dB
DEFAULT_COUPLING = 0.6  # zanim się nauczymy – ostrożne założenie, że echo jest dość głośne
ECHO_MARGIN = 1.4  # o ile głośniejsza od spodziewanego echa musi być mowa
MIN_SPEECH_LEVEL = 0.01
CANDIDATE_FRAMES = 3  # 3 × 80 ms = 240 ms mowy
MIN_OUTPUT_FOR_LEARNING = 0.005
REFERENCE_FRAMES = 3  # echo dociera z opóźnieniem – odniesieniem jest średnia z ostatnich 240 ms
COUPLING_PERCENTILE = 50  # mediana: odporna na ramki, w których użytkownik mówi ciszej niż próg
MIN_LEARNED_FRAMES = 12  # zanim poznamy poziom echa (~1 s mowy Jarvisa), przerywa tylko „Hej Jarvis”


@dataclass
class EchoGate:
    ratios: deque[float] = field(default_factory=lambda: deque(maxlen=150))
    outputs: deque[float] = field(default_factory=lambda: deque(maxlen=REFERENCE_FRAMES))
    consecutive: int = 0
    margin: float = ECHO_MARGIN

    @property
    def coupling(self) -> float:
        """Typowy stosunek echa w mikrofonie do głośności wyjścia."""
        if len(self.ratios) < 8:
            return DEFAULT_COUPLING
        return float(np.percentile(self.ratios, COUPLING_PERCENTILE))

    @property
    def reference(self) -> float:
        return sum(self.outputs) / len(self.outputs) if self.outputs else 0.0

    def threshold(self, noise_floor: float) -> float:
        return max(MIN_SPEECH_LEVEL, noise_floor * 3, self.coupling * self.reference * self.margin)

    @property
    def learned(self) -> bool:
        return len(self.ratios) >= MIN_LEARNED_FRAMES

    def update(self, mic_level: float, vad_prob: float, output_level: float, noise_floor: float) -> bool:
        """Przetwarza ramkę; True = prawdopodobnie użytkownik zaczął mówić."""
        self.outputs.append(output_level)
        is_voice = self.learned and vad_prob >= 0.5 and mic_level > self.threshold(noise_floor)
        if self.reference > MIN_OUTPUT_FOR_LEARNING and not is_voice:
            self.ratios.append(mic_level / self.reference)
        self.consecutive = self.consecutive + 1 if is_voice else 0
        return self.consecutive >= CANDIDATE_FRAMES

    def reset_candidate(self) -> None:
        self.consecutive = 0

    def penalize(self) -> None:
        """Po fałszywym alarmie (to jednak było echo) wymagamy wyraźniejszej mowy."""
        self.margin = min(self.margin * 1.25, ECHO_MARGIN * 3)
        self.consecutive = 0


@dataclass
class DuckTest:
    """Po ściszeniu Jarvisa: czy w mikrofonie zostało więcej, niż wynosi spodziewane echo?"""

    coupling: float
    noise_floor: float
    # rampa ściszenia (~50 ms) + opóźnienie echa (bufory audio, zwykle 100–200 ms)
    settle_frames: int = 3
    measure_frames: int = 2
    mic: list[float] = field(default_factory=list)
    out: list[float] = field(default_factory=list)
    _skipped: int = 0

    def add(self, mic_level: float, output_level: float) -> str | None:
        """Zwraca None (jeszcze mierzymy) albo werdykt: user | echo | uncertain."""
        if self._skipped < self.settle_frames:
            self._skipped += 1
            return None
        self.mic.append(mic_level)
        self.out.append(output_level)
        if len(self.mic) < self.measure_frames:
            return None
        return classify_duck(max(self.mic), self.coupling * max(self.out), self.noise_floor)


def classify_duck(mic_level: float, expected_echo: float, noise_floor: float) -> str:
    floor = max(MIN_SPEECH_LEVEL, noise_floor * 3)
    if mic_level >= max(floor, expected_echo * 4):
        return "user"  # po ściszeniu Jarvisa w mikrofonie wciąż jest wyraźny głos → mówi człowiek
    if mic_level <= max(floor, expected_echo * 1.5):
        return "echo"  # zostało tyle, ile powinno zostać ze ściszonego Jarvisa
    return "uncertain"
