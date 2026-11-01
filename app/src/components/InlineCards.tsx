// Saved tasks, metrics and permissions, shown as cards inside the conversation instead of separate tabs.
import { useEffect, useState } from "react";
import { Check, ChevronRight, GraduationCap, Play, Trash2 } from "lucide-react";
import type { Metrics, PermissionKind, Permissions, SavedTask } from "../lib/types";
import { RunChart } from "./RunChart";

export function TasksCard({
  tasks,
  running,
  onRun,
  onDelete,
}: {
  tasks: SavedTask[];
  running: boolean;
  onRun: (id: number) => void;
  onDelete: (id: number) => void;
}) {
  const [open, setOpen] = useState<number | null>(null);
  if (!tasks.length) {
    return (
      <div className="text-[14px] leading-relaxed text-fg-2">
        No saved tasks yet. Save a finished run, or teach me one: open the + menu and choose{" "}
        <span className="text-fg">Teach by demonstration</span>.
      </div>
    );
  }
  return (
    <div className="space-y-2">
      <div className="text-[14px]">Your saved tasks</div>
      <div className="divide-y divide-line-soft overflow-hidden rounded-xl border border-line">
        {tasks.map((t) => {
          const runs = t.runs.filter((r) => r.status !== "running");
          const first = runs[0]?.metrics;
          const last = runs[runs.length - 1]?.metrics;
          const speedup = runs.length > 1 && first?.elapsed && last?.elapsed ? first.elapsed / last.elapsed : null;
          const isOpen = open === t.id;
          return (
            <div key={t.id}>
              <div className="flex items-center gap-2 px-3 py-2.5">
                <button onClick={() => setOpen(isOpen ? null : t.id)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                  <ChevronRight
                    className={`h-3.5 w-3.5 shrink-0 text-fg-3 transition-transform ${isOpen ? "rotate-90" : ""}`}
                  />
                  <span className="min-w-0">
                    <span className="flex items-center gap-1.5 truncate text-[13.5px] font-medium">
                      {t.name}
                      {t.source === "teach" && <GraduationCap className="h-3.5 w-3.5 text-fg-3" strokeWidth={1.75} />}
                    </span>
                    <span className="block truncate text-[12px] text-fg-3">
                      {runs.length} {runs.length === 1 ? "run" : "runs"}
                      {t.versions.length > 1 ? ` · v${t.versions.length}` : ""}
                      {t.detours ? ` · ${t.detours} ${t.detours === 1 ? "way" : "ways"} back learned` : ""}
                      {speedup && speedup > 1.05 ? ` · now ${speedup.toFixed(1)}× faster` : ""}
                    </span>
                  </span>
                </button>
                <button
                  disabled={running}
                  onClick={() => onRun(t.id)}
                  className="flex h-7 items-center gap-1 rounded-full bg-fg px-3 text-[12px] font-medium text-white hover:bg-[#2b2b2b] disabled:opacity-30"
                >
                  <Play className="h-3 w-3 fill-white" /> Run
                </button>
              </div>
              {isOpen && (
                <div className="space-y-2 bg-surface px-3 pb-3 pt-1">
                  <div className="flex items-center gap-3 text-[11.5px] text-fg-3">
                    <span className="flex items-center gap-1">
                      <i className="h-2 w-2 rounded-sm bg-fg" /> time
                    </span>
                    <span className="flex items-center gap-1">
                      <i className="h-0.5 w-3 bg-cache" /> cost
                    </span>
                  </div>
                  <RunChart runs={t.runs} height={120} />
                  <pre className="selectable scroll-y max-h-36 overflow-auto rounded-lg border border-line-soft bg-white p-2.5 font-mono text-[11px] leading-[18px] text-fg-2">
                    {t.script}
                  </pre>
                  <div className="flex items-center justify-between text-[12px] text-fg-3">
                    <span>{t.versions.length > 1 ? `Latest: ${t.versions[t.versions.length - 1].note}` : "Original version"}</span>
                    <button onClick={() => onDelete(t.id)} className="flex items-center gap-1 hover:text-bad">
                      <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} /> Delete
                    </button>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="px-3 py-2.5">
      <div className="text-[12px] text-fg-3">{label}</div>
      <div className="mt-0.5 text-[17px] font-semibold tabular-nums tracking-tight">{value}</div>
      {sub && <div className="truncate text-[11.5px] text-fg-3">{sub}</div>}
    </div>
  );
}

export function MetricsCard({
  metrics,
  totals,
  tasks,
  onClearCache,
}: {
  metrics: Metrics | null;
  totals: { runs: number; success_rate: number; fix_success_rate: number } | null;
  tasks: SavedTask[];
  onClearCache: () => void;
}) {
  const m = metrics;
  const withRuns = tasks.filter((t) => t.runs.length > 1);
  return (
    <div className="space-y-3">
      <div className="text-[14px]">{m ? "Here's how the last run went." : "No runs yet this session."}</div>
      {m && (
        <div className="grid grid-cols-3 divide-x divide-y divide-line-soft overflow-hidden rounded-xl border border-line [&>*:nth-child(-n+3)]:border-t-0">
          <Stat label="Time" value={`${m.elapsed.toFixed(1)}s`} sub={`${m.model_time.toFixed(1)}s in models`} />
          <Stat label="Cost" value={`$${m.cost.toFixed(3)}`} />
          <Stat label="Steps" value={String(m.steps)} />
          <Stat
            label="Model calls"
            value={String(m.model_calls)}
            sub={Object.entries(m.calls_by_role || {}).map(([k, v]) => `${k} ${v}`).join(", ")}
          />
          <Stat label="From cache" value={`${Math.round(m.cache_hit_rate * 100)}%`} sub={`${m.calls_saved} calls skipped`} />
          <Stat label="Self-fixes" value={`${m.fixes_succeeded}/${m.fixes}`} sub="worked / tried" />
        </div>
      )}
      {totals && totals.runs > 0 && (
        <div className="text-[13px] text-fg-2">
          Across all {totals.runs} runs: {Math.round(totals.success_rate * 100)}% succeeded, and{" "}
          {Math.round(totals.fix_success_rate * 100)}% of self-fixes worked.
        </div>
      )}
      {withRuns.map((t) => (
        <div key={t.id} className="rounded-xl border border-line p-3">
          <div className="mb-1 text-[13px] font-medium">{t.name}</div>
          <RunChart runs={t.runs} height={120} />
        </div>
      ))}
      <button onClick={onClearCache} className="text-[12.5px] text-fg-3 underline-offset-2 hover:text-fg hover:underline">
        Clear the position cache
      </button>
    </div>
  );
}

const PERM_KEY = "agent.permissions.dismissed";

export function PermissionsCard() {
  const [perm, setPerm] = useState<Permissions | null>(null);
  const [dismissed, setDismissed] = useState(() => {
    try {
      return localStorage.getItem(PERM_KEY) === "1";
    } catch {
      return false;
    }
  });
  useEffect(() => {
    let alive = true;
    const poll = () => window.agent?.permissions().then((p) => alive && setPerm(p));
    poll();
    const t = setInterval(poll, 3000);
    return () => {
      alive = false;
      clearInterval(t);
    };
  }, []);
  if (!perm || perm.platform !== "darwin" || dismissed) return null;
  const ready = perm.screen === "granted" && perm.accessibility;
  if (ready && !perm.restart) return null; // everything the agent needs is on: nothing to show
  const rows = [
    { ok: perm.screen === "granted", label: "Screen Recording", why: "to see your screen", act: () => {
        window.agent?.askScreen();
        window.agent?.openPermission("screen");
      } },
    {
      ok: perm.accessibility,
      label: "Accessibility",
      why: "to move the mouse and type",
      act: () => {
        window.agent?.askAccessibility();
        window.agent?.openPermission("accessibility");
      },
    },
    { ok: perm.microphone === "granted", label: "Microphone", why: "for voice, optional", act: () => window.agent?.askMicrophone() },
    { ok: null, label: "Input Monitoring", why: "for teach mode", act: () => window.agent?.openPermission("input") },
  ];
  const required = rows[0].ok && rows[1].ok;
  return (
    <div className="rounded-2xl border border-line p-3.5 text-left">
      <div className="text-[14px] font-medium">Before the first run</div>
      <div className="mt-0.5 text-[13px] text-fg-2">
        macOS needs to allow this app to see and control the screen. Restart the app after granting.
      </div>
      <div className="mt-2.5 space-y-0.5">
        {rows.map((r) => (
          <button
            key={r.label}
            onClick={r.act}
            className="flex w-full items-center gap-2.5 rounded-lg px-1.5 py-1.5 text-left hover:bg-surface"
          >
            <span
              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                r.ok ? "border-ok bg-ok" : "border-fg-4"
              }`}
            >
              {r.ok && <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />}
            </span>
            <span className="text-[13px]">{r.label}</span>
            <span className="truncate text-[12px] text-fg-3">{r.why}</span>
            {!r.ok && <span className="ml-auto text-[12px] text-fg-2">Open</span>}
          </button>
        ))}
      </div>
      {perm.restart && (
        <div className="mt-2.5 flex items-center gap-3 rounded-xl bg-[#f0fdf4] px-3 py-2.5">
          <span className="flex-1 text-[12.5px] text-fg-2">
            Screen Recording is on. macOS applies it after Deskwright restarts.
          </span>
          <button
            onClick={() => window.agent?.relaunch()}
            className="h-8 shrink-0 rounded-full bg-fg px-3.5 text-[12.5px] font-medium text-white hover:bg-[#2b2b2b]"
          >
            Restart Deskwright
          </button>
        </div>
      )}
      <div className="mt-2 flex items-center justify-between border-t border-line-soft pt-2.5 text-[12px] text-fg-3">
        <span>Tip: turn on Do Not Disturb so notifications stay out of screenshots.</span>
        {required && (
          <button
            onClick={() => {
              try {
                localStorage.setItem(PERM_KEY, "1");
              } catch {}
              setDismissed(true);
            }}
            className="shrink-0 pl-2 text-fg underline-offset-2 hover:underline"
          >
            Done
          </button>
        )}
      </div>
    </div>
  );
}

/** Every macOS permission Deskwright uses: whether it's allowed, a way to allow it, and a way to take it back. */
export function PermissionsList() {
  const [perm, setPerm] = useState<Permissions | null>(null);
  const [busy, setBusy] = useState<PermissionKind | null>(null);
  const [note, setNote] = useState("");
  const poll = () => window.agent?.permissions().then(setPerm);
  useEffect(() => {
    poll();
    const t = setInterval(poll, 3000);
    return () => clearInterval(t);
  }, []);
  if (!perm) return <div className="text-[13px] text-fg-3">Checking permissions…</div>;
  if (perm.platform !== "darwin") return <div className="text-[13px] text-fg-2">Permissions are only needed on macOS.</div>;

  const rows: { kind: PermissionKind; label: string; why: string; ok: boolean | null; ask: () => void }[] = [
    { kind: "screen", label: "Screen Recording", why: "see your screen (required)", ok: perm.screen === "granted",
      ask: () => { window.agent?.askScreen(); window.agent?.openPermission("screen"); } },
    { kind: "accessibility", label: "Accessibility", why: "move the mouse and type (required)", ok: perm.accessibility,
      ask: () => { window.agent?.askAccessibility(); window.agent?.openPermission("accessibility"); } },
    { kind: "microphone", label: "Microphone", why: "hear “Hey Agent”", ok: perm.microphone === "granted",
      ask: () => window.agent?.askMicrophone().then(poll) },
    { kind: "speech", label: "Speech Recognition", why: "understand speech on this Mac",
      ok: perm.speech === "granted" ? true : perm.speech === "denied" ? false : null,
      ask: () => window.agent?.openPermission("speech") },
    { kind: "input", label: "Input Monitoring", why: "record your demonstrations in teach mode", ok: perm.input ?? null,
      ask: () => window.agent?.openPermission("input") },
    { kind: "automation", label: "Automation", why: "open and switch apps", ok: null,
      ask: () => window.agent?.openPermission("automation") },
  ];

  const revoke = async (kind: PermissionKind, label: string) => {
    setBusy(kind);
    const ok = await window.agent?.revokePermission(kind);
    setBusy(null);
    setNote(ok ? `${label} was taken back. macOS asks again the next time Deskwright needs it.` : `Couldn't change ${label}; use System Settings.`);
    poll();
  };

  return (
    <div className="rounded-2xl border border-line p-3.5 text-left">
      <div className="text-[14px] font-medium">Permissions</div>
      <div className="mt-0.5 text-[12.5px] text-fg-2">What macOS lets Deskwright do. Changes to Screen Recording and Accessibility apply after a restart.</div>
      <div className="mt-2.5 divide-y divide-line-soft">
        {rows.map((r) => (
          <div key={r.kind} className="flex items-center gap-2.5 py-2">
            <span
              className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                r.ok ? "border-ok bg-ok" : r.ok === false ? "border-bad" : "border-fg-4"
              }`}
            >
              {r.ok && <Check className="h-2.5 w-2.5 text-white" strokeWidth={3} />}
            </span>
            <div className="min-w-0 flex-1 leading-tight">
              <div className="text-[13px]">{r.label}</div>
              <div className="truncate text-[11.5px] text-fg-3">
                {r.ok ? "Allowed" : r.ok === false ? "Not allowed" : "Not asked yet"} · {r.why}
              </div>
            </div>
            {r.ok ? (
              <button
                disabled={busy === r.kind}
                onClick={() => revoke(r.kind, r.label)}
                className="h-7 shrink-0 rounded-full border border-line px-2.5 text-[12px] text-fg-2 hover:bg-surface disabled:opacity-50"
              >
                {busy === r.kind ? "…" : "Revoke"}
              </button>
            ) : (
              <button
                onClick={r.ask}
                className="h-7 shrink-0 rounded-full bg-fg px-2.5 text-[12px] font-medium text-white hover:bg-[#2b2b2b]"
              >
                Allow
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="mt-1 border-t border-line-soft pt-2 text-[11.5px] text-fg-3">
        Speaking out loud and playing sound need no permission on macOS.
      </div>
      {note && <div className="mt-2 text-[12px] text-fg-2">{note}</div>}
      {perm.restart && (
        <button
          onClick={() => window.agent?.relaunch()}
          className="mt-2 h-8 rounded-full bg-fg px-3.5 text-[12.5px] font-medium text-white hover:bg-[#2b2b2b]"
        >
          Restart Deskwright
        </button>
      )}
    </div>
  );
}
