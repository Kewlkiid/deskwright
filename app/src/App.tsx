import { useCallback, useEffect, useReducer, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ArrowUpRight, BarChart3, LayoutList, MoreHorizontal, PanelRightClose, Power, SquarePen } from "lucide-react";
import { engine } from "./lib/engine";
import { initialState, reducer, uid } from "./lib/state";
import type { ChatItem } from "./lib/types";
import { AgentNote, AgentTurn, ConfirmCard, ErrorNote, QuestionCard, SummaryCard, TeachCard, UserMessage } from "./components/Cards";
import { Composer } from "./components/Composer";
import { MetricsCard, PermissionsCard, TasksCard } from "./components/InlineCards";
import { Logo } from "./components/Logo";
import { Menu } from "./components/Menu";
import { Pill } from "./components/Pill";
import { ResultCard } from "./components/ResultCard";
import { RunActivity } from "./components/RunActivity";
import { ScriptView } from "./components/ScriptView";

const SUGGESTIONS = [
  "Create an invoice for every row in the orders table",
  "Copy the orders table into a new spreadsheet",
  "Summarize the page I'm looking at",
];

// Engine events that drive the on-screen overlay (grounding box, clicks, verdicts).
const OVERLAY_EVENTS = new Set([
  "run_started", "script_generated", "vision_scan", "sam_mask", "element_found", "vision_miss",
  "pointer", "expect_met", "expect_failed", "line_failed", "line_rewritten", "detour", "confirm_request", "run_finished",
]);

const TASKS_RE = /^(show |list |open )?(my )?(saved )?tasks\??$/i;
const METRICS_RE = /^(show )?(the )?(run )?(metrics|stats|statistics)\??$/i;

export default function App() {
  const [s, dispatch] = useReducer(reducer, initialState);
  // "panel": full-height column. "pill": compact bar in the top-right corner (during tasks, or collapsed by hand).
  const [mode, setModeState] = useState<"panel" | "pill">("panel");
  const modeRef = useRef(mode);
  const runningRef = useRef(false);
  const goPill = useCallback(() => {
    if (modeRef.current === "pill") return;
    modeRef.current = "pill";
    setModeState("pill"); // render the pill first (anchored top-right), then shrink the window around it
    window.agent?.setMode("pill");
  }, []);
  const goPanel = useCallback(() => {
    if (modeRef.current === "panel") return;
    modeRef.current = "panel";
    window.agent?.setMode("panel"); // grow the window first, then slide the panel in
    setTimeout(() => setModeState("panel"), 200);
  }, []);
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
      if (msg.type === "run_started") {
        runningRef.current = true;
        window.agent?.setRunning(true);
        window.agent?.yieldFocus();
        goPill();
      }
      if (msg.type === "run_finished") {
        runningRef.current = false;
        window.agent?.setRunning(false);
        goPanel();
      }
      // The run needs you: open the panel for the approval or question, then tuck away again.
      if (msg.type === "confirm_request" || msg.type === "ask_user") goPanel();
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
  const send = (text: string) => {
    add({ id: uid(), kind: "user", text });
    if (TASKS_RE.test(text.trim())) return showTasks();
    if (METRICS_RE.test(text.trim())) return showMetrics();
    engine.send({ type: "command", text });
  };
  const stop = () => engine.send({ type: "stop" });
  const toggleTeach = () => engine.send({ type: s.recording ? "teach_stop" : "teach_start" });
  const toggleReview = () => {
    engine.send({ type: "settings", auto_run: !s.autoRun });
    dispatch({ type: "setAutoRun", value: !s.autoRun });
  };
  const toggleBypass = () => {
    engine.send({ type: "settings", bypass_approvals: !s.bypass });
    dispatch({ type: "setBypass", value: !s.bypass });
  };
  const toggleCapture = () => engine.send({ type: "set_capture_paused", paused: !s.captureMuted });
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
            onAnswer={(value) => {
              engine.send({ type: "answer_user", id: item.qid, value });
              dispatch({ type: "patchItem", id: item.id, patch: { answer: value } });
              backToPillIfRunning();
            }}
          />
        );
      case "confirm":
        return (
          <ConfirmCard
            item={item}
            onReply={(value) => {
              engine.send({ type: "confirm_reply", id: item.qid, value });
              dispatch({ type: "patchItem", id: item.id, patch: { answer: value !== false } });
              if (value !== false) backToPillIfRunning();
            }}
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

  if (mode === "pill") {
    return (
      <Pill running={s.running} status={s.status} metrics={s.metrics} connected={s.connected} onStop={stop} onOpen={goPanel} />
    );
  }

  const empty = s.items.length === 0;

  return (
    <motion.div
      initial={{ opacity: 0, x: 24 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.24, ease: [0.2, 0.8, 0.2, 1] }}
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
          width={220}
          trigger={(open, toggle) => (
            <button
              onClick={toggle}
              title="More"
              className={`flex h-8 w-8 items-center justify-center rounded-lg text-fg-2 hover:bg-surface-2 ${open ? "bg-surface-2" : ""}`}
            >
              <MoreHorizontal className="h-[18px] w-[18px]" strokeWidth={1.75} />
            </button>
          )}
          items={[
            { label: "Saved tasks", icon: LayoutList, onSelect: showTasks },
            { label: "Run metrics", icon: BarChart3, onSelect: showMetrics },
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
                Describe a task. I'll write a program for it, run it on your screen, and fix my own code if something
                changes.
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
              <div>
                <div className="mb-1 px-1 text-[12px] text-fg-3">Try</div>
                <div className="divide-y divide-line-soft">
                  {SUGGESTIONS.map((t) => (
                    <button
                      key={t}
                      onClick={() => send(t)}
                      className="group flex w-full items-center gap-2 rounded-lg px-1 py-2.5 text-left text-[13.5px] text-fg-2 hover:text-fg"
                    >
                      <span className="flex-1">{t}</span>
                      <ArrowUpRight className="h-4 w-4 text-fg-4 transition group-hover:text-fg" strokeWidth={1.75} />
                    </button>
                  ))}
                </div>
              </div>
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
        running={s.running}
        recording={s.recording}
        reviewMode={!s.autoRun}
        bypass={s.bypass}
        onToggleBypass={toggleBypass}
        captureMuted={s.captureMuted}
        onSend={send}
        onStop={stop}
        onAudio={(data, mime) => engine.send({ type: "audio", data, mime })}
        onTeach={toggleTeach}
        onShowTasks={showTasks}
        onShowMetrics={showMetrics}
        onToggleReview={toggleReview}
        onToggleCapture={toggleCapture}
        onClear={() => dispatch({ type: "clearChat" })}
      />
    </motion.div>
  );
}
