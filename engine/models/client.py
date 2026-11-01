"""OpenAI-SDK client pointed at the Meta Model API, with metering and typed errors."""
from __future__ import annotations

import json
import re
import threading
import time
from typing import Any

from ..config import Config
from ..sdk.errors import AgentTimeoutError, ModelError


def current_metrics():
    from ..sdk.context import current_metrics as cm

    return cm()


def interruptible(fn):
    """Run a blocking API call so that a stop (Esc) ends the run right away instead of after the reply arrives.
    The abandoned request finishes in the background and its answer is dropped."""
    from ..sdk.context import _current as ctx  # read at call time; None outside a run

    if ctx is None:
        return fn()
    box: dict = {}

    def run():
        try:
            box["value"] = fn()
        except BaseException as e:  # noqa: BLE001 - re-raised on the calling thread
            box["error"] = e

    worker = threading.Thread(target=run, daemon=True, name="model-call")
    worker.start()
    while worker.is_alive():
        worker.join(0.05)
        ctx.check_stop()
    if "error" in box:
        raise box["error"]
    return box["value"]


def image_part(data_url: str) -> dict:
    return {"type": "image_url", "image_url": {"url": data_url}}


def text_part(text: str) -> dict:
    return {"type": "text", "text": text}


def extract_json(text: str) -> Any:
    """Parse the first JSON object/array in a model reply (tolerates ```json fences and prose)."""
    text = text.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if fence:
        text = fence.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = text.find(open_ch)
        end = text.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise ModelError(f"Model did not return valid JSON: {text[:200]}", retryable=True)


def extract_code(text: str) -> str:
    fence = re.search(r"```(?:python|py)?\s*\n(.*?)```", text, re.S)
    return (fence.group(1) if fence else text).strip("\n")


def _debug_call(role, model, messages, reply, seconds, error=None, tokens=(0, 0)):
    from ..runner.debug import current_debug

    d = current_debug()
    if d is not None:
        try:
            d.model_call(role, model, messages, reply, seconds, error=error, tokens=tokens)
        except Exception:  # noqa: BLE001 - debugging must never break a run
            pass


def _sleep(seconds: float):
    from ..sdk.context import _current as ctx

    if ctx is None:
        time.sleep(seconds)
    else:
        ctx.sleep(seconds)


class ModelClient:
    def __init__(self, cfg: Config):
        from openai import OpenAI

        if not cfg.api_key:
            raise ModelError(
                "MODEL_API_KEY is not set. Put it in .env or set AGENT_FAKE_MODELS=1 for offline mode.",
                retryable=False,
            )
        self.cfg = cfg
        self.client = OpenAI(api_key=cfg.api_key, base_url=cfg.base_url, timeout=cfg.request_timeout, max_retries=0)
        self.openrouter = "openrouter.ai" in cfg.base_url

    def _cost(self, usage) -> tuple[int, int, float]:
        if usage is None:
            return 0, 0, 0.0
        tin = getattr(usage, "prompt_tokens", 0) or 0
        tout = getattr(usage, "completion_tokens", 0) or 0
        # OpenRouter reports the real per-call cost (it differs per model); otherwise estimate from token prices.
        billed = (getattr(usage, "model_extra", None) or {}).get("cost")
        if isinstance(billed, (int, float)):
            return tin, tout, float(billed)
        cost = tin / 1e6 * self.cfg.price_in_per_m + tout / 1e6 * self.cfg.price_out_per_m
        return tin, tout, cost

    def chat(
        self,
        role: str,
        model: str,
        messages: list[dict],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.2,
        attempts: int = 4,
        reasoning: bool = True,
    ) -> str:
        """`reasoning=False` for models that answer directly: they get no thinking headroom, so a reply that
        rambles is cut off at max_tokens instead of running on."""
        import openai

        last: Exception | None = None
        for attempt in range(attempts):
            t0 = time.time()
            try:
                extra = None
                if self.openrouter:
                    extra = {"usage": {"include": True}}
                    if reasoning and self.cfg.reasoning_effort:
                        extra["reasoning"] = {"effort": self.cfg.reasoning_effort}
                resp = interruptible(lambda: self.client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens + (self.cfg.reasoning_headroom if reasoning else 0),
                    temperature=temperature,
                    extra_body=extra,
                ))
                tin, tout, cost = self._cost(getattr(resp, "usage", None))
                current_metrics().record_call(role, time.time() - t0, tin, tout, cost)
                reply = resp.choices[0].message.content or ""
                _debug_call(role, model, messages, reply, time.time() - t0, tokens=(tin, tout))
                return reply
            except openai.APITimeoutError:
                current_metrics().record_call(role, time.time() - t0)
                last = AgentTimeoutError(f"{role} model timed out", retryable=True)
                _debug_call(role, model, messages, None, time.time() - t0, error="timed out")
            except (openai.RateLimitError, openai.APIConnectionError, openai.InternalServerError) as e:
                current_metrics().record_call(role, time.time() - t0)
                last = ModelError(f"{role} model API error: {e}", retryable=True)
                _debug_call(role, model, messages, None, time.time() - t0, error=str(e))
            except openai.APIStatusError as e:
                current_metrics().record_call(role, time.time() - t0)
                _debug_call(role, model, messages, None, time.time() - t0, error=f"{e.status_code}: {e.message}")
                raise ModelError(f"{role} model API error {e.status_code}: {e.message}", retryable=False)
            if attempt < attempts - 1:
                # 2s, 5s, 12s: rides out short provider overloads (503) without stalling a run for long.
                _sleep((2, 5, 12)[min(attempt, 2)])
        raise last  # type: ignore[misc]

    def record_external(self, role: str, seconds: float, cost: float):
        current_metrics().record_call(role, seconds, cost=cost)
