import { Bar, CartesianGrid, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DayStats, SavedTask } from "../lib/types";
import { t } from "../lib/i18n";

export function RunChart({ runs, height = 140 }: { runs: SavedTask["runs"]; height?: number }) {
  const data = runs
    .filter((r) => r.metrics && r.status !== "running")
    .map((r, i) => ({
      run: `Run ${i + 1}`,
      time: Number((r.metrics.elapsed ?? 0).toFixed(1)),
      cost: Number(((r.metrics.cost ?? 0) * 1000).toFixed(2)),
    }));
  if (data.length === 0) return <div className="py-6 text-center text-[12.5px] text-fg-3">{t("No runs yet")}</div>;
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: -22 }}>
          <CartesianGrid stroke="#efefef" vertical={false} />
          <XAxis dataKey="run" tick={{ fill: "#8f8f8f", fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis yAxisId="t" tick={{ fill: "#8f8f8f", fontSize: 11 }} axisLine={false} tickLine={false} unit="s" />
          <YAxis yAxisId="c" orientation="right" hide />
          <Tooltip
            cursor={{ fill: "rgba(0,0,0,.03)" }}
            contentStyle={{
              background: "#fff",
              border: "none",
              borderRadius: 10,
              fontSize: 12,
              boxShadow: "0 0 0 1px rgba(0,0,0,.06), 0 8px 24px rgba(0,0,0,.12)",
            }}
            formatter={(v: number, name: string) =>
              name === "time" ? [`${v}s`, t("Time")] : [`$${(v / 1000).toFixed(4)}`, t("Cost")]
            }
          />
          <Bar yAxisId="t" dataKey="time" fill="#0d0d0d" radius={[4, 4, 0, 0]} maxBarSize={20} />
          <Line yAxisId="c" dataKey="cost" stroke="#c2410c" strokeWidth={2} dot={{ r: 2.5, fill: "#c2410c" }} />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

const TOOLTIP = {
  background: "#fff",
  border: "none",
  borderRadius: 10,
  fontSize: 12,
  boxShadow: "0 0 0 1px rgba(0,0,0,.06), 0 8px 24px rgba(0,0,0,.12)",
};

/** One chart over the last two weeks: a bar per day, or two series side by side. */
export function DayChart({
  days,
  series,
  unit = "",
  format = (v: number) => String(v),
  height = 120,
}: {
  days: DayStats[];
  series: { key: keyof DayStats; label: string; color: string }[];
  unit?: string;
  format?: (v: number) => string;
  height?: number;
}) {
  const data = days.map((d) => ({ ...d, label: d.day.slice(5).replace("-", "/") }));
  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer>
        <ComposedChart data={data} margin={{ top: 8, right: 0, bottom: 0, left: -18 }}>
          <CartesianGrid stroke="#efefef" vertical={false} />
          <XAxis dataKey="label" tick={{ fill: "#8f8f8f", fontSize: 10.5 }} axisLine={false} tickLine={false} interval={1} />
          <YAxis tick={{ fill: "#8f8f8f", fontSize: 10.5 }} axisLine={false} tickLine={false} unit={unit} width={44} />
          <Tooltip
            cursor={{ fill: "rgba(0,0,0,.03)" }}
            contentStyle={TOOLTIP}
            formatter={(v: number, name: string) => [format(v), series.find((s) => s.key === name)?.label ?? name]}
          />
          {series.map((s) => (
            <Bar key={s.key} dataKey={s.key} fill={s.color} radius={[4, 4, 0, 0]} maxBarSize={series.length > 1 ? 9 : 16} />
          ))}
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}
