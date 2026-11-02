import type { RunView } from "../lib/types";
import { t as tr } from "../lib/i18n";

/** Live line under the script while a run is active (the elements it found are under the finished run). */
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
      {live && !/^(Writing the|Escribiendo el|Écriture du|Schreibe das|Escrevendo o)/.test(status) && (
        <div className="flex items-center gap-2">
          <span className="shimmer min-w-0 flex-1 truncate text-[13.5px]">{status || tr("Working…")}</span>
          {m && (
            <span className="shrink-0 text-[12px] tabular-nums text-fg-3">
              {tr("{n} calls", { n: m.model_calls })}
              {m.cache_hits ? ` · ${tr("{n} cached", { n: m.cache_hits })}` : ""}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
