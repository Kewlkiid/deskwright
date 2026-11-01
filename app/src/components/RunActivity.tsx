import { AnimatePresence, motion } from "framer-motion";
import { Zap } from "lucide-react";
import type { RunView } from "../lib/types";

/** Live line under the script while a run is active, plus a filmstrip of every element the agent grounded. */
export function RunActivity({
  run,
  status,
  live,
}: {
  run: RunView;
  status: string;
  live: boolean;
}) {
  const m = run.metrics;
  return (
    <div className="space-y-2">
      {run.trace.length > 0 && (
        <div className="scroll-x -mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1">
          <AnimatePresence initial={false}>
            {run.trace.map((t, i) => (
              <motion.div
                key={i}
                initial={{ opacity: 0, scale: 0.92 }}
                animate={{ opacity: 1, scale: 1 }}
                title={`${t.fromCache ? "From the position cache" : "Found by the vision models"}: ${t.target}`}
                className={`relative h-[46px] w-[66px] shrink-0 overflow-hidden rounded-lg border bg-surface ${
                  t.fromCache ? "border-[#f3c9b3]" : "border-line"
                }`}
              >
                {t.thumbnail && <img src={t.thumbnail} alt="" className="h-full w-full object-cover" />}
                <span
                  className={`absolute bottom-0.5 right-0.5 flex h-4 items-center gap-0.5 rounded px-1 text-[9.5px] font-semibold ${
                    t.fromCache ? "bg-cache text-white" : "bg-white/95 text-fg-2"
                  }`}
                >
                  {t.fromCache ? <Zap className="h-2.5 w-2.5 fill-white" /> : "AI"}
                </span>
              </motion.div>
            ))}
          </AnimatePresence>
        </div>
      )}
      {live && (
        <div className="flex items-center gap-2">
          <span className="shimmer min-w-0 flex-1 truncate text-[13.5px]">{status || "Working…"}</span>
          {m && (
            <span className="shrink-0 text-[12px] tabular-nums text-fg-3">
              {m.model_calls} calls{m.cache_hits ? ` · ${m.cache_hits} cached` : ""}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
