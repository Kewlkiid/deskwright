import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, Copy, CornerDownRight, Pencil, Play, X, Zap } from "lucide-react";
import type { RunView, Segment } from "../lib/types";

const ROW: Record<string, string> = {
  pending: "text-fg-2",
  running: "bg-[#eff4ff] text-fg",
  passed: "text-fg",
  failed: "bg-[#fef2f2] text-fg",
  superseded: "text-fg-4 line-through decoration-fg-4/60",
};

function highlight(src: string) {
  // Light syntax colouring tuned for a white code block: strings, SDK calls, comments, keywords.
  const parts: { t: string; c: string }[] = [];
  const re =
    /(#.*$)|("(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|\b(for|in|if|else|elif|while|not|and|or|return|def|True|False|None)\b|\b([a-z_]+)(?=\()/g;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(src))) {
    if (m.index > last) parts.push({ t: src.slice(last, m.index), c: "" });
    if (m[1]) parts.push({ t: m[1], c: "text-fg-3 italic" });
    else if (m[2]) parts.push({ t: m[2], c: "text-[#0a7a4f]" });
    else if (m[3]) parts.push({ t: m[3], c: "text-[#a626a4]" });
    else parts.push({ t: m[4], c: "text-[#1f5fbf]" });
    last = m.index + m[0].length;
  }
  if (last < src.length) parts.push({ t: src.slice(last), c: "" });
  return parts.map((p, i) => (
    <span key={i} className={p.c}>
      {p.t}
    </span>
  ));
}

/** Wrapped continuation lines indent past the code's own indentation, like an editor's soft wrap. */
function hang(src: string) {
  const n = (src.match(/^ */)?.[0].length ?? 0) + 4;
  return { paddingLeft: `${n}ch`, textIndent: `-${n}ch` };
}

function Line({ seg, i, animate }: { seg: Segment; i: number; animate: boolean }) {
  const n = i + 1;
  const st = seg.states[i];
  const exp = seg.expects[n];
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (st === "running" || st === "failed") ref.current?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [st]);
  return (
    <motion.div
      ref={ref}
      initial={animate ? { opacity: 0, backgroundColor: "rgba(250, 204, 21, 0.22)" } : false}
      animate={{ opacity: 1, backgroundColor: "rgba(255,255,255,0)" }}
      transition={{ delay: animate ? i * 0.04 : 0, duration: 0.6 }}
    >
      <div className={`relative flex items-start transition-colors duration-200 ${ROW[st]}`}>
        {st === "running" && <span className="absolute inset-y-0 left-0 w-[2px] bg-focus" />}
        {st === "failed" && <span className="absolute inset-y-0 left-0 w-[2px] bg-bad" />}
        <span className="w-8 shrink-0 select-none pr-2 text-right font-mono text-[11px] leading-[22px] text-fg-4">{n}</span>
        <code
          className="min-w-0 flex-1 whitespace-pre-wrap break-words font-mono text-[12px] leading-[22px]"
          style={hang(seg.lines[i])}
        >
          {highlight(seg.lines[i])}
        </code>
        <span className="flex w-7 shrink-0 items-center justify-center pt-[5px]">
          {seg.cached[n] && st !== "failed" ? (
            <Zap className="h-3 w-3 fill-cache text-cache" aria-label="cached" />
          ) : st === "passed" ? (
            <Check className="h-3.5 w-3.5 text-ok" strokeWidth={2.5} />
          ) : st === "failed" ? (
            <X className="h-3.5 w-3.5 text-bad" strokeWidth={2.5} />
          ) : st === "running" ? (
            <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-focus" />
          ) : null}
        </span>
      </div>
      {exp && st !== "failed" && st !== "superseded" && (
        <div className={`pb-0.5 pl-8 text-[11.5px] ${exp.ok ? "text-ok" : "text-bad"}`}>
          {exp.ok ? "Verified" : "Not verified"}: {exp.text}
        </div>
      )}
      {st === "failed" && seg.failure && (
        <div className="bg-[#fef2f2] pb-2 pl-8 pr-3 text-[12px] leading-snug text-bad">
          {seg.failure.expect && (
            <div>
              <span className="text-bad/70">Expected</span> {seg.failure.expect}
            </div>
          )}
          {seg.failure.observation && (
            <div>
              <span className="text-bad/70">Saw</span> {seg.failure.observation}
            </div>
          )}
          {!seg.failure.expect && !seg.failure.observation && <div>{seg.failure.message}</div>}
        </div>
      )}
    </motion.div>
  );
}

export function ScriptView({
  run,
  onRun,
  onSave,
}: {
  run: RunView;
  onRun?: (script: string) => void;
  onSave?: (script: string, name: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [naming, setNaming] = useState(false);
  const [copied, setCopied] = useState(false);
  const [name, setName] = useState(run.task.slice(0, 48));
  const draftScript = run.segments[0]?.lines.join("\n") ?? "";
  const [text, setText] = useState(draftScript);
  useEffect(() => setText(draftScript), [draftScript]);
  const isDraft = run.draft && run.status === "draft";
  const script = editing ? text : draftScript;

  if (!run.segments.length) {
    return (
      <div className="rounded-xl border border-line px-4 py-3">
        <div className="shimmer text-[13.5px]">Writing the program…</div>
      </div>
    );
  }

  const fixes = run.segments.length - 1;
  const copy = () => {
    navigator.clipboard?.writeText(run.finalScript || run.segments.map((s) => s.lines.join("\n")).join("\n\n"));
    setCopied(true);
    setTimeout(() => setCopied(false), 1200);
  };

  return (
    <div className="overflow-hidden rounded-xl border border-line bg-white">
      <div className="flex h-9 items-center gap-2 border-b border-line-soft bg-surface px-3 text-[12px] text-fg-2">
        <span className="font-mono text-[11.5px] text-fg-2">python</span>
        {run.progress && run.progress.total > 0 && (
          <span className="text-fg-3">
            · {run.progress.done} of {run.progress.total} records
          </span>
        )}
        {fixes > 0 && (
          <span className="text-warn">
            · {fixes} {fixes === 1 ? "fix" : "fixes"}
          </span>
        )}
        <span className="flex-1" />
        {isDraft && !editing && (
          <button onClick={() => setEditing(true)} className="flex items-center gap-1 rounded-md px-1.5 py-1 hover:bg-surface-3">
            <Pencil className="h-3.5 w-3.5" strokeWidth={1.75} /> Edit
          </button>
        )}
        <button onClick={copy} className="flex items-center gap-1 rounded-md px-1.5 py-1 hover:bg-surface-3">
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" strokeWidth={1.75} />}
          {copied ? "Copied" : "Copy"}
        </button>
      </div>
      {editing ? (
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          spellCheck={false}
          className="h-60 w-full resize-none bg-white px-4 py-3 font-mono text-[12px] leading-[22px] text-fg outline-none"
        />
      ) : (
        <div className="scroll-y max-h-[320px] py-1.5">
          <AnimatePresence initial={false}>
            {run.segments.map((seg) => (
              <motion.div key={seg.id} initial={seg.id > 0 ? { opacity: 0 } : false} animate={{ opacity: 1 }}>
                {seg.id > 0 && (
                  <div className="my-1.5 flex items-start gap-2 border-y border-[#fde7c7] bg-[#fffbf3] px-3 py-1.5 text-[12px] leading-snug text-warn">
                    <CornerDownRight className="mt-[2px] h-3.5 w-3.5 shrink-0" />
                    <span>
                      <span className="font-medium">
                        {seg.detour
                          ? `Took a learned way back to line ${seg.fromLine}.`
                          : `Rewrote from line ${seg.fromLine} and resumed.`}
                      </span>{" "}
                      <span className="text-fg-2">{seg.explanation}</span>
                    </span>
                  </div>
                )}
                {seg.lines.map((_, i) => {
                  if (seg.states[i] !== "superseded") return <Line key={i} seg={seg} i={i} animate={seg.id > 0} />;
                  if (i > 0 && seg.states[i - 1] === "superseded") return null;
                  let n = 0;
                  while (seg.states[i + n] === "superseded") n++;
                  return (
                    <div key={i} className="py-0.5 pl-10 text-[11.5px] text-fg-3">
                      {n} {n === 1 ? "line" : "lines"} replaced by the rewrite below
                    </div>
                  );
                })}
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
      {isDraft &&
        (naming ? (
          <form
            className="flex items-center gap-2 border-t border-line-soft p-2"
            onSubmit={(e) => {
              e.preventDefault();
              if (!name.trim()) return;
              onSave?.(script, name.trim());
              setNaming(false);
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
            <button type="button" onClick={() => setNaming(false)} className="h-8 px-2 text-[13px] text-fg-2">
              Cancel
            </button>
          </form>
        ) : (
          <div className="flex items-center gap-2 border-t border-line-soft p-2">
            <button
              onClick={() => onRun?.(script)}
              className="flex h-8 items-center gap-1.5 rounded-lg bg-fg px-3 text-[13px] font-medium text-white hover:bg-[#2b2b2b]"
            >
              <Play className="h-3.5 w-3.5 fill-white" /> Run
            </button>
            <button
              onClick={() => setNaming(true)}
              className="h-8 rounded-lg border border-line px-3 text-[13px] text-fg hover:bg-surface"
            >
              Save as task
            </button>
            <span className="ml-auto text-[12px] text-fg-3">or say “start”</span>
          </div>
        ))}
    </div>
  );
}
