"""Environment-driven configuration. The API key is read here and never leaves the engine."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = Path(os.environ.get("AGENT_DATA_DIR", ROOT / "engine" / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)


def _flag(name: str, default: str = "0") -> bool:
    return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")


@dataclass
class Config:
    api_key: str = field(default_factory=lambda: os.environ.get("MODEL_API_KEY", ""))
    base_url: str = field(default_factory=lambda: os.environ.get("MODEL_BASE_URL", "https://api.meta.ai/v1"))
    planner_model: str = field(default_factory=lambda: os.environ.get("PLANNER_MODEL", "muse-wonder-1.0"))
    vision_model: str = field(default_factory=lambda: os.environ.get("VISION_MODEL", "muse-spark-1.3"))
    # SAM 3.1 finds elements first; empty disables it (e.g. on OpenRouter, which doesn't host SAM).
    grounding_model: str = field(default_factory=lambda: os.environ.get("GROUNDING_MODEL", "sam-3.1"))
    # Backup grounding: labelled-grid prompting on this vision model. Defaults to the vision model (Muse Spark);
    # on OpenRouter use google/gemma-4-26b-a4b-it, which is faster and more accurate at it.
    grid_model: str = field(default_factory=lambda: os.environ.get("GRID_MODEL", "") or os.environ.get("VISION_MODEL", "muse-spark-1.3"))
    # Meta API reasoning_effort for grid passes (minimal|low|medium|...); empty = the model's default.
    grid_effort: str = field(default_factory=lambda: os.environ.get("GRID_EFFORT", ""))
    # On-device OCR text lines as extra grounding candidates next to SAM's (macOS Vision framework).
    ocr_candidates: bool = field(default_factory=lambda: _flag("AGENT_OCR", "1"))
    # Wake word: "hey <wake_word>, ..." starts a task while the voice button is on (models/wake.py).
    wake_word: str = field(default_factory=lambda: os.environ.get("WAKE_WORD", "agent"))
    # Conversation turns (models/chat.py): quick replies, and the decision to take control. Defaults to the vision model.
    chat_model: str = field(default_factory=lambda: os.environ.get("CHAT_MODEL", "") or os.environ.get("VISION_MODEL", "muse-spark-1.3"))
    # Talking back (speaker.py): a Pocket TTS voice name (alba, anna, charles, eve, george, jane, mary, paul...).
    tts_voice: str = field(default_factory=lambda: os.environ.get("TTS_VOICE", "alba"))
    voice_model: str = field(default_factory=lambda: os.environ.get("VOICE_MODEL", "muse-voice-transcribe-1.0"))
    fake_models: bool = field(default_factory=lambda: _flag("AGENT_FAKE_MODELS"))
    # Synthetic screen and no real input at all: UI development and tests without screen permissions.
    fake_screen: bool = field(default_factory=lambda: _flag("AGENT_FAKE_SCREEN"))
    # Dry run: move the mouse but never click or type. Defaults on with fake models.
    dry_run: bool = field(default_factory=lambda: _flag("AGENT_DRY_RUN", os.environ.get("AGENT_FAKE_MODELS", "0")))
    price_in_per_m: float = field(default_factory=lambda: float(os.environ.get("PRICE_IN_PER_M", "1.0")))
    price_out_per_m: float = field(default_factory=lambda: float(os.environ.get("PRICE_OUT_PER_M", "4.0")))
    price_per_grounding_call: float = field(
        default_factory=lambda: float(os.environ.get("PRICE_PER_GROUNDING_CALL", "0.002"))
    )
    # Optional dedicated SAM endpoint path (e.g. "/segment"). Empty = call SAM through chat completions.
    grounding_endpoint: str = field(default_factory=lambda: os.environ.get("GROUNDING_ENDPOINT", ""))
    # Seconds to hold the on-screen overlay (found element) before acting, so people can follow along.
    show_delay: float = field(default_factory=lambda: float(os.environ.get("AGENT_SHOW_DELAY", "0.45")))
    # Reasoning models think before answering and those tokens count against max_tokens; this headroom is added
    # to every request so a long think never leaves an empty answer. Only tokens actually used are billed.
    reasoning_headroom: int = field(default_factory=lambda: int(os.environ.get("REASONING_HEADROOM", "4000")))
    # Reasoning effort hint for providers that accept one (OpenRouter): low keeps vision steps fast.
    reasoning_effort: str = field(default_factory=lambda: os.environ.get("REASONING_EFFORT", "low"))
    # Chrome extension bridge (extension/): DOM-first actions in Chrome, network capture, Chrome teach mode.
    browser_enabled: bool = field(default_factory=lambda: _flag("AGENT_BROWSER", "1"))
    browser_port: int = field(default_factory=lambda: int(os.environ.get("AGENT_BROWSER_PORT", "8777")))
    # Use the browser backend even when Chrome isn't the frontmost app (testing with a separate Chrome window).
    browser_force: bool = field(default_factory=lambda: _flag("AGENT_BROWSER_FORCE"))
    # Fixed location (not AGENT_DATA_DIR): every engine on this machine must hand the extension the same token.
    browser_token_path: Path = ROOT / "engine" / "data" / "browser_token"
    # Model images are downscaled so the long edge is at most this many pixels.
    model_image_max: int = 1280
    request_timeout: float = 60.0
    max_fixes_per_line: int = 3
    max_fixes_per_run: int = 10
    # Per-run debug folders (runner/debug.py): timeline, model calls, annotated screenshots.
    debug: bool = field(default_factory=lambda: _flag("AGENT_DEBUG", "1"))
    debug_keep: int = field(default_factory=lambda: int(os.environ.get("AGENT_DEBUG_KEEP", "40")))
    debug_dir: Path = DATA_DIR / "debug"
    db_path: Path = DATA_DIR / "agent.db"
    exports_dir: Path = DATA_DIR / "exports"
    recordings_dir: Path = DATA_DIR / "recordings"


config = Config()
config.exports_dir.mkdir(parents=True, exist_ok=True)
config.recordings_dir.mkdir(parents=True, exist_ok=True)
