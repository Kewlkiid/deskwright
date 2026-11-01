"""Agent: ties planner, runner, healer, cache, storage and teach mode together for one host (UI or CLI)."""
from __future__ import annotations

import re
import threading
from pathlib import Path
import time
import traceback

from .cache.position_cache import PositionCache
from .config import config
from .metrics import GLOBAL_METRICS
from .models import get_models
from .runner.healer import run_with_healing
from .runner.schema import header_problems, schema_of
from .runner.validate import scope_problems, validate
from .sdk import SDK_NAMES, sdk_reference
from .sdk.context import Host, RunContext, set_current
from .sdk.errors import AgentError, StoppedError, UserDeclinedError
from .sdk.progress import Progress
from .store.db import DB

START_COMMANDS = re.compile(r"^\s*(start|go|run( it)?|do it|go ahead|execute)\W*$", re.I)
STOP_COMMANDS = re.compile(r"^\s*(stop|halt|cancel|abort)\W*$", re.I)


class Agent:
    def __init__(self, host: Host, db: DB | None = None):
        self.host = host
        self.db = db or DB(config.db_path)
        self.cache = PositionCache(self.db)
        self.stop_event = threading.Event()
        self.capture_paused = threading.Event()
        self._busy = threading.Lock()
        # One run on the screen at a time across processes (the app's engine and CLI runs from other programs).
        from .runner.screen_lock import ScreenLock

        self.screen_lock = ScreenLock(Path(self.db.path).parent)
        self.lock_wait = 0.0  # seconds a run waits for the screen before giving up as "busy"
        self.draft: dict | None = None
        self.recorder = None
        self.teach_dir = None
        self.teach_browser = False  # the Chrome extension is recording too
        self.last_run: dict | None = None  # final script + detours of the latest run, for save_task
        # A pending "show me once" request from another program: {describe, name, request_id}.
        self.teach_request: dict | None = None
        self.ui_bounds: list[float] | None = None  # logical [x, y, w, h] of the floating window

    @property
    def models(self):
        return get_models()

    @property
    def busy(self) -> bool:
        return self._busy.locked()

    def stop(self):
        self.stop_event.set()
        self.host.emit("status", text="Stopping…")

    # Planning --------------------------------------------------------------
    def _context_hint(self) -> str:
        tasks = self.db.query("SELECT name, description FROM tasks ORDER BY updated DESC LIMIT 8")
        if not tasks:
            return ""
        return "Saved tasks the user has taught (for reference): " + "; ".join(
            f"{t['name']}" + (f" ({t['description']})" if t["description"] else "") for t in tasks
        )

    def _new_context(self, task: str, run_id: int = 0, task_id: int | None = None) -> RunContext:
        ctx = RunContext(
            host=self.host, models=self.models, db=self.db, cache=self.cache, task=task, run_id=run_id,
            task_id=task_id, stop_event=self.stop_event, capture_paused=self.capture_paused,
            panel_bounds=lambda: self.ui_bounds,
        )
        ctx.progress = Progress(run_id, self.db if run_id else None)
        if hasattr(self.models.grounder, "reset"):
            self.models.grounder.reset()  # every run starts in auto mode with a clean SAM failure count
        return ctx

    def write_script(self, ctx: RunContext, task: str) -> str:
        ref = sdk_reference()
        ctx.status("Writing the script…")
        shot = ctx.capture()
        script = self.models.planner.generate_script(task, shot.image, ref, self._context_hint())
        problems = validate(script, SDK_NAMES) + scope_problems(script) + header_problems(script)
        if problems:
            ctx.status("Fixing script problems…")
            script = self.models.planner.repair_validation(task, script, problems, ref)
            problems = validate(script, SDK_NAMES) + scope_problems(script) + header_problems(script)
            if problems:
                raise AgentError("The planner's script failed validation: " + "; ".join(problems), retryable=False)
        # Values the request already gave ("send sam hi") fill the inputs, so a chat run doesn't ask for them again.
        declared, _ = schema_of(script)
        given = getattr(self.models.planner, "request_inputs", {}) or {}
        for k, v in given.items():
            if k in declared and k not in ctx.inputs:
                ctx.inputs[k] = v
        return script

    def create_from_description(self, description: str, name: str = "", inputs: dict | None = None,
                                outputs: dict | None = None, test_inputs: dict | None = None,
                                request_id: str | None = None) -> dict:
        """Write and save a task from a text request, without a demonstration (CLI `create --describe`).
        Returns {"status": "ok" | "needs_demo" | "failed", "name", "inputs", "outputs", "error", "tested"}.
        "needs_demo": the planner couldn't produce a script that validates, or the test run with `test_inputs`
        failed, so someone has to show the task once (teach mode)."""
        import json as _json
        import re

        from .runner.schema import with_header

        name = (name or "").strip() or re.sub(r"\s+", " ", description).strip()[:48]
        result = {"status": "failed", "name": name, "inputs": {}, "outputs": {}, "error": None, "tested": False}
        if self.db.get_task(name=name):
            result["error"] = f"a task named {name!r} already exists"
            return result
        task = description
        if inputs is not None or outputs is not None:
            task += ("\n\nThis is a reusable task. Its header must declare exactly these:\n"
                     f"INPUTS = {_json.dumps(inputs or {})}\nOUTPUTS = {_json.dumps(outputs or {})}")
        ctx = self._new_context(task)
        set_current(ctx)
        try:
            script = self.write_script(ctx, task)
            if inputs is not None or outputs is not None:
                # The caller's schema is the contract: put it in the header exactly as given.
                header = f"INPUTS = {_json.dumps(inputs or {})}\nOUTPUTS = {_json.dumps(outputs or {})}"
                script = with_header(script, header)
                problems = validate(script, SDK_NAMES) + header_problems(script)
                if problems:
                    raise AgentError("the script doesn't fit the requested inputs/outputs: " + "; ".join(problems),
                                     retryable=False)
        except Exception as e:  # noqa: BLE001
            result.update(status="needs_demo", error=f"couldn't write it from the description: {e}")
            return result
        finally:
            set_current(None)
        result["inputs"], result["outputs"] = schema_of(script)
        if test_inputs is not None:
            out = self.run_task(description, script, inputs=test_inputs, no_ask=True)
            result["tested"] = True
            if out.get("status") != "succeeded":
                err = out.get("error")
                result.update(status="needs_demo",
                              error=f"the test run didn't work: {(err or {}).get('message') if isinstance(err, dict) else err}")
                return result
            script = out.get("final_script") or script
        self.db.save_task(name, script, description=description, source="describe", request_id=request_id)
        result["status"] = "ok"
        return result

    def draft_task(self, task: str):
        """Write a script and show it without running it (review mode). 'start' runs it."""
        if not self._busy.acquire(blocking=False):
            self.host.emit("error", message="Busy: a run is in progress")
            return
        self.stop_event.clear()
        ctx = self._new_context(task)
        set_current(ctx)
        try:
            script = self.write_script(ctx, task)
            self.draft = {"task": task, "script": script}
            self.host.emit("script_generated", script=script, segment=0, draft=True, task=task)
            self.host.emit("status", text='Script ready. Say "start" or press Run.')
        except StoppedError:
            self.host.emit("status", text="Stopped")
        except Exception as e:  # noqa: BLE001
            self.host.emit("error", message=str(e))
        finally:
            set_current(None)
            self._busy.release()

    # Running ---------------------------------------------------------------
    def run_task(self, task: str, script: str | None = None, task_id: int | None = None,
                 inputs: dict | None = None, no_ask: bool = False) -> dict:
        """Run a task. `inputs` are values for the script's declared INPUTS (from the CLI or another program);
        missing ones are asked for, unless `no_ask`, which makes a missing input fail the run."""
        if not self._busy.acquire(blocking=False):
            self.host.emit("error", message="Busy: a run is in progress")
            return {"status": "busy", "error": {"message": "a run is already in progress here"}, "outputs": {}, "run_id": None}
        from .runner.screen_lock import ScreenBusy

        try:
            self.screen_lock.acquire(task, wait=self.lock_wait)
        except ScreenBusy as e:
            self._busy.release()
            self.host.emit("error", message=f"Busy: {e}")
            return {"status": "busy", "error": {"message": str(e)}, "outputs": {}, "run_id": None}
        self.stop_event.clear()
        run_id = self.db.start_run(task, task_id)
        self.screen_lock.note_run(run_id)
        ctx = self._new_context(task, run_id, task_id)
        if task_id:
            from .runner.detours import Detour

            ctx.detours = [Detour(step=r["step"], when=r["when_text"], screen=r["screen"], window=r["window"] or "",
                                  recover=r["recover"], source=r["source"] or "", id=r["id"], uses=r["uses"])
                           for r in self.db.task_detours(task_id)]
        ctx.inputs = dict(inputs or {})
        ctx.no_ask = no_ask
        if config.debug and not config.fake_models:
            from .runner.debug import RunDebug

            try:
                ctx.debug = RunDebug(run_id, task)
            except OSError:
                ctx.debug = None
        set_current(ctx)
        status, final_script, error = "failed", script or "", None
        self.host.emit("run_started", run_id=run_id, task=task, task_id=task_id)
        try:
            if script is None:
                script = self.write_script(ctx, task)
            else:
                problems = validate(script, SDK_NAMES)
                if problems:
                    raise AgentError("Script failed validation: " + "; ".join(problems), retryable=False)
            final_script = script
            ctx.input_schema, ctx.output_schema = schema_of(script)
            self.host.emit("script_generated", script=script, segment=0, draft=False, task=task,
                           inputs=ctx.input_schema, outputs=ctx.output_schema)
            self._start_network_capture(ctx, script)
            result = run_with_healing(ctx, script, sdk_reference())
            status = result["status"]
            final_script = result["final_script"]
            error = result.get("error")
            if status == "succeeded" and task_id and ctx.metrics.fixes and final_script != script:
                t = self.db.get_task(task_id)
                if t:
                    self.db.save_task(t["name"], final_script, note=f"self-healed in run {run_id}")
                    self.host.emit("task_updated", task_id=task_id, note="Saved the repaired script into the task")
        except StoppedError as e:
            status, error = "stopped", e.to_dict()
        except UserDeclinedError as e:
            status, error = "declined", e.to_dict()
        except AgentError as e:
            status, error = "failed", e.to_dict()
        except Exception as e:  # noqa: BLE001
            status, error = "error", {"message": f"{type(e).__name__}: {e}", "trace": traceback.format_exc()[-1500:]}
        finally:
            self._release_browser(ctx)
            # Ways back learned in this run: saved tasks keep them; a chat run hands them to a later save.
            learned = [d.to_dict() for d in ctx.new_detours]
            if task_id:
                for d in learned:
                    self.db.add_detour(task_id, d)
            self.last_run = {"final_script": final_script, "detours": learned}
            metrics = ctx.metrics.snapshot()
            self.db.finish_run(run_id, status, metrics)
            if ctx.debug is not None:
                ctx.debug.finish(status, metrics, error)
            self.host.emit(
                "run_finished",
                run_id=run_id,
                task_id=task_id,
                task=task,
                status=status,
                error=error,
                metrics=metrics,
                final_script=final_script,
                results=ctx.results,
                outputs=ctx.outputs,
                history=self.db.task_runs(task_id) if task_id else [],
                totals=self.db.all_runs_summary(),
                debug_dir=str(ctx.debug.dir) if ctx.debug is not None else None,
            )
            set_current(None)
            self.screen_lock.release()
            self._busy.release()
        return {"status": status, "final_script": final_script, "error": error, "metrics": metrics,
                "outputs": dict(ctx.outputs), "run_id": run_id}

    # Chrome -----------------------------------------------------------------
    @staticmethod
    def _start_network_capture(ctx: RunContext, script: str):
        """network_response() can only see requests made after capture starts, so start it before the first line."""
        if "network_response" not in script:
            return
        from .browser.backend import browser_for

        b = browser_for(ctx, need_focus=False)
        if b:
            try:
                b.ensure_capture(ctx)
            except Exception as e:  # noqa: BLE001
                ctx.log(f"network capture unavailable: {e}")

    @staticmethod
    def _release_browser(ctx: RunContext):
        """Detach Chrome's debugger (network capture, page_js) when the run ends, so its banner goes away."""
        if not (ctx.browser_capture or ctx.browser_used):
            return
        from .browser.bridge import get_bridge

        bridge = get_bridge()
        try:
            if bridge is not None and bridge.connected:
                bridge.call("net_stop", timeout=3)
        except Exception:  # noqa: BLE001
            pass

    def browser_status(self) -> dict:
        from .browser.bridge import get_bridge

        bridge = get_bridge()
        if bridge is None:
            return {"enabled": False, "connected": False}
        return {"enabled": True, "connected": bridge.connected, "port": bridge.port, **bridge.info}

    def run_draft(self, script: str | None = None):
        if not self.draft and not script:
            self.host.emit("error", message="No script to run")
            return
        draft = self.draft or {"task": "edited script"}
        self.draft = None
        self.run_task(draft["task"], script or draft["script"])

    def run_saved(self, task_id: int | None = None, name: str | None = None):
        t = self.db.get_task(task_id=task_id, name=name)
        if not t:
            self.host.emit("error", message=f"No saved task {name or task_id}")
            return
        self.run_task(t["description"] or t["name"], t["script"], t["id"])

    def find_saved_by_phrase(self, text: str) -> dict | None:
        m = re.match(r"^\s*(run|do|replay)\s+(the\s+)?(?P<name>.+?)(\s+task)?\s*$", text, re.I)
        if not m:
            return None
        return self.db.get_task(name=m.group("name"))

    def handle_command(self, text: str, auto_run: bool = True):
        """Entry point for typed or spoken commands."""
        text = text.strip()
        if not text:
            return
        if STOP_COMMANDS.match(text):
            self.stop()
            return
        if START_COMMANDS.match(text) and self.draft:
            self.run_draft()
            return
        saved = self.find_saved_by_phrase(text)
        if saved:
            self.run_task(saved["description"] or saved["name"], saved["script"], saved["id"])
        elif auto_run:
            self.run_task(text)
        else:
            self.draft_task(text)

    # Voice -----------------------------------------------------------------
    def transcribe(self, audio: bytes, mime: str) -> str:
        t0 = time.time()
        text = self.models.voice.transcribe(audio, mime)
        self.host.emit("transcript", text=text, seconds=round(time.time() - t0, 2))
        return text

    # Teach mode ------------------------------------------------------------
    def _inside_ui(self, x: float, y: float) -> bool:
        b = self.ui_bounds
        return bool(b) and b[0] <= x <= b[0] + b[2] and b[1] <= y <= b[1] + b[3]

    def teach_start(self):
        from .teach.recorder import Recorder

        if self.recorder:
            return
        self.teach_dir = config.recordings_dir / time.strftime("%Y%m%d_%H%M%S")
        self.recorder = Recorder(self.teach_dir, exclude=self._inside_ui)
        self.recorder.start()
        # In Chrome, the extension also records DOM actions (selectors, labels, typed values) and API calls.
        from .browser.bridge import get_bridge

        bridge = get_bridge()
        if bridge is not None and bridge.connected:
            try:
                bridge.call("teach_start", timeout=5)
                self.teach_browser = True
            except Exception as e:  # noqa: BLE001
                self.host.emit("status", text=f"Chrome recording unavailable: {e}")
        self.host.emit("teach_recording", recording=True, browser=self.teach_browser)

    def teach_stop(self, name: str = "", description: str = ""):
        from .teach.compiler import compile_recording

        if not self.recorder:
            return
        meta = self.recorder.stop()
        self.recorder = None
        browser = None
        if self.teach_browser:
            from .browser.bridge import get_bridge

            try:
                browser = get_bridge().call("teach_stop", timeout=20)
            except Exception as e:  # noqa: BLE001
                self.host.emit("status", text=f"Could not collect the Chrome recording: {e}")
        self.teach_browser = False
        self.host.emit("teach_recording", recording=False, events=len(meta["events"]),
                       browser_events=len((browser or {}).get("events") or []))
        req = self.teach_request or {}
        name = name or req.get("name") or f"Taught task {time.strftime('%H:%M')}"
        description = description or req.get("describe") or ""
        try:
            out = compile_recording(meta, name, description, self.models, self.host.emit, browser=browser)
            self.host.emit("teach_compiled", name=name, description=description, script=out["script"],
                           steps=out["steps"], problems=out["problems"], metrics=GLOBAL_METRICS.snapshot())
        except Exception as e:  # noqa: BLE001
            self.host.emit("error", message=f"Could not compile the recording: {e}")

    # Tasks -----------------------------------------------------------------
    def save_task(self, name: str, script: str, description: str = "", source: str = "chat") -> int | None:
        problems = validate(script, SDK_NAMES)
        if problems:
            self.host.emit("error", message="Can't save: " + "; ".join(problems))
            return None
        # A taught task that answers a pending outside request gets that request's id, so the asker can find it.
        req = self.teach_request if source == "teach" else None
        task_id = self.db.save_task(name, script, description, source, request_id=(req or {}).get("request_id"))
        if req:
            self.teach_request = None
        last = self.last_run or {}
        if last.get("detours") and last.get("final_script", "").strip() == script.strip():
            for d in last["detours"]:
                self.db.add_detour(task_id, d)  # the ways back learned while making this task
        self.host.emit("tasks", tasks=self.db.list_tasks())
        return task_id
