from PIL import Image, ImageDraw

from engine.cache.position_cache import PositionCache
from engine.models.grounding import _decode_mask, mask_centroid
from engine.models.grid import GridGrounder, cells_box, parse_cell
from engine.screen.capture import Shot, fit
from engine.sdk.questions import Row
from engine.sdk.results import export_data, make_table
from engine.store.db import DB
from engine.teach.compiler import group_steps


def ui_image(offset=0):
    img = Image.new("RGB", (1600, 1000), (250, 250, 250))
    d = ImageDraw.Draw(img)
    d.rectangle([400 + offset, 300, 560 + offset, 350], fill=(30, 100, 220))
    d.text((420 + offset, 315), "Save", fill=(255, 255, 255))
    return img


def test_retina_scale_mapping():
    shot = Shot(image=Image.new("RGB", (2880, 1800)), scale=2.0)
    assert shot.to_logical(1000, 500) == (500, 250)
    assert shot.box_to_logical([100, 200, 300, 400]) == [50, 100, 150, 200]


def test_fit_downscales_to_long_edge():
    small, f = fit(Image.new("RGB", (2880, 1800)), 1280)
    assert small.size == (1280, 800) and f == 2.25


def test_grid_cells_parse_and_map_to_pixels():
    assert parse_cell("C3", 8, 6) == (2, 2)
    assert parse_cell(" b-2 ", 8, 6) == (1, 1)
    assert parse_cell("Z9", 8, 6) is None and parse_cell("", 8, 6) is None
    zone = [100, 0, 900, 600]  # 8x6 grid -> 100x100 cells
    assert cells_box([(1, 1), (2, 1)], zone, 8, 6) == [200, 100, 400, 200]
    assert cells_box([(0, 0)], zone, 8, 6, margin=1) == [100, 0, 300, 200]  # margin is clipped at the edge


def test_grid_grounder_zooms_in_on_the_named_element(monkeypatch):
    # A 1600x1200 screen with a button at (500-620, 420-460). The scripted "model" answers each pass with the
    # cells the button really covers, so the box should tighten pass by pass around it.
    target = [500, 420, 620, 460]
    views = []

    def fake_ask(self, img, phrase, cols, rows, first):
        zone = views[-1] if views else [0, 0, 1600, 1200]
        cw, ch = (zone[2] - zone[0]) / cols, (zone[3] - zone[1]) / rows
        cells = [f"{chr(65 + c)}{r + 1}" for c in range(cols) for r in range(rows)
                 if zone[0] + c * cw < target[2] and zone[0] + (c + 1) * cw > target[0]
                 and zone[1] + r * ch < target[3] and zone[1] + (r + 1) * ch > target[1]]
        cx, cy = (target[0] + target[2]) / 2, (target[1] + target[3]) / 2
        center = f"{chr(65 + int((cx - zone[0]) // cw))}{int((cy - zone[1]) // ch) + 1}"
        views.append(cells_box([parse_cell(c, cols, rows) for c in cells], zone, cols, rows, margin=1))
        return {"found": True, "cells": cells, "center": center}

    monkeypatch.setattr(GridGrounder, "_ask", fake_ask)
    g = GridGrounder(client=None).locate(Image.new("RGB", (1600, 1200)), "Save button")
    assert g.found
    assert target[0] <= g.point[0] <= target[2] and target[1] <= g.point[1] <= target[3]
    # Tighter than the first pass (two 200x200 cells); cell edges rarely line up with the element, so not exact.
    assert (g.box[2] - g.box[0]) <= 300 and (g.box[3] - g.box[1]) <= 100


def test_grid_grounder_reports_missing(monkeypatch):
    monkeypatch.setattr(GridGrounder, "_ask", lambda *a, **k: {"found": False, "reason": "no such button"})
    g = GridGrounder(client=None).locate(Image.new("RGB", (800, 600)), "Ghost button")
    assert not g.found and g.reason == "no such button"


def test_cache_hit_and_patch_mismatch(tmp_path):
    cache = PositionCache(DB(tmp_path / "c.db"))
    img = ui_image()
    cache.put("App|Win", img, "Save button", [400, 300, 560, 350])
    hit = cache.lookup("App|Win", img, "save   BUTTON")
    assert hit and hit.box == [400, 300, 560, 350]
    # The button moved: the pixels at the cached spot no longer match -> miss.
    assert cache.lookup("App|Win", ui_image(offset=300), "Save button") is None
    assert cache.lookup("Other|Win", img, "Save button") is None


def test_row_lookup_is_forgiving():
    r = Row({"Customer Name": "Acme", "Amount ($)": "12"})
    assert r["customer_name"] == "Acme"
    assert r["amount"] == "12"


def test_exports(tmp_path, monkeypatch):
    from engine.config import config

    monkeypatch.setattr(config, "exports_dir", tmp_path)
    rows = [{"name": "Acme", "amount": "1"}, {"name": "Globex", "amount": "2"}]
    for fmt in ("csv", "json", "md", "xlsx"):
        path = export_data(rows, fmt, "t")
        assert path.endswith(fmt)
    assert make_table(rows)["columns"] == ["name", "amount"]


def test_mask_decoding_and_centroid():
    m = _decode_mask([[10, 10], [30, 10], [30, 30], [10, 30]], (100, 100))
    cx, cy = mask_centroid(m)
    assert abs(cx - 20.5) < 2 and abs(cy - 20.5) < 2


def test_teach_grouping():
    ev = [
        {"type": "click", "t": 1.0, "x": 10, "y": 10},
        {"type": "char", "t": 1.5, "char": "A"},
        {"type": "char", "t": 1.6, "char": "c"},
        {"type": "key", "t": 1.7, "key": "backspace"},
        {"type": "char", "t": 1.8, "char": "x"},
        {"type": "key", "t": 2.0, "key": "enter"},
        {"type": "click", "t": 3.0, "x": 50, "y": 50},
        {"type": "click", "t": 3.2, "x": 51, "y": 50},
        {"type": "hotkey", "t": 4.0, "keys": ["cmd", "s"]},
    ]
    steps = group_steps(ev)
    assert [s["kind"] for s in steps] == ["click", "type", "press", "double_click", "hotkey"]
    assert steps[1]["text"] == "Ax"


def test_small_ui_change_counts_as_change():
    from engine.screen.fingerprint import changed_pixels, sig_changed_pixels, signature

    before = ui_image()
    after = before.copy()
    ImageDraw.Draw(after).rectangle([700, 600, 716, 616], fill=(30, 100, 220))  # a checkbox gets ticked
    region = [640, 540, 780, 680]
    assert changed_pixels(before, before) == 0
    assert sig_changed_pixels(signature(before, region), signature(before, region)) == 0
    assert sig_changed_pixels(signature(before, region), signature(after, region)) >= 3


def test_teach_compile_only_writes_a_valid_script(tmp_path):
    from engine.cache.position_cache import PositionCache
    from engine.models.fake import FakeGrounder, FakePlanner, FakeVision
    from engine.models import Models
    from engine.teach.compiler import compile_recording

    img = ui_image()
    before = tmp_path / "click0.jpg"
    frame = tmp_path / "frame0.jpg"
    img.save(before)
    img.save(frame)
    meta = {
        "scale": 1.0,
        "frames": [[5.0, str(frame)]],
        "events": [
            {"type": "click", "t": 1.0, "x": 480, "y": 325, "window": "App|Win", "before": str(before), "scale": 1.0},
            {"type": "char", "t": 1.5, "char": "h"},
            {"type": "char", "t": 1.6, "char": "i"},
            {"type": "key", "t": 2.0, "key": "enter"},
        ],
    }
    events = []
    grounder = FakeGrounder()
    grounder.locate = lambda *a, **k: (_ for _ in ()).throw(AssertionError("teach should not ground elements"))
    out = compile_recording(meta, "greet", "", Models(FakePlanner(), FakeVision(), grounder, None),
                            lambda t, **d: events.append(t))
    assert out["problems"] == []
    assert out["script"].startswith("INPUTS = {}")  # it only writes the script (with its header)
    assert [s["kind"] for s in out["steps"]] == ["click", "type", "press"]
    assert "teach_step" in events


class _StubGrounder:
    def __init__(self, label, found):
        self.label, self.found, self.calls = label, found, 0

    def locate(self, img, phrase):
        from engine.models.grounding import Grounded
        self.calls += 1
        if self.found:
            return Grounded(box=[10, 10, 50, 30], point=(30, 20))
        return Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False, reason="not seen")


def test_router_tries_sam_then_grid_and_switches_after_strikes():
    from engine.models.routing import SAM_STRIKES, GroundingRouter
    sam, grid = _StubGrounder("SAM 3.1", False), _StubGrounder("Spark grid", True)
    r = GroundingRouter(sam, grid)
    img = Image.new("RGB", (100, 100))
    g = r.locate(img, "Save button")
    assert g.found and g.label == "Spark grid" and sam.calls == 1 and grid.calls == 1
    for _ in range(SAM_STRIKES - 1):
        r.locate(img, "Save button")
    assert r.label == "Spark grid"  # SAM missed 3 times: grid goes first now
    r.locate(img, "Save button")
    assert sam.calls == SAM_STRIKES  # and SAM is no longer tried while the grid succeeds
    r.reset()
    assert r.mode == "auto" and r.label == "SAM 3.1"


def test_router_pinned_modes_and_combined_reason():
    import pytest
    from engine.models.routing import GroundingRouter
    sam, grid = _StubGrounder("SAM 3.1", False), _StubGrounder("Spark grid", False)
    r = GroundingRouter(sam, grid)
    g = r.locate(Image.new("RGB", (100, 100)), "Ghost")
    assert not g.found and "SAM 3.1: not seen" in g.reason and "Spark grid: not seen" in g.reason
    r.set_mode("sam")
    r.locate(Image.new("RGB", (100, 100)), "Ghost")
    assert grid.calls == 1  # pinned to SAM: no grid fallback
    with pytest.raises(ValueError):
        GroundingRouter(sam=None, grid=grid).set_mode("sam")


def test_use_grounding_from_a_script(screen, agent_factory):
    from engine.models.routing import GroundingRouter
    agent, host = agent_factory()
    sam, grid = _StubGrounder("SAM 3.1", True), _StubGrounder("Spark grid", True)
    agent.models.grounder = GroundingRouter(sam, grid)
    out = agent.run_task("pin grid", 'use_grounding("grid")\nclick("New Invoice button")\nclick("Save button")')
    assert out["status"] == "succeeded"
    assert grid.calls == 2 and sam.calls == 0
    agent.run_task("next run", 'click("Reset button")')
    assert sam.calls == 1  # the pin lasted only for its run


def test_cache_replays_the_found_click_point_not_the_box_centre(tmp_path):
    cache = PositionCache(DB(tmp_path / "c.db"))
    img = ui_image()
    # A loose box (grid cells overshoot) whose centre is not on the element; the click point is.
    cache.put("App|Win", img, "Save button", [400, 300, 900, 350], point=(450, 325))
    hit = cache.lookup("App|Win", img, "Save button")
    assert hit and hit.point == (450, 325)


def test_screenshots_crop_to_the_app_and_clicks_map_back(screen, agent_factory, monkeypatch):
    from engine.screen import windows

    # The window starts at (50, 50) so the fake screen's change marker (top-left corner) stays inside the crop.
    monkeypatch.setattr(windows, "app_window_bounds", lambda app: (50, 50, 900, 700) if app == "Invoices" else None)
    agent, _ = agent_factory()
    out = agent.run_task("scoped", 'open_app("Invoices")\nclick("New Invoice button")')
    assert out["status"] == "succeeded"
    move = [i for i in screen.inputs if i[0] in ("click", "move")][-1]
    x, y = move[1][0], move[1][1]
    assert 50 <= x <= 950 and 50 <= y <= 750  # inside the app window, in screen coordinates


def test_planner_must_say_which_app():
    from engine.runner.validate import scope_problems

    assert scope_problems('click("Save button")')  # no app named
    assert not scope_problems('open_app("Discord")\nclick("Save button")')
    assert not scope_problems('open_url("https://x.io")\nclick("Save")')
    assert scope_problems('x = 1\ntype_text("hi")\nopen_app("Notes")')


def test_cache_survives_a_moved_window_but_not_a_resized_one(tmp_path):
    cache = PositionCache(DB(tmp_path / "c.db"))
    window = ui_image().crop((200, 150, 1400, 900))  # the app's window, as the agent sees it
    cache.put("App|Win", window, "Save button", [200, 150, 360, 200], point=(280, 175))
    # Same window elsewhere on screen: the cropped image is identical, coordinates are window-relative.
    assert cache.lookup("App|Win", window.copy(), "Save button").point == (280, 175)
    resized = ui_image().crop((200, 150, 1300, 900))  # 100 px narrower: layout may have reflowed
    assert cache.lookup("App|Win", resized, "Save button") is None
