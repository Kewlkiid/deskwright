import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import {
  BarChart3, GraduationCap, KeyRound, LayoutList, ListChecks, Mic, MoreHorizontal, PanelRightClose, Power, ShieldOff,
  Languages, SquarePen, Volume2,
} from "lucide-react";
import { engine } from "./lib/engine";
import { getLang, LANGUAGES, setLang, t, tStatus } from "./lib/i18n";
import { Markdown } from "./lib/markdown";
import { useWakeWord } from "./lib/wake";
import { initialState, reducer, uid } from "./lib/state";
import type { ChatItem, RunView } from "./lib/types";
import { AgentNote, AgentTurn, ConfirmCard, ErrorNote, QuestionCard, SummaryCard, TeachCard, UserMessage } from "./components/Cards";
import { Composer } from "./components/Composer";
import { LanguageList, MetricsCard, PermissionsCard, PermissionsList, TasksCard } from "./components/InlineCards";
import { Logo } from "./components/Logo";
import { Menu } from "./components/Menu";
import { Pill } from "./components/Pill";
import { Sheet } from "./components/Sheet";
import { ResultCard } from "./components/ResultCard";
import { RunActivity } from "./components/RunActivity";
import { ScriptView } from "./components/ScriptView";


// Engine events that drive the on-screen overlay (grounding box, clicks, verdicts).
const OVERLAY_EVENTS = new Set([
  "run_started", "script_generated", "vision_scan", "sam_mask", "element_found", "vision_miss",
  "pointer", "expect_met", "expect_failed", "line_failed", "line_rewritten", "detour", "confirm_request", "run_finished",
]);

const TASKS_RE = /^(show |list |open )?(my )?(saved )?tasks\??$/i;
const METRICS_RE = /^(show )?(the )?(run )?(metrics|stats|statistics)\??$/i;

const TRANSITION_MS = 240;

/** A spoken answer to a question with options: the option sharing the most words ("the Control one" -> "Control's
 * #support"), else the words as said. */
function matchOption(said: string, options?: string[]): string {
  if (!options || !options.length) return said;
  const words = (t: string) => new Set(t.toLowerCase().replace(/[^a-z0-9#\s]/g, " ").split(/\s+/).filter((w) => w.length > 1));
  const heard = words(said);
  let best = "";
  let score = 0;
  for (const o of options) {
    const n = [...words(o)].filter((w) => heard.has(w) || heard.has(w.replace(/s$/, ""))).length;
    if (n > score) [best, score] = [o, n];
  }
  return score > 0 ? best : said;
}

export default function App() {
  const [s, dispatch] = useReducer(reducer, initialState);
  setLang(s.language); // every t() below and in the components renders in it
  // "panel": full-height column. "pill": compact bar in the top-right corner (during tasks, or collapsed by hand).
  // panel <-> corner bar. The window itself resizes instantly (the bar sits at the same screen spot in both sizes,
  // so nothing visibly moves); all the motion is in the page: the panel slides while the bar fades in or out.
  const [mode, setModeState] = useState<"panel" | "closing" | "pill" | "opening">("panel");
  const modeRef = useRef<"panel" | "pill">("panel");
  const runningRef = useRef(false);
  const actingRef = useRef(false); // the run has started acting on the screen (the panel collapsed for it)
  const pillSize = useRef<"pill" | "mini">("pill");
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const goPill = useCallback(() => {
    // Running: the status bar. Collapsed while idle: only the icon and the open button.
    const size = runningRef.current ? "pill" : "mini";
    if (modeRef.current === "pill") {
      if (pillSize.current !== size) window.agent?.setMode(size);
      pillSize.current = size;
      return;
    }
    modeRef.current = "pill";
    pillSize.current = size;
    clearTimeout(timer.current);
    setModeState("closing"); // slide the panel away and fade the bar in, then shrink the window around the bar
    timer.current = setTimeout(() => {
      window.agent?.setMode(size);
      setModeState("pill");
    }, TRANSITION_MS);
  }, []);
  const goPanel = useCallback(() => {
    if (modeRef.current === "panel") return;
    modeRef.current = "panel";
    clearTimeout(timer.current);
    window.agent?.setMode("panel"); // grow the window first (transparent, the bar stays put), then slide the panel in
    requestAnimationFrame(() => setModeState("opening"));
    timer.current = setTimeout(() => setModeState("panel"), TRANSITION_MS + 40);
  }, []);
  const sendToEngine = useCallback((msg: Record<string, unknown>) => engine.send(msg as any), []);
  const [running, setRunningState] = useState(false);
  // The approval or question the run is waiting on, if any (answerable by voice: "approve", "agent input ...").
  const waiting = [...s.items]
    .reverse()
    .find((i) => (i.kind === "confirm" || i.kind === "question") && i.answer === undefined && !i.closed);
  // Utterances go to the engine even during a run ("stop", "approve") and while Deskwright talks (to cut it off).
  const wake = useWakeWord(sendToEngine, s.speaking, waiting?.kind === "question");
  const wakeRef = useRef(wake);
  wakeRef.current = wake;
  const composer = useRef<{ submit: () => void } | null>(null);
  const voiceRef = useRef<(action: string, text: string) => void>(() => {});
  const bottom = useRef<HTMLDivElement>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const off = engine.on((msg) => {
      dispatch({ type: "event", msg });
      if (OVERLAY_EVENTS.has(msg.type)) {
        const { thumbnail, results, history, final_script, ...light } = msg;
        window.agent?.overlay({ ...light, lang: getLang() });
      }
      if (msg.type === "wake_heard") wakeRef.current.heard();
      if (msg.type === "voice_action") voiceRef.current(msg.action, msg.text || "");
      if (msg.type === "wake_unavailable") wakeRef.current.off();
      if (msg.type === "run_started") {
        // Stay open while the program is written: it may ask for an input first. Collapse at its first action.
        setRunningState(true);
        runningRef.current = true;
        actingRef.current = false;
        window.agent?.setRunning(true);
      }
      const startsActing =
        msg.type === "element_found" ||
        (msg.type === "status" && !/^(Writing the script|Fixing script problems|Stopping)/.test(msg.text || ""));
      if (runningRef.current && !actingRef.current && startsActing) {
        actingRef.current = true;
        window.agent?.yieldFocus(); // the script's typing must reach the app underneath, not this panel
        goPill();
      }
      if (msg.type === "run_finished") {
        setRunningState(false);
        runningRef.current = false;
        window.agent?.setRunning(false);
        goPanel();
      }
      // The run needs you: open the panel for the approval or question, then tuck away again.
      if (msg.type === "confirm_request" || msg.type === "ask_user" || msg.type === "teach_request") goPanel();
      if (msg.type === "suppress_esc") window.agent?.suppressEsc();
      if (msg.type === "request_hide") window.agent?.hideForCapture().then(() => engine.send({ type: "hidden_ack" }));
      if (msg.type === "request_show") window.agent?.showAfterCapture();
    });
    engine.connect();
    const offStop = window.agent?.onGlobalStop(() => engine.send({ type: "stop" }));
    const offBounds = window.agent?.onBounds((b) =>
      engine.send({ type: "ui_bounds", bounds: [b.x, b.y, b.width, b.height] }),
    );
    return () => {
      off();
      offStop?.();
      offBounds?.();
      engine.close();
    };
  }, []);

  useEffect(() => {
    bottom.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [s.items.length, s.runs]);

  const add = (item: ChatItem) => dispatch({ type: "add", item });
  // Saved tasks, metrics and permissions open in a sheet over the chat (closed with ×), not as chat messages.
  const [sheet, setSheet] = useState<null | "tasks" | "metrics" | "permissions" | "language">(null);
  const showTasks = () => {
    engine.send({ type: "list_tasks" });
    setSheet("tasks");
  };
  const showMetrics = () => setSheet("metrics");
  const clearChat = () => {
    dispatch({ type: "clearChat" });
    engine.send({ type: "clear_chat" }); // the engine's conversation memory too
  };
  const showPermissions = () => setSheet("permissions");
  const send = (text: string) => {
    add({ id: uid(), kind: "user", text });
    if (TASKS_RE.test(text.trim())) return showTasks();
    if (METRICS_RE.test(text.trim())) return showMetrics();
    dispatch({ type: "thinking" });
    engine.send({ type: "command", text });
  };
  const toggleTeach = () => engine.send({ type: s.recording ? "teach_stop" : "teach_start" });
  const saveRun = (run: RunView, name: string, script: string) => {
    saveTask(name, script, run.task);
    dispatch({ type: "patchRun", key: run.key, patch: { savedAs: name } });
  };
  // "agent save task": the latest finished run that can be saved, under the given or a default name.
  const saveLatest = (name: string) => {
    const latest = [...s.items]
      .reverse()
      .map((i) => (i.kind === "summary" ? s.runs[i.runKey] : undefined))
      .find((r) => r && !r.taskId && r.finalScript && r.status === "succeeded" && !r.savedAs);
    if (latest) saveRun(latest, name || latest.task.slice(0, 48), latest.finalScript!);
  };
  const answerQuestion = (item: Extract<ChatItem, { kind: "question" }>, value: string) => {
    engine.send({ type: "answer_user", id: item.qid, value });
    dispatch({ type: "patchItem", id: item.id, patch: { answer: value } });
    backToPillIfRunning();
  };
  const replyConfirm = (item: Extract<ChatItem, { kind: "confirm" }>, value: boolean | "all") => {
    engine.send({ type: "confirm_reply", id: item.qid, value });
    dispatch({ type: "patchItem", id: item.id, patch: { answer: value !== false } });
    if (value !== false) backToPillIfRunning();
  };
  // Spoken commands (engine/models/wake.py), done exactly as the matching button would.
  voiceRef.current = (action, text) => {
    if (action === "approve" && waiting?.kind === "confirm") replyConfirm(waiting, true);
    else if (action === "decline" && waiting?.kind === "confirm") replyConfirm(waiting, false);
    else if (action === "input") {
      if (waiting?.kind === "question") answerQuestion(waiting, matchOption(text, waiting.options));
      else if (!running && text) send(text);
    } else if (action === "send") composer.current?.submit();
    else if (action === "teach" && !s.recording) toggleTeach();
    else if (action === "teach_stop" && s.recording) toggleTeach();
    else if (action === "teach_cancel" && s.recording) engine.send({ type: "teach_cancel" });
    else if (action === "listen_off") wake.off();
    else if (action === "save") saveLatest(text);
  };
  const toggleReview = () => {
    engine.send({ type: "settings", auto_run: !s.autoRun });
    dispatch({ type: "setAutoRun", value: !s.autoRun });
  };
  const toggleSpeak = () => {
    engine.send({ type: "settings", speak: !s.speak });
    dispatch({ type: "setSpeak", value: !s.speak });
  };
  const chooseLanguage = (code: string) => {
    engine.send({ type: "settings", language: code });
    dispatch({ type: "setLanguage", value: code });
  };
  const toggleBypass = () => {
    engine.send({ type: "settings", bypass_approvals: !s.bypass });
    dispatch({ type: "setBypass", value: !s.bypass });
  };
  const saveTask = (name: string, script: string, description = "", source = "chat") =>
    engine.send({ type: "save_task", name, script, description, source });
  const runScript = (script: string) => engine.send({ type: "run_script", script });
  const runSaved = (id: number) => engine.send({ type: "run_saved", task_id: id });
  const backToPillIfRunning = () => setTimeout(() => runningRef.current && actingRef.current && goPill(), 350);

  const renderAgentItem = (item: ChatItem) => {
    switch (item.kind) {
      case "agent":
        return <AgentNote item={item} />;
      case "reply":
        return (
          <div className="selectable text-[14px] leading-relaxed text-fg">
            <Markdown text={item.text} />
          </div>
        );
      case "error":
        return <ErrorNote text={item.text} />;
      case "run": {
        const run = s.runs[item.runKey];
        if (!run) return null;
        const live = s.running && s.activeRun === run.key;
        return (
          <div className="space-y-2.5">
            {!run.draft && run.segments.length > 0 && (
              <div className="text-[14px] leading-relaxed">
                {run.taskId
                  ? live
                    ? t("Running your saved task.")
                    : t("Ran your saved task.")
                  : live
                    ? t("I wrote a program for this and I'm running it on your screen.")
                    : t("Here's the program I wrote and ran.")}
              </div>
            )}
            {run.draft && <div className="text-[14px] leading-relaxed">{t("Here's the program. Review it, then run it.")}</div>}
            <ScriptView run={run} onRun={runScript} onSave={(script, name) => saveTask(name, script, run.task)} />
            {!run.draft && <RunActivity run={run} status={tStatus(s.status)} live={live} />}
          </div>
        );
      }
      case "summary": {
        const run = s.runs[item.runKey];
        if (!run) return null;
        const task = run.taskId ? s.tasks.find((t) => t.id === run.taskId) : null;
        const done = task?.runs.filter((r) => r.status !== "running") ?? [];
        return (
          <SummaryCard
            run={run}
            firstRun={done[0]?.metrics}
            runNumber={done.length}
            onSave={(name, script) => saveRun(run, name, script)}
            onResume={run.runId ? () => engine.send({ type: "resume_run", run_id: run.runId }) : undefined}
          />
        );
      }
      case "result":
        return (
          <ResultCard
            result={item.result}
            onExport={(fmt) => engine.send({ type: "export", data: item.result, fmt, name: item.result.title || "result" })}
          />
        );
      case "question":
        return (
          <QuestionCard
            item={item}
            onAnswer={(value) => answerQuestion(item, value)}
          />
        );
      case "confirm":
        return (
          <ConfirmCard
            item={item}
            onReply={(value) => replyConfirm(item, value)}
          />
        );
      case "teach":
        return <TeachCard item={item} onRun={runScript} onSave={(name, script, d) => saveTask(name, script, d, "teach")} />;
      case "tasks":
        return (
          <TasksCard
            tasks={s.tasks}
            running={s.running}
            onRun={runSaved}
            onDelete={(id) => engine.send({ type: "delete_task", task_id: id })}
          />
        );
      case "permissions":
        return <PermissionsList />;
      case "metrics":
        return (
          <MetricsCard
            metrics={s.metrics}
            totals={s.totals}
            tasks={s.tasks}
            onClearCache={() => engine.send({ type: "clear_cache" })}
          />
        );
      default:
        return null;
    }
  };

  // Group consecutive assistant items into one turn with a single mark, like a chat transcript.
  const turns: { user?: ChatItem; agent: ChatItem[] }[] = [];
  for (const item of s.items) {
    if (item.kind === "user") turns.push({ user: item, agent: [] });
    else if (turns.length) turns[turns.length - 1].agent.push(item);
    else turns.push({ agent: [item] });
  }

  const empty = s.items.length === 0;
  const active = s.activeRun ? s.runs[s.activeRun] : undefined;
  const stageText = (() => {
    const st = active?.stages;
    if (!s.running || !st || st.length < 2) return "";
    const i = Math.min(active!.checkpoints.length, st.length - 1);
    return t("Stage {i} of {n}", { i: i + 1, n: st.length });
  })();
  const bar =
    mode === "panel" ? null : (
      <Pill
        running={s.running}
        status={tStatus(s.status)}
        metrics={s.metrics}
        connected={s.connected}
        stage={stageText}
        listening={wake.on}
        visible={mode !== "opening"}
        onOpen={goPanel}
      />
    );

  return (
    <>
      {mode !== "pill" && (
    <motion.div
      initial={{ opacity: 0, x: 32 }}
      animate={mode === "closing" ? { opacity: 0, x: 32 } : { opacity: 1, x: 0 }}
      transition={{ duration: TRANSITION_MS / 1000, ease: [0.2, 0.8, 0.2, 1] }}
      className="relative flex h-full flex-col border-l border-line bg-white text-fg"
    >
      {/* Header */}
      <div className={`flex h-12 shrink-0 items-center gap-2 px-3 transition-shadow ${scrolled ? "shadow-[0_1px_0_#efefef]" : ""}`}>
        <Logo size={22} />
        <span className="text-[15px] font-semibold tracking-tight">Deskwright</span>
        {!s.connected && (
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11.5px] text-fg-2">
            {s.engineDown ? t("Engine offline") : t("Connecting…")}
          </span>
        )}
        {s.bypass && (
          <button
            onClick={toggleBypass}
            title={t("Sensitive actions run without asking. Click to turn approvals back on.")}
            className="rounded-full bg-[#fef3c7] px-2 py-0.5 text-[11.5px] font-medium text-[#92400e]"
          >
            {t("Approvals off")}
          </button>
        )}
        {s.running && (
          <span className="flex items-center gap-1.5 text-[12px] text-fg-3">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-focus" /> {t("Working")}
          </span>
        )}
        <span className="flex-1" />
        <button
          onClick={() => clearChat()}
          title={t("New conversation")}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-fg-2 hover:bg-surface-2"
        >
          <SquarePen className="h-[18px] w-[18px]" strokeWidth={1.75} />
        </button>
        <Menu
          align="right"
          trigger={(open, toggle) => (
            <button
              onClick={toggle}
              title={t("More")}
              className={`flex h-8 w-8 items-center justify-center rounded-lg text-fg-2 hover:bg-surface-2 ${open ? "bg-surface-2" : ""}`}
            >
              <MoreHorizontal className="h-[18px] w-[18px]" strokeWidth={1.75} />
            </button>
          )}
          width={260}
          items={[
            { label: s.recording ? t("Finish demonstration") : t("Teach by demonstration"), icon: GraduationCap, onSelect: toggleTeach },
            { label: t("Saved tasks"), icon: LayoutList, hint: "/tasks", onSelect: showTasks },
            { label: t("Run metrics"), icon: BarChart3, hint: "/metrics", onSelect: showMetrics },
            { label: t("Permissions"), icon: KeyRound, onSelect: showPermissions },
            {
              label: t("Language"),
              icon: Languages,
              hint: LANGUAGES.find((l) => l.code === s.language)?.name,
              onSelect: () => setSheet("language"),
            },
            { kind: "separator" },
            { kind: "toggle", label: t("Listen for “Hey Agent”"), icon: Mic, checked: wake.on, onSelect: wake.toggle },
            {
              kind: "toggle",
              label: s.speak && s.voiceState === "loading" ? t("Speak out loud (loading voice…)") : t("Speak out loud"),
              icon: Volume2,
              checked: s.speak,
              onSelect: toggleSpeak,
            },
            { kind: "toggle", label: t("Review before running"), icon: ListChecks, checked: !s.autoRun, onSelect: toggleReview },
            { kind: "toggle", label: t("Skip approvals"), icon: ShieldOff, checked: s.bypass, onSelect: toggleBypass },
            { kind: "separator" },
            { label: t("Quit Deskwright"), icon: Power, onSelect: () => window.agent?.quit() },
          ]}
        />
        <button
          onClick={goPill}
          title={t("Collapse")}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-fg-2 hover:bg-surface-2"
        >
          <PanelRightClose className="h-[18px] w-[18px]" strokeWidth={1.75} />
        </button>
      </div>

      {/* Conversation */}
      <div ref={scroller} onScroll={(e) => setScrolled(e.currentTarget.scrollTop > 4)} className="scroll-y min-h-0 flex-1">
        {empty ? (
          <div className="flex min-h-full flex-col px-5 pb-6">
            <div className="flex flex-1 flex-col items-center justify-center pb-4 pt-6 text-center">
              <h1 className="font-serif text-[28px] font-normal leading-tight tracking-tight">{t("What should I do?")}</h1>
              <p className="mt-2 max-w-[300px] text-[13.5px] leading-relaxed text-fg-2">
                {t("Describe a task and I'll take control.")}
              </p>
            </div>
            <div className="space-y-4">
              <PermissionsCard />
            </div>
          </div>
        ) : (
          <div className="space-y-6 px-4 pb-6 pt-3">
            {turns.map((turn, i) => (
              <div key={turn.user?.id ?? turn.agent[0]?.id ?? i} className="space-y-4">
                {turn.user && turn.user.kind === "user" && <UserMessage text={turn.user.text} voice={turn.user.voice} />}
                {turn.agent.length > 0 && (
                  <AgentTurn>
                    {turn.agent.map((item) => (
                      <div key={item.id}>{renderAgentItem(item)}</div>
                    ))}
                  </AgentTurn>
                )}
              </div>
            ))}
            {s.thinking && (
              <AgentTurn>
                <span className="shimmer text-[13.5px]">{t("Thinking…")}</span>
              </AgentTurn>
            )}
            {s.teachStatus && (
              <AgentTurn>
                <span className="shimmer text-[13.5px]">{t(s.teachStatus)}…</span>
              </AgentTurn>
            )}
            <div ref={bottom} />
          </div>
        )}
      </div>

      <Composer
        apiRef={composer}
        onStop={() => engine.send({ type: "stop" })}
        running={s.running}
        recording={s.recording}
        reviewMode={!s.autoRun}
        bypass={s.bypass}
        wakeOn={wake.on}
        wakeState={wake.state}
        onToggleWake={wake.toggle}
        onSend={send}
        onTeach={toggleTeach}
        onCancelTeach={() => engine.send({ type: "teach_cancel" })}
        onShowTasks={showTasks}
        onShowMetrics={showMetrics}
        onToggleReview={toggleReview}
        onClear={() => clearChat()}
      />
      <AnimatePresence>
        {sheet && (
          <Sheet
            title={t(
              sheet === "tasks" ? "Saved tasks" : sheet === "metrics" ? "Run metrics" : sheet === "language" ? "Language" : "Permissions",
            )}
            onClose={() => setSheet(null)}
          >
            {sheet === "tasks" && (
              <TasksCard
                tasks={s.tasks}
                running={s.running}
                onRun={(id) => {
                  setSheet(null);
                  runSaved(id);
                }}
                onDelete={(id) => engine.send({ type: "delete_task", task_id: id })}
                onExport={(id) => engine.send({ type: "export_task", task_id: id })}
              />
            )}
            {sheet === "metrics" && (
              <MetricsCard
                metrics={s.metrics}
                totals={s.totals}
                tasks={s.tasks}
                onClearCache={() => engine.send({ type: "clear_cache" })}
              />
            )}
            {sheet === "permissions" && <PermissionsList />}
            {sheet === "language" && <LanguageList current={s.language} onChoose={chooseLanguage} />}
          </Sheet>
        )}
      </AnimatePresence>
    </motion.div>
      )}
      {bar}
    </>
  );
}
