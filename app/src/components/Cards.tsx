import { useState } from "react";
import { motion } from "framer-motion";
import { ArrowUp, Check, CircleSlash, Copy, FolderOpen, Mic, Save, Sparkles, TriangleAlert, X } from "lucide-react";
import type { ChatItem, Metrics, RunView } from "../lib/types";
import { ScriptView } from "./ScriptView";

const fade = { initial: { opacity: 0, y: 4 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.18 } };

export function UserMessage({ text, voice }: { text: string; voice?: boolean }) {
  return (
    <motion.div {...fade} className="flex justify-end pl-10">
      <div className="selectable whitespace-pre-wrap rounded-[20px] bg-surface-2 px-4 py-2.5 text-[14px] leading-[1.45]">
        {voice && <Mic className="-mt-0.5 mr-1.5 inline h-3.5 w-3.5 text-fg-3" strokeWidth={2} />}
        {text}
      </div>
    </motion.div>
  );
}

/** An assistant turn: the mark on the left, content on the right, no bubble. */
/** The agent's side of the conversation: plain, no avatar. */
export function AgentTurn({ children }: { children: React.ReactNode; mark?: boolean }) {
  return (
    <motion.div {...fade} className="min-w-0 space-y-2.5">
      {children}
    </motion.div>
  );
}

export function AgentNote({ item }: { item: Extract<ChatItem, { kind: "agent" }> }) {
  const Icon = item.icon === "copy" ? Copy : item.icon === "save" ? Save : item.icon === "sparkle" ? Sparkles : null;
  return (
    <div className="flex items-center gap-2 text-[13.5px] text-fg-2">
      {Icon && <Icon className="h-3.5 w-3.5" strokeWidth={1.75} />}
      <span>{item.text}</span>
      {item.path && (
        <button
          onClick={() => window.agent?.revealFile(item.path!)}
          className="inline-flex items-center gap-1 rounded-md px-1.5 py-0.5 text-fg underline-offset-2 hover:underline"
        >
          <FolderOpen className="h-3.5 w-3.5" strokeWidth={1.75} /> Show in Finder
        </button>
      )}
    </div>
  );
}

export function ErrorNote({ text }: { text: string }) {
  return (
    <div className="selectable flex gap-2 rounded-xl border border-[#f5d0d0] bg-[#fef6f6] px-3 py-2.5 text-[13px] text-bad">
      <TriangleAlert className="mt-[2px] h-3.5 w-3.5 shrink-0" />
      <span>{text}</span>
    </div>
  );
}

export function QuestionCard({
  item,
  onAnswer,
}: {
  item: Extract<ChatItem, { kind: "question" }>;
  onAnswer: (value: string) => void;
}) {
  const [text, setText] = useState("");
  const done = item.answer !== undefined || item.closed;
  return (
    <div className="space-y-2">
      <div className="selectable whitespace-pre-wrap text-[14px] leading-relaxed">{item.question}</div>
      {done ? (
        <div className="text-[13px] text-fg-3">{item.answer ? `You answered: ${item.answer}` : "No longer needed"}</div>
      ) : (
        <form
          className="flex items-center gap-1.5 rounded-2xl border border-line py-1 pl-3 pr-1 focus-within:border-fg-4"
          onSubmit={(e) => {
            e.preventDefault();
            onAnswer(text);
          }}
        >
          <input
            autoFocus
            value={text}
            onChange={(e) => setText(e.target.value)}
            className="h-8 flex-1 bg-transparent text-[14px] outline-none placeholder:text-fg-3"
            placeholder="Reply…"
          />
          <button className="flex h-8 w-8 items-center justify-center rounded-full bg-fg text-white">
            <ArrowUp className="h-4 w-4" strokeWidth={2.25} />
          </button>
        </form>
      )}
    </div>
  );
}

export function ConfirmCard({
  item,
  onReply,
}: {
  item: Extract<ChatItem, { kind: "confirm" }>;
  onReply: (value: boolean | "all") => void;
}) {
  const done = item.answer !== undefined || item.closed;
  if (done) {
    return (
      <div className="flex items-center gap-2 text-[13px] text-fg-3">
        {item.answer === true ? <Check className="h-3.5 w-3.5 text-ok" /> : <X className="h-3.5 w-3.5" />}
        {item.answer === true ? "Approved" : item.answer === false ? "Declined" : "Closed"}:{" "}
        <span className="truncate">{item.summary.split("\n")[0]}</span>
      </div>
    );
  }
  return (
    <div className="rounded-2xl border border-line p-3.5 shadow-[0_1px_2px_rgba(0,0,0,.04)]">
      <div className="text-[14px] font-medium">Approve this action?</div>
      <div className="selectable mt-1 whitespace-pre-wrap text-[13px] leading-relaxed text-fg-2">{item.summary}</div>
      <div className="mt-3 flex gap-2">
        <button
          autoFocus
          onClick={() => onReply(true)}
          className="h-8 rounded-full bg-fg px-4 text-[13px] font-medium text-white hover:bg-[#2b2b2b]"
        >
          Approve
        </button>
        <button onClick={() => onReply(false)} className="h-8 rounded-full border border-line px-4 text-[13px] hover:bg-surface">
          Decline
        </button>
        <button
          onClick={() => onReply("all")}
          className="ml-auto h-8 px-1 text-[12.5px] text-fg-2 underline-offset-2 hover:text-fg hover:underline"
        >
          Approve all this run
        </button>
      </div>
    </div>
  );
}

function fmtCost(c: number) {
  return c < 0.01 ? `$${c.toFixed(4)}` : `$${c.toFixed(3)}`;
}

export function SummaryCard({
  run,
  firstRun,
  runNumber,
  onSave,
}: {
  run: RunView;
  firstRun?: Partial<Metrics> | null;
  runNumber?: number;
  onSave: (name: string, script: string) => void;
}) {
  const [name, setName] = useState(run.task.slice(0, 48));
  const [open, setOpen] = useState(false);
  const [saved, setSaved] = useState(false);
  const m = run.metrics;
  const ok = run.status === "succeeded";
  const title = ok
    ? `Done in ${m ? m.elapsed.toFixed(1) : "?"}s`
    : run.status === "stopped"
      ? "Stopped"
      : run.status === "declined"
        ? "Stopped: you declined an action"
        : "Couldn't finish";
  const speedup =
    ok && firstRun?.elapsed && m && runNumber && runNumber > 1 && m.elapsed > 0 ? firstRun.elapsed / m.elapsed : null;
  const cheaper = ok && firstRun?.cost && m && runNumber && runNumber > 1 ? 1 - m.cost / firstRun.cost : null;

  return (
    <div className="space-y-2">
      <div className="flex items-center gap-2 text-[14px]">
        {ok ? (
          <Check className="h-4 w-4 text-ok" strokeWidth={2.5} />
        ) : (
          <CircleSlash className="h-4 w-4 text-fg-3" strokeWidth={2} />
        )}
        <span className="font-medium">{title}</span>
      </div>
      {run.error?.message && !ok && <div className="selectable text-[13px] text-fg-2">{run.error.message}</div>}
      {m && (
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-[12.5px] text-fg-2">
          <span>{m.steps} steps</span>
          <span>{m.model_calls} model calls</span>
          {m.cache_hits + m.cache_misses > 0 && <span>{Math.round(m.cache_hit_rate * 100)}% from cache</span>}
          <span>{fmtCost(m.cost)}</span>
          {m.fixes > 0 && (
            <span className="text-warn">
              {m.fixes_succeeded}/{m.fixes} self-fixes worked
            </span>
          )}
        </div>
      )}
      {speedup && speedup > 1.05 && (
        <div className="inline-flex items-center gap-1.5 rounded-full bg-[#fff4ed] px-2.5 py-1 text-[12.5px] text-cache">
          Run {runNumber}: {speedup.toFixed(1)}× faster
          {cheaper && cheaper > 0.05 ? `, ${Math.round(cheaper * 100)}% cheaper` : ""} than run 1
        </div>
      )}
      {m && m.calls_saved > 0 && !(speedup && speedup > 1.05) && (
        <div className="text-[12.5px] text-fg-3">
          The position cache skipped {m.calls_saved} model calls (about {m.time_saved.toFixed(0)}s, {fmtCost(m.cost_saved)}).
        </div>
      )}
      {!run.taskId && run.finalScript && ok && !saved && (
        <div>
          {open ? (
            <form
              className="flex items-center gap-2"
              onSubmit={(e) => {
                e.preventDefault();
                if (!name.trim()) return;
                onSave(name.trim(), run.finalScript!);
                setSaved(true);
              }}
            >
              <input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Name this task"
                className="h-8 flex-1 rounded-lg border border-line px-2.5 text-[13px] outline-none focus:border-fg-3"
              />
              <button className="h-8 rounded-lg bg-fg px-3 text-[13px] font-medium text-white">Save</button>
            </form>
          ) : (
            <button
              onClick={() => setOpen(true)}
              className="flex h-8 items-center gap-1.5 rounded-full border border-line px-3 text-[13px] hover:bg-surface"
            >
              <Save className="h-3.5 w-3.5" strokeWidth={1.75} /> Save as a reusable task
            </button>
          )}
        </div>
      )}
      {saved && <div className="text-[13px] text-fg-2">Saved. Say “run {name}” any time.</div>}
    </div>
  );
}

export function TeachCard({
  item,
  onSave,
  onRun,
}: {
  item: Extract<ChatItem, { kind: "teach" }>;
  onSave: (name: string, script: string, description: string) => void;
  onRun: (script: string) => void;
}) {
  const lines = item.script.split("\n");
  const run: RunView = {
    key: item.id,
    task: item.name,
    draft: true,
    status: "draft",
    checkpoints: [],
    trace: [],
    segments: [{ id: 0, lines, states: lines.map(() => "pending"), expects: {}, cached: {} }],
  };
  return (
    <div className="space-y-2.5">
      <div className="text-[14px] leading-relaxed">
        I watched your demonstration ({item.steps.length} steps) and turned it into a program. Recorded values became
        variables, so it can run on new records.
      </div>
      <ol className="space-y-1 text-[13px] text-fg-2">
        {item.steps.slice(0, 8).map((s) => (
          <li key={s.step} className="flex gap-2">
            <span className="w-4 shrink-0 text-right text-fg-3">{s.step}</span>
            <span className="min-w-0">
              {s.intent || s.kind}
              {s.element ? <span className="text-fg-3"> · {s.element}</span> : null}
            </span>
          </li>
        ))}
        {item.steps.length > 8 && <li className="pl-6 text-fg-3">and {item.steps.length - 8} more</li>}
      </ol>
      {item.problems.length > 0 && <ErrorNote text={`Needs a quick edit: ${item.problems.join("; ")}`} />}
      <ScriptView run={run} onRun={onRun} onSave={(script, name) => onSave(name, script, item.description)} />
    </div>
  );
}
