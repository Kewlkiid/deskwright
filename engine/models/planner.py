"""Muse Wonder: writes SDK scripts, repairs them when a line fails, and generalizes demonstrations."""
from __future__ import annotations

import json
import re

from PIL import Image

from ..config import config
from ..screen.capture import fit, to_data_url
from . import prompts
from .client import (ModelClient, ModelError, extract_code, extract_json, image_part, language_line, now_line,
                     text_part)


def _request_values(reply: str) -> dict:
    """The ```json block after the script: input values given in the user's request."""
    m = re.search(r"```json\s*(\{.*?\})\s*```", reply, re.S)
    if not m:
        return {}
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


MULTI_STEP = re.compile(r"\b(then|after that|afterwards|also|each|every|all|table|compare|and save|and send|"
                        r"for each|list of|both)\b", re.I)


def simple_request(task: str) -> bool:
    """A short, single-goal request: the planner thinks less (much faster) for these."""
    return len(task.split()) <= 22 and not MULTI_STEP.search(task)


def _clarify(reply: str) -> dict | None:
    """A ```clarify block: the planner needs the user to settle an ambiguity before writing the script."""
    m = re.search(r"```clarify\s*(\{.*?\})\s*```", reply, re.S)
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    q = str(data.get("question") or "").strip()
    if not q:
        return None
    opts = [str(o).strip() for o in (data.get("options") or []) if str(o).strip()][:6]
    return {"question": q, "options": opts}


def numbered(script: str, start: int = 1) -> str:
    return "\n".join(f"{i:>3}| {line}" for i, line in enumerate(script.splitlines(), start))


class Planner:
    def __init__(self, client: ModelClient):
        self.client = client
        self.request_inputs: dict = {}  # input values the last generate_script() found in the user's request
        self.clarify: dict | None = None  # the question the last generate_script() asked instead of a script

    def _chat(self, system: str, content: list, max_tokens: int = 3000, effort: str | None = None) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        reply = self.client.chat("planner", config.planner_model, messages, max_tokens=max_tokens, temperature=0.2,
                                 effort=effort)
        if "```" not in reply and "{" not in reply:
            # Muse Wonder occasionally answers with only the explanation sentence; ask once more for the code.
            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": "That reply had no code. Reply in the required format now: the ```python "
                                            "code block, then the ```json block of input values if the script has inputs."},
            ]
            reply = self.client.chat("planner", config.planner_model, messages, max_tokens=max_tokens, temperature=0.2)
        return reply

    def generate_script(self, task: str, screenshot: Image.Image | None, sdk_reference: str, context: str = "") -> str:
        content = []
        if screenshot is not None:
            content.append(image_part(to_data_url(fit(screenshot, config.model_image_max)[0])))
        text = f"TASK: {task}\n{now_line()}\n{language_line()}"
        if context:
            text += f"\nCONTEXT:\n{context}\n"
        text += "\nThe image is the user's screen right now. Write the script."
        content.append(text_part(text))
        reply = self._chat(prompts.PLANNER_SYSTEM.format(sdk_reference=sdk_reference, never_open=config.never_open), content,
                           effort="low" if simple_request(task) else None)
        self.request_inputs = _request_values(reply)
        self.clarify = _clarify(reply)
        if self.clarify and "```python" not in reply:
            return ""  # a question instead of a script: the caller asks the user and plans again
        return extract_code(reply)

    def repair_validation(self, task: str, script: str, problems: list[str], sdk_reference: str) -> str:
        content = [
            text_part(
                f"TASK: {task}\n\nThis script was rejected by the safety validator:\n```python\n{script}\n```\n"
                "Problems:\n- " + "\n- ".join(problems) + "\n\nRewrite it to follow the rules."
            )
        ]
        reply = self._chat(prompts.PLANNER_SYSTEM.format(sdk_reference=sdk_reference, never_open=config.never_open), content)
        self.request_inputs = _request_values(reply) or self.request_inputs  # the values may only come now
        return extract_code(reply)

    def fix_script(
        self,
        *,
        task: str,
        script: str,
        failing_line: int,
        error: dict,
        screenshot: Image.Image | None,
        progress_log: dict,
        variables: dict,
        action_log: list[str],
        user_hint: str = "",
        sdk_reference: str,
        tried: list[str] | None = None,
        on_screen: list[str] | None = None,
    ) -> dict:
        lines = script.splitlines()
        failing_src = lines[failing_line - 1] if 0 < failing_line <= len(lines) else ""
        text = (
            f"TASK: {task}\n{now_line()}\n{language_line()}\nSCRIPT:\n{numbered(script)}\n\n"
            f"FAILING LINE {failing_line}: {failing_src.strip()}\n"
            f"ERROR: {json.dumps(error)}\n\n"
            f"PROGRESS LOG: {json.dumps(progress_log)[:3000]}\n\n"
            f"VARIABLES (already defined): {json.dumps(variables)[:3000]}\n\n"
            "RECENT ACTIONS:\n" + "\n".join(action_log[-15:]) + "\n"
        )
        if tried:
            text += "\nALREADY TRIED for this step (failed, don't repeat):\n- " + "\n- ".join(tried) + "\n"
        if on_screen:
            text += "\nWHAT IS ON SCREEN (text and controls): " + " | ".join(on_screen) + "\n"
        if user_hint:
            text += f"\nTHE USER SAYS: {user_hint}\n"
        text += "\nThe image is the screen right now. Reply with the JSON."
        content = []
        if screenshot is not None:
            content.append(image_part(to_data_url(fit(screenshot, config.model_image_max)[0])))
        content.append(text_part(text))
        system = prompts.FIXER_SYSTEM.format(sdk_reference=sdk_reference, never_open=config.never_open)
        try:
            data = extract_json(self._chat(system, content, 4000))
        except ModelError:
            # Cut off: long reasoning used up the budget before the JSON ended. Once more with room to finish.
            data = extract_json(self._chat(system, content, 9000))
        clarify = data.get("clarify")
        if isinstance(clarify, dict) and str(clarify.get("question") or "").strip():
            return {"clarify": {"question": str(clarify["question"]).strip(),
                                "options": [str(o) for o in (clarify.get("options") or [])][:6]},
                    "explanation": "", "wrong_state": "", "recovery": "", "continuation": "", "full_script": ""}
        return {
            "explanation": str(data.get("explanation", "")),
            "wrong_state": str(data.get("wrong_state") or ""),
            "recovery": extract_code(str(data.get("recovery") or "")),
            "continuation": extract_code(str(data.get("continuation", ""))),
            "full_script": extract_code(str(data.get("full_script", ""))),
        }

    def generalize_recording(self, name: str, description: str, steps: list[dict], sdk_reference: str) -> str:
        text = (
            f"TASK NAME: {name}\nWHAT THE USER SAID ABOUT IT: {description or '(nothing)'}\n\n"
            f"RECORDED STEPS:\n{json.dumps(steps, indent=1)}\n\nWrite the reusable script."
        )
        return extract_code(
            self._chat(prompts.GENERALIZE_SYSTEM.format(sdk_reference=sdk_reference), [text_part(text)], 4000)
        )
