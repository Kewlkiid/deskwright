"""Muse Spark: the vision executor behind the SDK's prompt-driven methods."""
from __future__ import annotations

from PIL import Image, ImageDraw

from ..config import config
from ..screen.capture import fit, to_data_url
from . import prompts
from .client import ModelClient, extract_json, image_part, text_part


def _prev_block(prev: dict | None) -> str:
    if not prev:
        return prompts.NO_PREV_BLOCK
    return prompts.PREV_EXPECT_BLOCK.format(prev_action=prev.get("action", "an action"), expect=prev["expect"])


def _bool_or_none(v) -> bool | None:
    if v is None:
        return None
    if isinstance(v, str):
        return v.strip().lower() in ("true", "yes", "1")
    return bool(v)


def zoom_for_reading(img: Image.Image, min_edge: int = 500) -> Image.Image:
    if max(img.size) < min_edge:
        f = min_edge / max(img.size, default=1)
        return img.resize((round(img.width * f), round(img.height * f)), Image.LANCZOS)
    return img


class Vision:
    def __init__(self, client: ModelClient):
        self.client = client
        self.system = prompts.VISION_SYSTEM

    def _ask_json(self, images: list[Image.Image], prompt: str, max_tokens: int = 800) -> dict:
        content = [image_part(to_data_url(i)) for i in images] + [text_part(prompt)]
        reply = self.client.chat(
            "vision",
            config.vision_model,
            [{"role": "system", "content": self.system}, {"role": "user", "content": content}],
            max_tokens=max_tokens,
            temperature=0.0,
        )
        data = extract_json(reply)
        return data if isinstance(data, dict) else {"value": data}

    def check(self, img: Image.Image, condition: str, prev: dict | None = None) -> dict:
        small, _ = fit(img, config.model_image_max)
        data = self._ask_json(
            [small],
            prompts.CHECK_PROMPT.format(w=small.width, h=small.height, condition=condition, prev_block=_prev_block(prev)),
        )
        return {
            "result": bool(_bool_or_none(data.get("result"))),
            "reason": str(data.get("reason") or ""),
            "prev_expect_met": _bool_or_none(data.get("prev_expect_met")) if prev else None,
            "observation": str(data.get("observation") or ""),
        }

    def ask(self, img: Image.Image, question: str, prev: dict | None = None) -> dict:
        small, _ = fit(img, config.model_image_max)
        data = self._ask_json(
            [small],
            prompts.ASK_PROMPT.format(w=small.width, h=small.height, question=question, prev_block=_prev_block(prev)),
            max_tokens=1500,
        )
        return {
            "answer": str(data.get("answer") or data.get("value") or ""),
            "prev_expect_met": _bool_or_none(data.get("prev_expect_met")) if prev else None,
            "observation": str(data.get("observation") or ""),
        }

    def read_text(self, img: Image.Image) -> str:
        img, _ = fit(zoom_for_reading(img), 1600)
        content = [image_part(to_data_url(img, "PNG")), text_part(prompts.READ_TEXT_PROMPT)]
        return self.client.chat(
            "vision",
            config.vision_model,
            [{"role": "system", "content": self.system}, {"role": "user", "content": content}],
            max_tokens=3000,
            temperature=0.0,
        ).strip()

    def read_table(self, img: Image.Image, target: str, columns: list[str] | None = None) -> dict:
        img, _ = fit(zoom_for_reading(img, 800), 1600)
        hint = f" (expected columns: {', '.join(columns)})" if columns else ""
        data = self._ask_json([img], prompts.READ_TABLE_PROMPT.format(target=target, columns_hint=hint), max_tokens=4000)
        return {"columns": [str(c) for c in data.get("columns") or []], "rows": data.get("rows") or []}

    def reread_columns(self, img: Image.Image, columns: list[str]) -> list[dict]:
        zoomed = img.resize((img.width * 2, img.height * 2), Image.LANCZOS)
        zoomed, _ = fit(zoomed, 2000)
        data = self._ask_json([zoomed], prompts.ZOOM_NUMBERS_PROMPT.format(columns=", ".join(columns)), max_tokens=3000)
        return [r for r in data.get("rows") or [] if isinstance(r, dict)]

    def summarize(self, instruction: str, data: str, img: Image.Image | None = None) -> str:
        content = []
        if img is not None:
            small, _ = fit(img, config.model_image_max)
            content.append(image_part(to_data_url(small)))
        content.append(text_part(prompts.SUMMARIZE_PROMPT.format(instruction=instruction, data=data or "(none)")))
        return self.client.chat(
            "vision",
            config.vision_model,
            [{"role": "system", "content": self.system}, {"role": "user", "content": content}],
            max_tokens=2000,
            temperature=0.3,
        ).strip()

    def _text_json(self, prompt: str, max_tokens: int = 400) -> dict:
        reply = self.client.chat(
            "vision",
            config.vision_model,
            [{"role": "system", "content": self.system}, {"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.0,
        )
        data = extract_json(reply)
        return data if isinstance(data, dict) else {}

    def pick_element(self, target: str, verb: str, lines: list[str], url: str = "") -> int | None:
        """Choose the target from a numbered text list of page elements (no screenshot)."""
        data = self._text_json(prompts.PICK_ELEMENT_PROMPT.format(url=url, verb=verb, target=target, lines="\n".join(lines)))
        try:
            return None if data.get("index") is None else int(data["index"])
        except (TypeError, ValueError):
            return None

    def check_text(self, condition: str, text: str, url: str = "", network: list[str] | None = None) -> dict:
        """Judge a condition from page text; result is True, False, or None (can't tell from text)."""
        net = ("RECENT NETWORK CALLS:\n" + "\n".join(network) + "\n") if network else ""
        data = self._text_json(prompts.CHECK_TEXT_PROMPT.format(condition=condition, url=url, text=text[:6000], network=net))
        return {"result": _bool_or_none(data.get("result")), "reason": str(data.get("reason") or "")}

    def describe_step(self, before: Image.Image, after: Image.Image, event: str, point: tuple[int, int] | None) -> dict:
        b = before.convert("RGB").copy()
        if point:
            d = ImageDraw.Draw(b)
            x, y = point
            d.ellipse([x - 18, y - 18, x + 18, y + 18], outline=(255, 0, 0), width=4)
            crop = before.crop((x - 160, y - 100, x + 160, y + 100))
        else:
            crop = before.crop((0, 0, min(before.width, 640), min(before.height, 400)))
        images = [fit(b, config.model_image_max)[0], crop, fit(after, config.model_image_max)[0]]
        return self._ask_json(images, prompts.DESCRIBE_STEP_PROMPT.format(event=event))
