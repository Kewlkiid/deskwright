import { motion } from "framer-motion";
import { Mic, PanelRightOpen } from "lucide-react";
import type { Metrics } from "../lib/types";
import { Logo } from "./Logo";

/** Compact bar in the top-right corner: shown while a task runs, or when the panel is collapsed by hand.
 * While running there are no buttons: Esc stops the run and the panel reopens by itself at the end. */
export function Pill({
  running,
  status,
  metrics,
  connected,
  listening = false,
  visible = true,
  onOpen,
}: {
  running: boolean;
  status: string;
  metrics: Metrics | null;
  connected: boolean;
  listening?: boolean; // wake word on: say "stop" works too
  visible?: boolean;
  onOpen: () => void;
}) {
  if (!running) {
    return (
      <div className="pointer-events-none fixed right-[12px] top-[12px]">
        <motion.div
          initial={{ opacity: 0, scale: 0.92 }}
          animate={visible ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.92 }}
          transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
          style={{ transformOrigin: "top right" }}
          className="pointer-events-auto flex h-[58px] w-[86px] items-center justify-between rounded-[20px] border border-black/[.06] bg-white/95 pl-3 pr-2 shadow-[0_2px_6px_rgba(0,0,0,.06),0_10px_28px_rgba(0,0,0,.14)] backdrop-blur"
        >
          <Logo size={26} />
          <button
            onClick={onOpen}
            title={connected ? "Open panel" : "Open panel (connecting…)"}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-fg-2 hover:bg-surface-2"
          >
            <PanelRightOpen className="h-[18px] w-[18px]" strokeWidth={1.75} />
          </button>
        </motion.div>
      </div>
    );
  }
  return (
    <div className="pointer-events-none fixed right-[12px] top-[12px]">
      <motion.div
        initial={{ opacity: 0, scale: 0.92 }}
        animate={visible ? { opacity: 1, scale: 1 } : { opacity: 0, scale: 0.92 }}
        transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
        style={{ transformOrigin: "top right" }}
        className="pointer-events-auto flex h-[58px] w-[374px] items-center gap-3 rounded-[20px] border border-black/[.06] bg-white/95 pl-3 pr-4 shadow-[0_2px_6px_rgba(0,0,0,.06),0_10px_28px_rgba(0,0,0,.14)] backdrop-blur"
      >
        <span className="relative flex h-7 w-7 shrink-0 items-center justify-center">
          <span className="absolute inset-0 animate-ping rounded-full bg-focus/20" />
          <span className="h-2.5 w-2.5 rounded-full bg-focus" />
        </span>
        <div className="min-w-0 flex-1 leading-tight">
          <div className="shimmer truncate text-[13.5px]">{status || "Working…"}</div>
          <div className="mt-0.5 truncate text-[11.5px] text-fg-3">
            Press <kbd className="rounded border border-line bg-surface px-1 font-sans text-[10.5px] text-fg-2">esc</kbd>
            {listening ? " or say “stop”" : ""} to stop
            {metrics ? ` · ${metrics.model_calls} model calls${metrics.cache_hits ? `, ${metrics.cache_hits} cached` : ""}` : ""}
          </div>
                </div>
        {listening && (
          <span title="Listening: say “stop” to stop" className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-focus/10 text-focus">
            <Mic className="h-4 w-4" strokeWidth={2.25} />
          </span>
        )}
      </motion.div>
    </div>
  );
}
