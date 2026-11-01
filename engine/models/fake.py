"""Deterministic offline stand-ins for every model role (AGENT_FAKE_MODELS=1 and tests).

AGENT_FAKE_FAIL="Save button" makes the first grounding of any target containing that text fail,
so the healing path (red line -> rewrite -> resume) can be demoed without API access.
"""
from __future__ import annotations

import ast
import hashlib
import os

from PIL import Image, ImageDraw

from .grounding import Grounded


def _meter(role: str, seconds: float, cost: float):
    """Simulated metering so the metrics panel and per-run chart work offline (no real sleeping)."""
    from ..sdk.context import current_metrics

    current_metrics().record_call(role, seconds, 900, 120, cost)

DEMO_SCRIPT = '''INPUTS = {}
OUTPUTS = {"invoices_created": "int: number of invoices created"}

open_app("Invoices")
rows = read_table("orders table")
for row in progress.pending(rows):
    click("New Invoice button", expect="empty invoice form is open")
    type_into("Customer field", row["name"])
    type_into("Amount field", row["amount"])
    click("Save button", confirm=True, expect="invoice saved message")
    progress.done(row)
checkpoint("invoices created")
show(summarize("invoices created this run"))
output(invoices_created=len(rows))
'''


def _spot(target: str, size: tuple[int, int]) -> list[int]:
    h = int(hashlib.md5(target.lower().encode()).hexdigest(), 16)
    w, ht = size
    cx = int(w * (0.3 + (h % 400) / 1000))
    cy = int(ht * (0.3 + ((h >> 10) % 400) / 1000))
    bw, bh = max(60, w // 16), max(24, ht // 40)
    return [cx - bw // 2, cy - bh // 2, cx + bw // 2, cy + bh // 2]


class FakeVision:
    def check(self, img, condition, prev=None):
        _meter("vision", 1.1, 0.0012)
        return {"result": True, "reason": "fake", "prev_expect_met": True if prev else None, "observation": ""}

    def ask(self, img, question, prev=None):
        _meter("vision", 1.3, 0.0015)
        return {"answer": f"(fake answer to: {question})", "prev_expect_met": True if prev else None, "observation": ""}

    def read_text(self, img):
        _meter("vision", 1.2, 0.0014)
        return "Fake text read from the screen"

    def read_table(self, img, target, columns=None):
        _meter("vision", 2.4, 0.004)
        return {
            "columns": ["name", "amount"],
            "rows": [["Acme Corp", "1200.00"], ["Globex", "860.50"], ["Initech", "455.25"]],
        }

    def reread_columns(self, img, columns):
        return []

    def summarize(self, instruction, data, img=None):
        _meter("vision", 1.8, 0.002)
        return ("Created **3 invoices** this run:\n\n"
                "- Acme Corp: $1,200.00\n- Globex: $860.50\n- Initech: $455.25\n\n"
                "Total invoiced: **$2,515.75**. Each one showed the \"Invoice saved\" confirmation.")

    def pick_element(self, target, verb, lines, url=""):
        _meter("vision", 0.8, 0.0004)
        want = [w for w in target.lower().replace('"', " ").split() if len(w) > 2]
        for i, line in enumerate(lines):
            if want and all(w in line.lower() for w in want):
                return i
        return None

    def check_text(self, condition, text, url="", network=None):
        _meter("vision", 0.7, 0.0004)
        return {"result": True, "reason": "fake"}

    def describe_step(self, before, after, event, point):
        _meter("vision", 1.5, 0.002)
        return {"element": f"element at {point}" if point else "", "intent": event, "result": "screen updated"}


class FakeGrounder:
    label = "SAM 3.1"

    def __init__(self):
        self.fail_on = [s.strip().lower() for s in os.environ.get("AGENT_FAKE_FAIL", "").split(",") if s.strip()]
        self.failed: set[str] = set()

    def locate(self, img: Image.Image, phrase: str) -> Grounded:
        _meter("grounding", 0.9, 0.002)
        key = phrase.lower()
        for f in self.fail_on:
            if f in key and "alternative" not in key and f not in self.failed:
                self.failed.add(f)
                return Grounded(box=[0, 0, 0, 0], point=(0, 0), found=False, reason=f"No element matching '{phrase}' is visible")
        box = _spot(phrase, img.size)
        mask = Image.new("L", img.size, 0)
        ImageDraw.Draw(mask).rounded_rectangle(box, radius=8, fill=255)
        return Grounded(box=box, point=((box[0] + box[2]) / 2, (box[1] + box[3]) / 2), mask=mask)


def _continuation_from(script: str, line: int) -> str:
    """Source of the top-level statement containing `line` and everything after it."""
    tree = ast.parse(script)
    lines = script.splitlines()
    for stmt in tree.body:
        if stmt.lineno <= line <= (stmt.end_lineno or stmt.lineno):
            return "\n".join(lines[stmt.lineno - 1 :])
    return "\n".join(lines[line - 1 :])


class FakePlanner:
    def generate_script(self, task, screenshot, sdk_reference, context=""):
        _meter("planner", 4.0, 0.012)
        return DEMO_SCRIPT.strip("\n")

    def repair_validation(self, task, script, problems, sdk_reference):
        return DEMO_SCRIPT.strip("\n")

    def fix_script(self, *, task, script, failing_line, error, screenshot, progress_log, variables, action_log,
                   user_hint="", sdk_reference):
        _meter("planner", 4.0, 0.012)
        lines = script.splitlines()
        bad = lines[failing_line - 1] if 0 < failing_line <= len(lines) else ""
        target = None
        try:
            call = ast.parse(bad.strip()).body[0].value  # type: ignore[attr-defined]
            if isinstance(call, ast.Call) and call.args and isinstance(call.args[0], ast.Constant):
                target = call.args[0].value
        except Exception:
            pass
        cont = _continuation_from(script, failing_line)
        full = script
        if isinstance(target, str):
            cont = cont.replace(f'"{target}"', f'"{target} (alternative)"', 1)
            full = script.replace(f'"{target}"', f'"{target} (alternative)"', 1)
        return {"explanation": f"Couldn't find '{target}'; trying an alternative description.",
                "wrong_state": "", "recovery": "", "continuation": cont, "full_script": full}

    def generalize_recording(self, name, description, steps, sdk_reference):
        _meter("planner", 4.0, 0.012)
        out = ["INPUTS = {}", "OUTPUTS = {}", "", f"# {name}", 'open_app("Demo")']
        for i, s in enumerate(steps, 1):
            out.append(f"# Step {i}: {s.get('intent', '')}")
            if s["kind"] == "click":
                out.append(f'click("{s.get("element") or "target"}", expect="{s.get("result", "")}")')
            elif s["kind"] == "type":
                out.append(f"type_text({s.get('text', '')!r})")
            elif s["kind"] == "press":
                out.append(f"press({s.get('key', 'enter')!r})")
            elif s["kind"] == "hotkey":
                out.append("hotkey(" + ", ".join(repr(k) for k in s.get("keys", [])) + ")")
        return "\n".join(out)


class FakeVoice:
    def transcribe(self, audio: bytes, mime: str = "audio/webm") -> str:
        return "create invoices from the orders table"
