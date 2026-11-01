import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { motion } from "framer-motion";
import {
  BarChart3, GraduationCap, KeyRound, LayoutList, ListChecks, Mic, MoreHorizontal, PanelRightClose, Power, ShieldOff,
  SquarePen,
} from "lucide-react";
import { engine } from "./lib/engine";
import { useWakeWord } from "./lib/wake";
import { initialState, reducer, uid } from "./lib/state";
import type { ChatItem } from "./lib/types";
import { AgentNote, AgentTurn, ConfirmCard, ErrorNote, QuestionCard, SummaryCard, TeachCard, UserMessage } from "./components/Cards";
import { Composer } from "./components/Composer";
import { MetricsCard, PermissionsCard, PermissionsList, TasksCard } from "./components/InlineCards";
import { Logo } from "./components/Logo";
import { Menu } from "./components/Menu";
import { Pill } from "./components/Pill";
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

export default function App() {
  const [s, dispatch] = useReducer(reducer, initialState);
  // "panel": full-height column. "pill": compact bar in the top-right corner (during tasks, or collapsed by hand).
  // panel <-> corner bar. The window itself resizes instantly (the bar sits at the same screen spot in both sizes,
  // so nothing visibly moves); all the motion is in the page: the panel slides while the bar fades in or out.
  const [mode, setModeState] = useState<"panel" | "closing" | "pill" | "opening">("panel");
  const modeRef = useRef<"panel" | "pill">("panel");
  const runningRef = useRef(false);
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
  // While a run is on the screen, utterances are only sent when it's waiting for an answer.
  const wake = useWakeWord(sendToEngine, running && !waiting);
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
        window.agent?.overlay(light);
      }
      if (msg.type === "wake_heard") wakeRef.current.heard();
      if (msg.type === "voice_action") voiceRef.current(msg.action, msg.text || "");
      if (msg.type === "wake_unavailable") wakeRef.current.off();
      if (msg.type === "run_started") {
        setRunningState(true);
        runningRef.current = true;
        window.agent?.setRunning(true);
        window.agent?.yieldFocus();
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
  const showTasks = () => {
    engine.send({ type: "list_tasks" });
    add({ id: uid(), kind: "tasks" });
  };
  const showMetrics = () => add({ id: uid(), kind: "metrics" });
  const showPermissions = () => add({ id: uid(), kind: "permissions" });
  const send = (text: string) => {
    add({ id: uid(), kind: "user", text });
    if (TASKS_RE.test(text.trim())) return showTasks();
    if (METRICS_RE.test(text.trim())) return showMetrics();
    engine.send({ type: "command", text });
  };
  const toggleTeach = () => engine.send({ type: s.recording ? "teach_stop" : "teach_start" });
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
      if (waiting?.kind === "question") answerQuestion(waiting, text);
      else if (!running && text) send(text);
    } else if (action === "send") composer.current?.submit();
    else if (action === "teach" && !s.recording) toggleTeach();
    else if (action === "teach_stop" && s.recording) toggleTeach();
    else if (action === "listen_off") wake.off();
  };
  const toggleReview = () => {
    engine.send({ type: "settings", auto_run: !s.autoRun });
    dispatch({ type: "setAutoRun", value: !s.autoRun });
  };
  const toggleBypass = () => {
    engine.send({ type: "settings", bypass_approvals: !s.bypass });
    dispatch({ type: "setBypass", value: !s.bypass });
  };
  const saveTask = (name: string, script: string, description = "", source = "chat") =>
    engine.send({ type: "save_task", name, script, description, source });
  const runScript = (script: string) => engine.send({ type: "run_script", script });
  const runSaved = (id: number) => engine.send({ type: "run_saved", task_id: id });
  const backToPillIfRunning = () => setTimeout(() => runningRef.current && goPill(), 350);

  const renderAgentItem = (item: ChatItem) => {
    switch (item.kind) {
      case "agent":
        return <AgentNote item={item} />;
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
                    ? "Running your saved task."
                    : "Ran your saved task."
                  : live
                    ? "I wrote a program for this and I'm running it on your screen."
                    : "Here's the program I wrote and ran."}
              </div>
            )}
            {run.draft && <div className="text-[14px] leading-relaxed">Here's the program. Review it, then run it.</div>}
            <ScriptView run={run} onRun={runScript} onSave={(script, name) => saveTask(name, script, run.task)} />
            {!run.draft && <RunActivity run={run} status={s.status} live={live} />}
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
            onSave={(name, script) => saveTask(name, script, run.task)}
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
  const bar =
    mode === "panel" ? null : (
      <Pill
        running={s.running}
        status={s.status}
        metrics={s.metrics}
        connected={s.connected}
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
      className="flex h-full flex-col border-l border-line bg-white text-fg"
    >
      {/* Header */}
      <div className={`flex h-12 shrink-0 items-center gap-2 px-3 transition-shadow ${scrolled ? "shadow-[0_1px_0_#efefef]" : ""}`}>
        <Logo size={22} />
        <span className="text-[15px] font-semibold tracking-tight">Agent</span>
        {!s.connected && (
          <span className="rounded-full bg-surface-2 px-2 py-0.5 text-[11.5px] text-fg-2">
            {s.engineDown ? "Engine offline" : "Connecting…"}
          </span>
        )}
        {s.bypass && (
          <button
            onClick={toggleBypass}
            title="Sensitive actions run without asking. Click to turn approvals back on."
            className="rounded-full bg-[#fef3c7] px-2 py-0.5 text-[11.5px] font-medium text-[#92400e]"
          >
            Approvals off
          </button>
        )}
        {s.running && (
          <span className="flex items-center gap-1.5 text-[12px] text-fg-3">
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-focus" /> Working
          </span>
        )}
        <span className="flex-1" />
        <button
          onClick={() => dispatch({ type: "clearChat" })}
          title="New conversation"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-fg-2 hover:bg-surface-2"
        >
          <SquarePen className="h-[18px] w-[18px]" strokeWidth={1.75} />
        </button>
        <Menu
          align="right"
          trigger={(open, toggle) => (
            <button
              onClick={toggle}
              title="More"
              className={`flex h-8 w-8 items-center justify-center rounded-lg text-fg-2 hover:bg-surface-2 ${open ? "bg-surface-2" : ""}`}
            >
              <MoreHorizontal className="h-[18px] w-[18px]" strokeWidth={1.75} />
            </button>
          )}
          width={260}
          items={[
            { label: s.recording ? "Finish demonstration" : "Teach by demonstration", icon: GraduationCap, onSelect: toggleTeach },
            { label: "Saved tasks", icon: LayoutList, hint: "/tasks", onSelect: showTasks },
            { label: "Run metrics", icon: BarChart3, hint: "/metrics", onSelect: showMetrics },
            { label: "Permissions", icon: KeyRound, onSelect: showPermissions },
            { kind: "separator" },
            { kind: "toggle", label: "Listen for “Hey Agent”", icon: Mic, checked: wake.on, onSelect: wake.toggle },
            { kind: "toggle", label: "Review before running", icon: ListChecks, checked: !s.autoRun, onSelect: toggleReview },
            { kind: "toggle", label: "Skip approvals", icon: ShieldOff, checked: s.bypass, onSelect: toggleBypass },
            { kind: "separator" },
            { label: "Quit Agent", icon: Power, onSelect: () => window.agent?.quit() },
          ]}
        />
        <button
          onClick={goPill}
          title="Collapse"
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
              <h1 className="font-serif text-[28px] font-normal leading-tight tracking-tight">What should I do?</h1>
              <p className="mt-2 max-w-[300px] text-[13.5px] leading-relaxed text-fg-2">
                Describe a task and I'll take control.
              </p>
            </div>
            <div className="space-y-4">
              <PermissionsCard />
              {s.tasks.length > 0 && (
                <div>
                  <div className="mb-1.5 px-1 text-[12px] text-fg-3">Saved tasks</div>
                  <div className="flex flex-wrap gap-1.5">
                    {s.tasks.slice(0, 4).map((t) => (
                      <button
                        key={t.id}
                        onClick={() => runSaved(t.id)}
                        className="rounded-full border border-line px-3 py-1.5 text-[13px] hover:bg-surface"
                      >
                        {t.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}
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
            {s.teachStatus && (
              <AgentTurn>
                <span className="shimmer text-[13.5px]">{s.teachStatus}…</span>
              </AgentTurn>
            )}
            <div ref={bottom} />
          </div>
        )}
      </div>

      <Composer
        apiRef={composer}
        running={s.running}
        recording={s.recording}
        reviewMode={!s.autoRun}
        bypass={s.bypass}
        wakeOn={wake.on}
        wakeState={wake.state}
        onToggleWake={wake.toggle}
        onSend={send}
        onTeach={toggleTeach}
        onShowTasks={showTasks}
        onShowMetrics={showMetrics}
        onToggleReview={toggleReview}
        onClear={() => dispatch({ type: "clearChat" })}
      />
    </motion.div>
      )}
      {bar}
    </>
  );
}
