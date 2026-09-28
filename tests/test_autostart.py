"""Autostart z Windowsem – na osobnym kluczu testowym w HKCU, nigdy na prawdziwym …\\Run."""

import contextlib
import sys

import pytest

from jarvis import autostart

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="autostart tylko w Windowsie")


@pytest.fixture
def test_key(monkeypatch):
    import winreg

    key = r"Software\JarvisTest\Run"
    monkeypatch.setattr(autostart, "RUN_KEY", key)
    yield key
    for path in (key, r"Software\JarvisTest"):
        with contextlib.suppress(FileNotFoundError):
            winreg.DeleteKey(winreg.HKEY_CURRENT_USER, path)


def test_enable_disable(test_key):
    assert autostart.status() == {"supported": True, "enabled": False}
    autostart.set_enabled(True)
    assert autostart.is_enabled() and autostart._current() == autostart.command()
    assert "pythonw.exe" in autostart.command() and autostart.command().endswith('jarvis.pyw"')
    autostart.set_enabled(False)
    autostart.set_enabled(False)  # brak wpisu to nie błąd
    assert not autostart.is_enabled()


def test_refresh_fixes_stale_path_only_when_enabled(test_key):
    import winreg

    autostart.refresh()
    assert not autostart.is_enabled()  # wyłączonego nie włączamy
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, test_key) as key:
        winreg.SetValueEx(key, autostart.NAME, 0, winreg.REG_SZ, r'"C:\stary\pythonw.exe" "C:\stary\jarvis.pyw"')
    autostart.refresh()
    assert autostart._current() == autostart.command()
