"""Muse Wonder: writes SDK scripts, repairs them when a line fails, and generalizes demonstrations."""
from __future__ import annotations

import json
import re

from PIL import Image

from ..config import config
from ..screen.capture import fit, to_data_url
from . import prompts
from .client import ModelClient, extract_code, extract_json, image_part, text_part


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


def numbered(script: str, start: int = 1) -> str:
    return "\n".join(f"{i:>3}| {line}" for i, line in enumerate(script.splitlines(), start))


class Planner:
    def __init__(self, client: ModelClient):
        self.client = client
        self.request_inputs: dict = {}  # input values the last generate_script() found in the user's request

    def _chat(self, system: str, content: list, max_tokens: int = 3000) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        reply = self.client.chat("planner", config.planner_model, messages, max_tokens=max_tokens, temperature=0.2)
        if "```" not in reply and "{" not in reply:
            # Muse Wonder occasionally answers with only the explanation sentence; ask once more for the code.
            messages += [
                {"role": "assistant", "content": reply},
                {"role": "user", "content": "That reply had no code. Reply with the ```python code block only."},
            ]
            reply = self.client.chat("planner", config.planner_model, messages, max_tokens=max_tokens, temperature=0.2)
        return reply

    def generate_script(self, task: str, screenshot: Image.Image | None, sdk_reference: str, context: str = "") -> str:
        content = []
        if screenshot is not None:
            content.append(image_part(to_data_url(fit(screenshot, config.model_image_max)[0])))
        text = f"TASK: {task}\n"
        if context:
            text += f"\nCONTEXT:\n{context}\n"
        text += "\nThe image is the user's screen right now. Write the script."
        content.append(text_part(text))
        reply = self._chat(prompts.PLANNER_SYSTEM.format(sdk_reference=sdk_reference), content)
        self.request_inputs = _request_values(reply)
        return extract_code(reply)

    def repair_validation(self, task: str, script: str, problems: list[str], sdk_reference: str) -> str:
        content = [
            text_part(
                f"TASK: {task}\n\nThis script was rejected by the safety validator:\n```python\n{script}\n```\n"
                "Problems:\n- " + "\n- ".join(problems) + "\n\nRewrite it to follow the rules."
            )
        ]
        return extract_code(self._chat(prompts.PLANNER_SYSTEM.format(sdk_reference=sdk_reference), content))

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
    ) -> dict:
        lines = script.splitlines()
        failing_src = lines[failing_line - 1] if 0 < failing_line <= len(lines) else ""
        text = (
            f"TASK: {task}\n\nSCRIPT:\n{numbered(script)}\n\n"
            f"FAILING LINE {failing_line}: {failing_src.strip()}\n"
            f"ERROR: {json.dumps(error)}\n\n"
            f"PROGRESS LOG: {json.dumps(progress_log)[:3000]}\n\n"
            f"VARIABLES (already defined): {json.dumps(variables)[:3000]}\n\n"
            "RECENT ACTIONS:\n" + "\n".join(action_log[-15:]) + "\n"
        )
        if user_hint:
            text += f"\nTHE USER SAYS: {user_hint}\n"
        text += "\nThe image is the screen right now. Reply with the JSON."
        content = []
        if screenshot is not None:
            content.append(image_part(to_data_url(fit(screenshot, config.model_image_max)[0])))
        content.append(text_part(text))
        data = extract_json(self._chat(prompts.FIXER_SYSTEM.format(sdk_reference=sdk_reference), content, 4000))
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
