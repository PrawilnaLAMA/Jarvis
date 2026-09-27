PY ?= python3
VENV ?= .venv

.PHONY: run browser text test lint pi-setup pi-run

run:  ## Jarvis w oknie
	$(PY) -m jarvis

browser:  ## interfejs w przeglądarce zamiast okna
	$(PY) -m jarvis --browser

text:  ## bez mikrofonu i dźwięku (tylko komendy wpisywane)
	$(PY) -m jarvis --no-voice

test:
	$(PY) -m pytest

lint:
	$(PY) -m ruff check .

# Raspberry Pi 4/5 z 64-bitowym Raspberry Pi OS i ekranem.
# GTK/WebKit (okno pywebview) pochodzą z systemu, dlatego venv widzi pakiety systemowe.
# openWakeWord instalujemy bez zależności: jego tflite-runtime nie jest potrzebny (używamy onnx),
# a na nowszych wersjach Pythona nie ma dla niego paczek.
pi-setup:
	sudo apt-get install -y python3-venv python3-gi python3-gi-cairo gir1.2-gtk-3.0 gir1.2-webkit2-4.1 libportaudio2 chromium
	python3 -m venv --system-site-packages $(VENV)
	$(VENV)/bin/pip install $$(grep -v '^openwakeword' requirements.txt)
	$(VENV)/bin/pip install --no-deps openwakeword
	$(VENV)/bin/pip install scipy scikit-learn tqdm

pi-run:
	$(VENV)/bin/python -m jarvis --fullscreen
