import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ArrowUp, BarChart3, Eye, GraduationCap, LayoutList, ListChecks, Mic, Plus, ShieldOff, Square, Trash2 } from "lucide-react";
import { Menu } from "./Menu";

export interface SlashCommand {
  name: string;
  label: string;
  icon: any;
  run: () => void;
}

async function blobToBase64(blob: Blob): Promise<string> {
  const buf = new Uint8Array(await blob.arrayBuffer());
  let s = "";
  for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return btoa(s);
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
  onToggleBypass,
  captureMuted,
  onSend,
  onStop,
  onAudio,
  onTeach,
  onShowTasks,
  onShowMetrics,
  onToggleReview,
  onToggleCapture,
  onClear,
}: {
  running: boolean;
  recording: boolean;
  reviewMode: boolean;
  bypass: boolean;
  onToggleBypass: () => void;
  captureMuted: boolean;
  onSend: (text: string) => void;
  onStop: () => void;
  onAudio: (b64: string, mime: string) => void;
  onTeach: () => void;
  onShowTasks: () => void;
  onShowMetrics: () => void;
  onToggleReview: () => void;
  onToggleCapture: () => void;
  onClear: () => void;
}) {
  const [text, setText] = useState("");
  const [listening, setListening] = useState(false);
  const [sel, setSel] = useState(0);
  const rec = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
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
  useEffect(() => {
    const el = ta.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = Math.min(168, el.scrollHeight) + "px";
  }, [text]);

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

  const toggleMic = async () => {
    if (listening) {
      rec.current?.stop();
      return;
    }
    try {
      await window.agent?.askMicrophone();
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mime = MediaRecorder.isTypeSupported("audio/webm;codecs=opus") ? "audio/webm;codecs=opus" : "audio/webm";
      const r = new MediaRecorder(stream, { mimeType: mime });
      chunks.current = [];
      r.ondataavailable = (e) => e.data.size && chunks.current.push(e.data);
      r.onstop = async () => {
        stream.getTracks().forEach((t) => t.stop());
        setListening(false);
        const blob = new Blob(chunks.current, { type: mime });
        if (blob.size > 1000) onAudio(await blobToBase64(blob), mime);
      };
      rec.current = r;
      r.start();
      setListening(true);
    } catch (e) {
      console.error("microphone", e);
      setListening(false);
    }
  };

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

      <div className="rounded-[26px] bg-white px-2 pb-2 pt-1 shadow-composer">
        <textarea
          ref={ta}
          rows={1}
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
          placeholder={listening ? "Listening…" : running ? "Working on it…" : "Ask Agent to do something"}
          className="block max-h-[168px] min-h-[44px] w-full resize-none bg-transparent px-2.5 pt-2.5 text-[14.5px] leading-[1.45] outline-none placeholder:text-fg-3"
        />
        <div className="flex items-center gap-1">
          <Menu
            side="top"
            width={260}
            trigger={(open, toggle) => (
              <button
                onClick={toggle}
                title="More"
                className={`flex h-9 w-9 items-center justify-center rounded-full text-fg-2 hover:bg-surface-2 ${open ? "bg-surface-2" : ""}`}
              >
                <Plus className="h-[18px] w-[18px]" strokeWidth={1.75} />
              </button>
            )}
            items={[
              { label: recording ? "Finish demonstration" : "Teach by demonstration", icon: GraduationCap, onSelect: onTeach },
              { label: "Saved tasks", icon: LayoutList, hint: "/tasks", onSelect: onShowTasks },
              { label: "Run metrics", icon: BarChart3, hint: "/metrics", onSelect: onShowMetrics },
              { kind: "separator" },
              { kind: "toggle", label: "Review before running", icon: ListChecks, checked: reviewMode, onSelect: onToggleReview },
              { kind: "toggle", label: "Skip approvals", icon: ShieldOff, checked: bypass, onSelect: onToggleBypass },
              { kind: "toggle", label: "Pause screen capture", icon: Eye, checked: captureMuted, onSelect: onToggleCapture },
            ]}
          />
          <span className="flex-1" />
          <button
            onClick={toggleMic}
            title={listening ? "Stop and send" : "Voice"}
            className={`flex h-9 w-9 items-center justify-center rounded-full transition ${
              listening ? "bg-[#fef2f2] text-bad" : "text-fg-2 hover:bg-surface-2"
            }`}
          >
            {listening ? <span className="h-2.5 w-2.5 animate-rec rounded-sm bg-bad" /> : <Mic className="h-[18px] w-[18px]" strokeWidth={1.75} />}
          </button>
          {running ? (
            <button
              onClick={onStop}
              title="Stop (⌘⇧X)"
              className="flex h-9 w-9 items-center justify-center rounded-full bg-fg text-white hover:bg-[#2b2b2b]"
            >
              <Square className="h-3 w-3 fill-white" />
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={!text.trim()}
              title="Send"
              className="flex h-9 w-9 items-center justify-center rounded-full bg-fg text-white transition hover:bg-[#2b2b2b] disabled:bg-surface-3 disabled:text-fg-4"
            >
              <ArrowUp className="h-[18px] w-[18px]" strokeWidth={2.25} />
            </button>
          )}
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
