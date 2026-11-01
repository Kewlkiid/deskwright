import type { ChatItem, ElementInfo, Metrics, RunView, SavedTask, Segment } from "./types";

export interface State {
  connected: boolean;
  engineDown: boolean;
  items: ChatItem[];
  runs: Record<string, RunView>;
  activeRun: string | null;
  draftKey: string | null;
  running: boolean;
  status: string;
  element: ElementInfo | null;
  metrics: Metrics | null;
  tasks: SavedTask[];
  totals: { runs: number; success_rate: number; fix_success_rate: number } | null;
  recording: boolean;
  teachStatus: string;
  thinking: boolean; // a message was sent and the chat hasn't answered yet
  speak: boolean; // talking back on
  voiceState: string; // "off" | "loading" | "ready"
  speaking: boolean; // Deskwright is talking right now (the wake word stops listening meanwhile)
  autoRun: boolean;
  bypass: boolean; // approvals off: sensitive actions run without asking
  lastCacheHit: string | null;
}

export const initialState: State = {
  connected: false,
  engineDown: false,
  items: [],
  runs: {},
  activeRun: null,
  draftKey: null,
  running: false,
  status: "",
  element: null,
  metrics: null,
  tasks: [],
  totals: null,
  recording: false,
  teachStatus: "",
  thinking: false,
  speak: false,
  voiceState: "off",
  speaking: false,
  autoRun: true,
  bypass: false,
  lastCacheHit: null,
};

let seq = 0;
export const uid = (p = "i") => `${p}${Date.now().toString(36)}${(seq++).toString(36)}`;

function segment(id: number, script: string, extra: Partial<Segment> = {}): Segment {
  const lines = script.replace(/\s+$/, "").split("\n");
  return { id, lines, states: lines.map(() => "pending"), expects: {}, cached: {}, ...extra };
}

function updateRun(s: State, key: string | null, fn: (r: RunView) => RunView): State {
  if (!key || !s.runs[key]) return s;
  return { ...s, runs: { ...s.runs, [key]: fn(s.runs[key]) } };
}

function updateSeg(r: RunView, segId: number, fn: (g: Segment) => Segment): RunView {
  return { ...r, segments: r.segments.map((g) => (g.id === segId ? fn(g) : g)) };
}

function setLine(g: Segment, line: number, st: Segment["states"][number]): Segment {
  if (line < 1 || line > g.states.length) return g;
  const states = g.states.slice();
  if (st === "running") {
    for (let i = 0; i < states.length; i++) if (states[i] === "running") states[i] = "passed";
  }
  if (states[line - 1] === "failed" && st !== "failed") return g;
  states[line - 1] = st;
  return { ...g, states };
}

export type Action =
  | { type: "event"; msg: any }
  | { type: "add"; item: ChatItem }
  | { type: "patchItem"; id: string; patch: Partial<ChatItem> }
  | { type: "setAutoRun"; value: boolean }
  | { type: "setBypass"; value: boolean }
  | { type: "clearChat" }
  | { type: "thinking" }
  | { type: "setSpeak"; value: boolean }
  | { type: "patchRun"; key: string; patch: Partial<RunView> };

export function reducer(s: State, a: Action): State {
  switch (a.type) {
    case "add":
      return { ...s, items: [...s.items, a.item] };
    case "patchItem":
      return { ...s, items: s.items.map((i) => (i.id === a.id ? ({ ...i, ...a.patch } as ChatItem) : i)) };
    case "setBypass":
      return { ...s, bypass: a.value };
    case "setAutoRun":
      return { ...s, autoRun: a.value };
    case "clearChat":
      return { ...s, items: [], runs: {}, draftKey: null, thinking: false };
    case "thinking":
      return { ...s, thinking: true };
    case "setSpeak":
      return { ...s, speak: a.value };
    case "patchRun":
      return s.runs[a.key] ? { ...s, runs: { ...s.runs, [a.key]: { ...s.runs[a.key], ...a.patch } } } : s;
    case "event": {
      const next = onEvent(s, a.msg);
      // A run or draft starting means the chat handed over: stop showing "Thinking…".
      return ["run_started", "script_generated", "status"].includes(a.msg.type) && next.thinking ? { ...next, thinking: false } : next;
    }
  }
}

function onEvent(s: State, m: any): State {
  switch (m.type) {
    case "_connected":
      return { ...s, connected: true, engineDown: false };
    case "_disconnected":
      return { ...s, connected: false, running: false };
    case "_engine_down":
      return { ...s, connected: false, engineDown: true };
    case "hello":
      return {
        ...s,
        tasks: m.tasks || [],
        totals: m.totals,
        autoRun: m.settings?.auto_run ?? s.autoRun,
        bypass: !!m.settings?.bypass_approvals,
        speak: !!m.settings?.speak,
      };
    case "tasks":
      return { ...s, tasks: m.tasks || [] };
    case "status":
      return { ...s, status: m.text || "" };

    case "run_started": {
      const key = `run${m.run_id}`;
      const run: RunView = {
        key, task: m.task, draft: false, status: "running", segments: [], checkpoints: [], taskId: m.task_id, trace: [],
      };
      // A draft that is now running no longer needs its Run button.
      const runs = { ...s.runs, [key]: run };
      if (s.draftKey && runs[s.draftKey]) runs[s.draftKey] = { ...runs[s.draftKey], status: "succeeded" };
      return {
        ...s, runs, activeRun: key, draftKey: null, running: true, element: null, metrics: null,
        items: [...s.items, { id: uid(), kind: "run", runKey: key }],
      };
    }
    case "script_generated": {
      if (m.draft) {
        const key = uid("draft");
        const run: RunView = {
          key, task: m.task, draft: true, status: "draft", segments: [segment(0, m.script)], checkpoints: [], trace: [],
        };
        return {
          ...s, runs: { ...s.runs, [key]: run }, draftKey: key,
          items: [...s.items, { id: uid(), kind: "run", runKey: key }],
        };
      }
      return updateRun(s, s.activeRun, (r) => ({ ...r, segments: [segment(0, m.script)] }));
    }
    case "line_started":
      return updateRun(s, s.activeRun, (r) => updateSeg(r, m.segment, (g) => setLine(g, m.line, "running")));
    case "line_passed":
      return updateRun(s, s.activeRun, (r) => updateSeg(r, m.segment, (g) => setLine(g, m.line, "passed")));
    case "line_failed":
      return updateRun(s, s.activeRun, (r) =>
        updateSeg(r, m.segment, (g) => ({
          ...setLine(g, m.line, "failed"),
          failedLine: m.line,
          failure: { code: m.error?.code, message: m.error?.message, expect: m.expect, observation: m.observation },
        })),
      );
    case "line_rewritten":
      return updateRun(s, s.activeRun, (r) => {
        const prev = r.segments.find((g) => g.id === m.from_segment);
        const segs = r.segments.map((g) =>
          g.id === m.from_segment
            ? {
                ...g,
                states: g.states.map((st, i) => (i + 1 > (m.failed_line ?? 0) && st !== "passed" ? "superseded" : st)),
              }
            : g,
        );
        const fromLine = (prev ? m.failed_line : 0) as number;
        return {
          ...r,
          segments: [...segs, segment(m.segment, m.script, { explanation: m.explanation, fromLine, detour: !!m.detour })],
          finalScript: m.full_script,
        };
      });
    case "expect_met":
    case "expect_failed":
      if (m.line == null) return s;
      return updateRun(s, s.activeRun, (r) =>
        updateSeg(r, m.segment, (g) => ({
          ...g,
          expects: { ...g.expects, [m.line]: { text: m.expect, ok: m.type === "expect_met", observation: m.observation } },
        })),
      );
    case "cache_hit":
      return {
        ...updateRun(s, s.activeRun, (r) =>
          m.line == null ? r : updateSeg(r, m.segment, (g) => ({ ...g, cached: { ...g.cached, [m.line]: true } })),
        ),
        lastCacheHit: m.target,
      };
    case "element_found":
      return {
        ...updateRun(s, s.activeRun, (r) => ({
          ...r,
          trace: [...r.trace, { target: m.target, thumbnail: m.thumbnail, fromCache: !!m.from_cache, verb: m.verb }].slice(-24),
        })),
        element: m,
      };
    case "metrics":
      return { ...updateRun(s, s.activeRun, (r) => ({ ...r, metrics: m.metrics })), metrics: m.metrics };
    case "progress":
      return updateRun(s, s.activeRun, (r) => ({ ...r, progress: { done: m.done, total: m.total } }));
    case "progress_item":
      return updateRun(s, s.activeRun, (r) =>
        r.progress ? { ...r, progress: { ...r.progress, done: Math.min(r.progress.total, r.progress.done + 1) } } : r,
      );
    case "checkpoint":
      return updateRun(s, s.activeRun, (r) => ({ ...r, checkpoints: [...r.checkpoints, m.name] }));
    case "ask_user":
      return { ...s, items: [...s.items, { id: uid(), kind: "question", qid: m.id, question: m.question }] };
    case "confirm_request":
      return { ...s, items: [...s.items, { id: uid(), kind: "confirm", qid: m.id, summary: m.summary }] };
    case "question_closed":
      return {
        ...s,
        items: s.items.map((i) =>
          (i.kind === "question" || i.kind === "confirm") && i.qid === m.id ? { ...i, closed: true } : i,
        ),
      };
    case "result_ready":
      return { ...s, items: [...s.items, { id: uid(), kind: "result", result: m.result }] };
    case "run_finished": {
      const key = `run${m.run_id}`;
      let tasks = s.tasks;
      if (m.task_id) tasks = tasks.map((t) => (t.id === m.task_id ? { ...t, runs: m.history } : t));
      const next = updateRun(s, key, (r) => ({
        ...r,
        status: m.status,
        metrics: m.metrics,
        finalScript: m.final_script,
        error: m.error,
        taskId: m.task_id,
        segments: r.segments.map((g) => ({
          ...g,
          states: g.states.map((st) => (st === "running" ? (m.status === "succeeded" ? "passed" : "pending") : st)),
        })),
      }));
      return {
        ...next,
        tasks,
        totals: m.totals,
        running: false,
        status: "",
        metrics: m.metrics,
        items: [...next.items, { id: uid(), kind: "summary", runKey: key }],
      };
    }
    case "chat_reply":
      return { ...s, thinking: false, items: [...s.items, { id: uid(), kind: "reply", text: m.text }] };
    case "chat_done":
      return { ...s, thinking: false };
    case "voice_status":
      return { ...s, voiceState: m.state };
    case "speaking":
      return { ...s, speaking: !!m.on };
    case "task_updated":
      return { ...s, items: [...s.items, { id: uid(), kind: "agent", text: m.note, icon: "sparkle" }] };
    case "transcript":
      return { ...s, items: [...s.items, { id: uid(), kind: "user", text: m.text, voice: true }] };
    case "teach_recording":
      return {
        ...s,
        recording: !!m.recording,
        teachStatus: m.recording || m.cancelled ? "" : "Analysing your demonstration",
      };
    case "teach_request":
      // Another program wants a task the agent can't write on its own: the user shows it once.
      return {
        ...s,
        items: [
          ...s.items,
          {
            id: uid(),
            kind: "agent",
            icon: "sparkle",
            text: `A task was requested: ${String(m.describe).replace(/[.\s]+$/, "")}. Press ● and do it once, then ■. I'll save it as “${m.name || "the requested task"}”, and whoever asked can use it right away.`,
          },
        ],
      };
    case "teach_status":
      return { ...s, teachStatus: m.text };
    case "teach_compiled":
      return {
        ...s,
        teachStatus: "",
        items: [
          ...s.items,
          {
            id: uid(), kind: "teach", name: m.name, description: m.description, script: m.script, steps: m.steps,
            problems: m.problems || [],
          },
        ],
      };
    case "exported":
      return {
        ...s,
        items: [
          ...s.items,
          {
            id: uid(),
            kind: "agent",
            text:
              m.path === "clipboard"
                ? "Copied to the clipboard"
                : m.fmt === "py"
                  ? "Exported the task's code (run it from other apps with deskwright.py)"
                  : `Exported ${String(m.fmt).toUpperCase()}`,
            path: m.path === "clipboard" ? undefined : m.path,
            icon: m.path === "clipboard" ? "copy" : "save",
          },
        ],
      };
    case "wake_unavailable":
      return { ...s, items: [...s.items, { id: uid(), kind: "agent", text: m.message, icon: "sparkle" }] };
    case "error":
      return { ...s, items: [...s.items, { id: uid(), kind: "error", text: m.message }], teachStatus: "", thinking: false };
    default:
      return s;
  }
}
