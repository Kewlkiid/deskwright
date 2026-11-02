// Saved tasks, metrics and permissions, shown as cards inside the conversation instead of separate tabs.
import { useEffect, useState } from "react";
import { Check, ChevronRight, Code2, GraduationCap, Play, Trash2 } from "lucide-react";
import type { Metrics, PermissionKind, Permissions, SavedTask, Totals } from "../lib/types";
import { LANGUAGES, plural, t, t as tr } from "../lib/i18n";
import { DayChart, RunChart } from "./RunChart";

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
  const [copied, setCopied] = useState<number | null>(null);
  if (!tasks.length) {
    return (
      <div className="text-[14px] leading-relaxed text-fg-2">
        {t("No saved tasks yet. Save a finished run, or teach me one: open the … menu and choose")}{" "}
        <span className="text-fg">{t("Teach by demonstration")}</span>.
      </div>
    );
  }
  return (
    <div className="space-y-2">
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
                      {plural("1 run", "{n} runs", runs.length)}
                      {t.versions.length > 1 ? ` · v${t.versions.length}` : ""}
                      {t.detours ? ` · ${plural("1 way back learned", "{n} ways back learned", t.detours)}` : ""}
                      {speedup && speedup > 1.05 ? ` · ${tr("now {x}× faster", { x: speedup.toFixed(1) })}` : ""}
                    </span>
                  </span>
                </button>
                <button
                  disabled={running}
                  onClick={() => onRun(t.id)}
                  className="flex h-7 items-center gap-1 rounded-full bg-fg px-3 text-[12px] font-medium text-white hover:bg-[#2b2b2b] disabled:opacity-30"
                >
                  <Play className="h-3 w-3 fill-white" /> {tr("Run")}
                </button>
              </div>
              {isOpen && (
                <div className="space-y-2 bg-surface px-3 pb-3 pt-1">
                  <div className="flex items-center gap-3 text-[11.5px] text-fg-3">
                    <span className="flex items-center gap-1">
                      <i className="h-2 w-2 rounded-sm bg-fg" /> {tr("time")}
                    </span>
                    <span className="flex items-center gap-1">
                      <i className="h-0.5 w-3 bg-cache" /> {tr("cost")}
                    </span>
                  </div>
                  <RunChart runs={t.runs} height={120} />
                  <pre className="selectable scroll-y max-h-36 overflow-auto rounded-lg border border-line-soft bg-white p-2.5 font-mono text-[11px] leading-[18px] text-fg-2">
                    {t.script}
                  </pre>
                  <div className="flex items-center justify-between text-[12px] text-fg-3">
                    <button
                      onClick={() => {
                        navigator.clipboard?.writeText(t.script);
                        setCopied(t.id);
                        setTimeout(() => setCopied((c) => (c === t.id ? null : c)), 1500);
                      }}
                      className="flex items-center gap-1 hover:text-fg"
                    >
                      {copied === t.id ? <Check className="h-3.5 w-3.5 text-ok" /> : <Code2 className="h-3.5 w-3.5" strokeWidth={1.75} />}
                      {copied === t.id ? tr("Copied") : tr("Copy code")}
                    </button>
                    <button onClick={() => onDelete(t.id)} className="flex items-center gap-1 hover:text-bad">
                      <Trash2 className="h-3.5 w-3.5" strokeWidth={1.75} /> {tr("Delete")}
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

export function MetricsCard({ metrics, totals }: { metrics: Metrics | null; totals: Totals | null }) {
  const m = metrics;
  const days = totals?.days ?? [];
  const any = days.some((d) => d.runs > 0);
  return (
    <div className="space-y-4">
      <div className="space-y-3">
        <div className="text-[14px]">{m ? t("Here's how the last run went.") : t("No runs yet this session.")}</div>
        {m && (
          <div className="grid grid-cols-3 divide-x divide-y divide-line-soft overflow-hidden rounded-xl border border-line [&>*:nth-child(-n+3)]:border-t-0">
            <Stat label={t("Time")} value={`${m.elapsed.toFixed(1)}s`} sub={t("{s}s in models", { s: m.model_time.toFixed(1) })} />
            <Stat label={t("Cost")} value={`$${m.cost.toFixed(3)}`} />
            <Stat label={t("Steps")} value={String(m.steps)} />
            <Stat
              label={t("Model calls")}
              value={String(m.model_calls)}
              sub={Object.entries(m.calls_by_role || {}).map(([k, v]) => `${k} ${v}`).join(", ")}
            />
            <Stat label={t("From cache")} value={`${Math.round(m.cache_hit_rate * 100)}%`} sub={t("{n} calls skipped", { n: m.calls_saved })} />
            <Stat label={t("Self-fixes")} value={`${m.fixes_succeeded}/${m.fixes}`} sub={t("worked / tried")} />
          </div>
        )}
        {totals && totals.runs > 0 && (
          <div className="text-[13px] text-fg-2">
            {t("Across all {n} runs: {a}% succeeded, and {b}% of self-fixes worked.", {
              n: totals.runs, a: Math.round(totals.success_rate * 100), b: Math.round(totals.fix_success_rate * 100),
            })}
          </div>
        )}
      </div>
      {any && (
        <>
          <ChartBlock title={t("Cost per day")}>
            <DayChart days={days} series={[{ key: "cost", label: t("Cost"), color: "#c2410c" }]} format={(v) => `$${v.toFixed(3)}`} />
          </ChartBlock>
          <ChartBlock title={t("Runs and model calls per day")}>
            <DayChart
              days={days}
              series={[
                { key: "runs", label: t("Runs"), color: "#0d0d0d" },
                { key: "model_calls", label: t("Model calls"), color: "#9ca3af" },
              ]}
            />
          </ChartBlock>
          <ChartBlock
            title={t("Average run time: first run vs. repeats")}
            note={t("A repeat is a saved task or the same request run again: the position cache makes it faster.")}
          >
            <DayChart
              days={days}
              unit="s"
              series={[
                { key: "first_time", label: t("First run"), color: "#0d0d0d" },
                { key: "repeat_time", label: t("Repeat"), color: "#c2410c" },
              ]}
              format={(v) => `${v}s`}
            />
          </ChartBlock>
        </>
      )}
    </div>
  );
}

function ChartBlock({ title, note, children }: { title: string; note?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-line p-3">
      <div className="text-[13px] font-medium">{title}</div>
      {note && <div className="text-[11.5px] text-fg-3">{note}</div>}
      <div className="mt-1.5">{children}</div>
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
    { ok: perm.screen === "granted", label: t("Screen Recording"), why: t("to see your screen"), act: () => {
        window.agent?.askScreen();
        window.agent?.openPermission("screen");
      } },
    {
      ok: perm.accessibility,
      label: t("Accessibility"),
      why: t("to move the mouse and type"),
      act: () => {
        window.agent?.askAccessibility();
        window.agent?.openPermission("accessibility");
      },
    },
    { ok: perm.microphone === "granted", label: t("Microphone"), why: t("for voice, optional"), act: () => window.agent?.askMicrophone() },
    { ok: null, label: t("Input Monitoring"), why: t("for teach mode"), act: () => window.agent?.openPermission("input") },
  ];
  const required = rows[0].ok && rows[1].ok;
  return (
    <div className="rounded-2xl border border-line p-3.5 text-left">
      <div className="text-[14px] font-medium">{t("Before the first run")}</div>
      <div className="mt-0.5 text-[13px] text-fg-2">
        {t("macOS needs to allow this app to see and control the screen. Restart the app after granting.")}
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
            {!r.ok && <span className="ml-auto text-[12px] text-fg-2">{t("Open")}</span>}
          </button>
        ))}
      </div>
      {perm.restart && (
        <div className="mt-2.5 flex items-center gap-3 rounded-xl bg-[#f0fdf4] px-3 py-2.5">
          <span className="flex-1 text-[12.5px] text-fg-2">
            {t("Screen Recording is on. macOS applies it after Deskwright restarts.")}
          </span>
          <button
            onClick={() => window.agent?.relaunch()}
            className="h-8 shrink-0 rounded-full bg-fg px-3.5 text-[12.5px] font-medium text-white hover:bg-[#2b2b2b]"
          >
            {t("Restart Deskwright")}
          </button>
        </div>
      )}
      <div className="mt-2 flex items-center justify-between border-t border-line-soft pt-2.5 text-[12px] text-fg-3">
        <span>{t("Tip: turn on Do Not Disturb so notifications stay out of screenshots.")}</span>
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
            {t("Done")}
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
  if (!perm) return <div className="text-[13px] text-fg-3">{t("Checking permissions…")}</div>;
  if (perm.platform !== "darwin") return <div className="text-[13px] text-fg-2">{t("Permissions are only needed on macOS.")}</div>;

  const rows: { kind: PermissionKind; label: string; why: string; ok: boolean | null; ask: () => void }[] = [
    { kind: "screen", label: t("Screen Recording"), why: t("see your screen (required)"), ok: perm.screen === "granted",
      ask: () => { window.agent?.askScreen(); window.agent?.openPermission("screen"); } },
    { kind: "accessibility", label: t("Accessibility"), why: t("move the mouse and type (required)"), ok: perm.accessibility,
      ask: () => { window.agent?.askAccessibility(); window.agent?.openPermission("accessibility"); } },
    { kind: "microphone", label: t("Microphone"), why: t("hear “Hey Agent”"), ok: perm.microphone === "granted",
      ask: () => window.agent?.askMicrophone().then(poll) },
    { kind: "speech", label: t("Speech Recognition"), why: t("understand speech on this Mac"),
      ok: perm.speech === "granted" ? true : perm.speech === "denied" ? false : null,
      ask: () => window.agent?.openPermission("speech") },
    { kind: "input", label: t("Input Monitoring"), why: t("record your demonstrations in teach mode"), ok: perm.input ?? null,
      ask: () => window.agent?.openPermission("input") },
    { kind: "automation", label: t("Automation"), why: t("open and switch apps"), ok: null,
      ask: () => window.agent?.openPermission("automation") },
  ];

  const revoke = async (kind: PermissionKind, label: string) => {
    setBusy(kind);
    const ok = await window.agent?.revokePermission(kind);
    setBusy(null);
    setNote(ok ? t("{label} was taken back. macOS asks again the next time Deskwright needs it.", { label }) : t("Couldn't change {label}; use System Settings.", { label }));
    poll();
  };

  return (
    <div className="text-left">
      <div className="text-[12.5px] text-fg-2">{t("What macOS lets Deskwright do. Changes to Screen Recording and Accessibility apply after a restart.")}</div>
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
                {r.ok ? t("Allowed") : r.ok === false ? t("Not allowed") : t("Not asked yet")} · {r.why}
              </div>
            </div>
            {r.ok ? (
              <button
                disabled={busy === r.kind}
                onClick={() => revoke(r.kind, r.label)}
                className="h-7 shrink-0 rounded-full border border-line px-2.5 text-[12px] text-fg-2 hover:bg-surface disabled:opacity-50"
              >
                {busy === r.kind ? "…" : t("Revoke")}
              </button>
            ) : (
              <button
                onClick={r.ask}
                className="h-7 shrink-0 rounded-full bg-fg px-2.5 text-[12px] font-medium text-white hover:bg-[#2b2b2b]"
              >
                {t("Allow")}
              </button>
            )}
          </div>
        ))}
      </div>
      <div className="mt-1 border-t border-line-soft pt-2 text-[11.5px] text-fg-3">
        {t("Speaking out loud and playing sound need no permission on macOS.")}
      </div>
      {note && <div className="mt-2 text-[12px] text-fg-2">{note}</div>}
      {perm.restart && (
        <button
          onClick={() => window.agent?.relaunch()}
          className="mt-2 h-8 rounded-full bg-fg px-3.5 text-[12.5px] font-medium text-white hover:bg-[#2b2b2b]"
        >
          {t("Restart Deskwright")}
        </button>
      )}
    </div>
  );
}

/** The language Deskwright's text, voice and answers use. */
export function LanguageList({ current, onChoose }: { current: string; onChoose: (code: string) => void }) {
  return (
    <div className="text-left">
      <div className="divide-y divide-line-soft">
        {LANGUAGES.map((l) => (
          <button
            key={l.code}
            onClick={() => onChoose(l.code)}
            className="-mx-2 flex w-[calc(100%+16px)] items-center gap-3 rounded-xl px-2 py-3.5 text-left hover:bg-surface"
          >
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-surface-2 text-[12px] font-semibold uppercase text-fg-2">
              {l.code}
            </span>
            <span className="min-w-0 flex-1 leading-tight">
              <span className="block text-[15.5px] font-medium">{l.name}</span>
              <span className="block text-[12.5px] text-fg-3">{l.english}</span>
            </span>
            {current === l.code && <Check className="h-5 w-5 text-ok" strokeWidth={2.5} />}
          </button>
        ))}
      </div>
      <div className="mt-3 rounded-xl bg-surface px-3 py-2.5 text-[12.5px] leading-relaxed text-fg-2">
        {t("The voice speaks this language. Voice commands work in it and in English.")}
      </div>
    </div>
  );
}
