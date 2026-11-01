import { motion } from "framer-motion";
import { PanelRightOpen, Square } from "lucide-react";
import type { Metrics } from "../lib/types";
import { Logo } from "./Logo";

/** Compact bar in the top-right corner: shown while a task runs, or when the panel is collapsed by hand. */
export function Pill({
  running,
  status,
  metrics,
  connected,
  onStop,
  onOpen,
}: {
  running: boolean;
  status: string;
  metrics: Metrics | null;
  connected: boolean;
  onStop: () => void;
  onOpen: () => void;
}) {
  return (
    <div className="fixed inset-0 flex items-start justify-end p-[6px]">
      <motion.div
        initial={{ opacity: 0, scale: 0.94, y: -6 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        transition={{ duration: 0.22, ease: [0.2, 0.8, 0.2, 1] }}
        style={{ transformOrigin: "top right" }}
        className="flex h-[58px] w-full items-center gap-3 rounded-[20px] border border-black/[.06] bg-white/95 pl-3 pr-2 shadow-[0_2px_6px_rgba(0,0,0,.06),0_10px_28px_rgba(0,0,0,.14)] backdrop-blur"
      >
        {running ? (
          <span className="relative flex h-7 w-7 shrink-0 items-center justify-center">
            <span className="absolute inset-0 animate-ping rounded-full bg-focus/20" />
            <span className="h-2.5 w-2.5 rounded-full bg-focus" />
          </span>
        ) : (
          <Logo size={26} />
        )}
        <div className="min-w-0 flex-1 leading-tight">
          {running ? (
            <>
              <div className="shimmer truncate text-[13.5px]">{status || "Working…"}</div>
              <div className="mt-0.5 truncate text-[11.5px] text-fg-3">
                Press <kbd className="rounded border border-line bg-surface px-1 font-sans text-[10.5px] text-fg-2">esc</kbd> to stop
                {metrics ? ` · ${metrics.model_calls} model calls${metrics.cache_hits ? `, ${metrics.cache_hits} cached` : ""}` : ""}
              </div>
            </>
          ) : (
            <>
              <div className="text-[13.5px] font-semibold tracking-tight">Agent</div>
              <div className="text-[11.5px] text-fg-3">{connected ? "Ready" : "Connecting…"}</div>
            </>
          )}
        </div>
        {running && (
          <button
            onClick={onStop}
            className="flex h-9 shrink-0 items-center gap-1.5 rounded-full bg-fg px-3.5 text-[13px] font-medium text-white hover:bg-[#2b2b2b]"
          >
            <Square className="h-2.5 w-2.5 fill-white" /> Stop
          </button>
        )}
        <button
          onClick={onOpen}
          title="Open panel"
          className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-fg-2 hover:bg-surface-2"
        >
          <PanelRightOpen className="h-[18px] w-[18px]" strokeWidth={1.75} />
        </button>
      </motion.div>
    </div>
  );
}
