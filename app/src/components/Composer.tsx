import { type MutableRefObject, useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, BarChart3, GraduationCap, LayoutList, ListChecks, Mic, Trash2 } from "lucide-react";
import type { WakeState } from "../lib/wake";

export interface SlashCommand {
  name: string;
  label: string;
  icon: any;
  run: () => void;
}

function useElapsed(active: boolean) {
  const [t, setT] = useState(0);
  useEffect(() => {
    if (!active) return setT(0);
    const start = Date.now();
    const id = setInterval(() => setT(Math.floor((Date.now() - start) / 1000)), 500);
    return () => clearInterval(id);
  }, [active]);
  return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
}

export function Composer({
  running,
  recording,
  reviewMode,
  bypass,
  wakeOn,
  wakeState,
  onToggleWake,
  onSend,
  onTeach,
  onShowTasks,
  onShowMetrics,
  onToggleReview,
  onClear,
  apiRef,
}: {
  apiRef?: MutableRefObject<{ submit: () => void } | null>;
  running: boolean;
  recording: boolean;
  reviewMode: boolean;
  bypass: boolean;
  wakeOn: boolean;
  wakeState: WakeState;
  onToggleWake: () => void;
  onSend: (text: string) => void;
  onTeach: () => void;
  onShowTasks: () => void;
  onShowMetrics: () => void;
  onToggleReview: () => void;
  onClear: () => void;
}) {
  const [text, setText] = useState("");
  const [sel, setSel] = useState(0);
  const ta = useRef<HTMLTextAreaElement>(null);
  const elapsed = useElapsed(recording);

  const commands: SlashCommand[] = [
    { name: "tasks", label: "Show saved tasks", icon: LayoutList, run: onShowTasks },
    { name: "metrics", label: "Show run metrics", icon: BarChart3, run: onShowMetrics },
    { name: "teach", label: "Teach by demonstration", icon: GraduationCap, run: onTeach },
    { name: "review", label: reviewMode ? "Run scripts right away" : "Review before running", icon: ListChecks, run: onToggleReview },
    { name: "clear", label: "Clear the conversation", icon: Trash2, run: onClear },
  ];
  const slash = text.startsWith("/") ? commands.filter((c) => c.name.startsWith(text.slice(1).trim().toLowerCase())) : [];

  useEffect(() => setSel(0), [text]);
  // Fit the box to its text. Measure again when its width changes: the panel can mount while the window is still
  // the narrow corner bar, where the placeholder wraps onto many lines.
  const fit = () => {
    const el = ta.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(200, el.scrollHeight) + "px";
  };
  useEffect(fit, [text]);
  useEffect(() => {
    const el = ta.current;
    if (!el) return;
    let width = el.clientWidth;
    const ro = new ResizeObserver(() => {
      if (el.clientWidth !== width) {
        width = el.clientWidth;
        fit();
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  if (apiRef) apiRef.current = { submit: () => submit() }; // "agent send" presses Send
  const submit = () => {
    if (slash.length) {
      slash[Math.min(sel, slash.length - 1)].run();
      setText("");
      return;
    }
    const t = text.trim();
    if (!t || running) return;
    onSend(t);
    setText("");
  };

  const placeholder = running
    ? "Working on it…"
    : wakeState === "command"
      ? "Listening… say the task"
      : wakeState === "hearing"
        ? "Hearing you…"
        : wakeOn
          ? "Say “Hey Agent…” or type a task"
          : "Ask Agent to do something";
  const hot = wakeState === "hearing" || wakeState === "command";

  return (
    <div className="no-drag relative px-3 pb-2 pt-1">
      <AnimatePresence>
        {recording && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            className="mb-2 flex items-center gap-2.5 rounded-2xl border border-[#f5d0d0] bg-[#fef6f6] px-3.5 py-2.5"
          >
            <span className="h-2 w-2 shrink-0 animate-rec rounded-full bg-bad" />
            <div className="min-w-0 flex-1">
              <div className="text-[13px] font-medium text-fg">Recording your demonstration · {elapsed}</div>
              <div className="text-[12px] text-fg-2">Do the task once in any app. Clicks on this panel aren't recorded.</div>
            </div>
            <button onClick={onTeach} className="h-8 shrink-0 rounded-full bg-fg px-3.5 text-[12.5px] font-medium text-white">
              Finish
            </button>
          </motion.div>
        )}
      </AnimatePresence>

      <AnimatePresence>
        {slash.length > 0 && (
          <motion.div
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.12 }}
            className="absolute bottom-[calc(100%-2px)] left-3 right-3 z-40 rounded-2xl bg-white p-1.5 shadow-pop"
          >
            {slash.map((c, i) => (
              <button
                key={c.name}
                onMouseEnter={() => setSel(i)}
                onClick={() => {
                  c.run();
                  setText("");
                }}
                className={`flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-[13.5px] ${
                  i === sel ? "bg-surface-2" : ""
                }`}
              >
                <c.icon className="h-4 w-4 text-fg-2" strokeWidth={1.75} />
                <span className="font-mono text-[12.5px] text-fg-2">/{c.name}</span>
                <span className="text-fg">{c.label}</span>
              </button>
            ))}
          </motion.div>
        )}
      </AnimatePresence>

      <div className="flex items-stretch gap-1.5 rounded-[24px] bg-white py-1.5 pl-2 pr-1.5 shadow-composer">
        <textarea
          ref={ta}
          rows={3}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            if (slash.length && (e.key === "ArrowDown" || e.key === "ArrowUp")) {
              e.preventDefault();
              setSel((s) => (s + (e.key === "ArrowDown" ? 1 : slash.length - 1)) % slash.length);
            } else if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          placeholder={placeholder}
          className="block max-h-[200px] min-h-[96px] flex-1 resize-none bg-transparent px-2.5 py-2 text-[14.5px] leading-[1.45] outline-none placeholder:text-fg-3"
        />
        {/* Mic on top, a tall Send below it */}
        <div className="flex w-9 shrink-0 flex-col gap-1.5">
          <button
            onClick={onToggleWake}
            title={wakeOn ? "Stop listening for “Hey Agent”" : "Listen for “Hey Agent”"}
            className={`relative flex h-9 w-9 shrink-0 items-center justify-center rounded-full transition ${
              wakeOn ? "bg-focus/10 text-focus" : "text-fg-2 hover:bg-surface-2"
            }`}
          >
            {hot && <span className="absolute inset-0 animate-ping rounded-full bg-focus/20" />}
            <Mic className="relative h-[18px] w-[18px]" strokeWidth={wakeOn ? 2.25 : 1.75} />
          </button>
          <button
            onClick={submit}
            disabled={!text.trim() || running}
            title="Send"
            className="flex min-h-9 w-9 flex-1 items-center justify-center rounded-full bg-fg text-white transition hover:bg-[#2b2b2b] disabled:bg-surface-3 disabled:text-fg-4"
          >
            <ArrowUp className="h-[18px] w-[18px]" strokeWidth={2.25} />
          </button>
        </div>
      </div>
      {(running || bypass) && (
        <div className="mt-1.5 text-center text-[11.5px] text-fg-3">
          {running ? "Press esc to stop" : "Approvals are off: sensitive actions run without asking."}
        </div>
      )}
    </div>
  );
}
