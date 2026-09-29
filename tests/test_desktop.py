"""Geometria kulki na pulpicie (czyste funkcje – bez okien)."""

import math

import pytest

from jarvis.ui.desktop import cover_radius, ease_in_out, ease_out, fit_rect, placement

WORK = (0, 0, 1920, 1032)  # ekran 1080p bez paska zadań


def test_fit_rect_centers_and_keeps_inside_screen():
    assert fit_rect(960, 516, 1180, 760, WORK) == (370, 136, 1180, 760)
    x, y, w, h = fit_rect(1900, 1020, 1180, 760, WORK)  # kulka w prawym dolnym rogu
    assert (x + w, y + h) == (1920 - 16, 1032 - 16)
    second = (-1920, 0, 1536, 864)  # drugi monitor po lewej
    assert fit_rect(-2500, -500, 1180, 760, second)[:2] == (-1920 + 16, 16)
    assert fit_rect(-100, 900, 1180, 760, second)[:2] == (-384 - 16 - 1180, 864 - 16 - 760)


def test_fit_rect_shrinks_to_small_screen():
    assert fit_rect(400, 240, 1180, 760, (0, 0, 800, 480)) == (16, 16, 768, 448)


def test_placement_centers_window_on_the_orbs_screen():
    centered = (370, 136, 1180, 760)
    assert placement((960, 516), (1180, 760), WORK, 56) == centered
    assert placement((600, 300), (1180, 760), WORK, 56) == centered  # kulka obok środka – okno i tak na środku
    second = (-1920, 0, 1536, 816)  # kulka na drugim monitorze – okno na jego środku
    assert placement((-1150, 413), (1180, 760), second, 56) == (-1920 + 178, 28, 1180, 760)


def test_placement_follows_orb_far_from_center():
    # kulka w rogu nie zmieściłaby się w oknie na środku – okno staje wokół niej, na ekranie
    x, y, w, h = placement((1880, 60), (1180, 760), WORK, 56)
    assert (x + w, y) == (1920 - 16, 16) and x <= 1880 <= x + w and y <= 60 <= y + h


@pytest.mark.parametrize("cx, cy", [(0, 0), (413, 340), (1180, 760), (590, 380)])
def test_cover_radius_reaches_every_corner(cx, cy):
    r = cover_radius(cx, cy, 1180, 760)
    assert all(math.hypot(px - cx, py - cy) <= r for px in (0, 1180) for py in (0, 760))


def test_easing_bounds():
    assert ease_out(0) == 0 and ease_out(1) == 1 and ease_out(0.5) > 0.5
    assert ease_in_out(0) == 0 and ease_in_out(1) == 1 and ease_in_out(0.5) == 0.5 and ease_in_out(0.25) < 0.25
