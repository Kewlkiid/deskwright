import { ChevronDown, Clipboard, Download, FileJson, FileSpreadsheet, FileText } from "lucide-react";
import type { ResultItem } from "../lib/types";
import { Markdown } from "../lib/markdown";
import { Menu } from "./Menu";

export function ResultCard({ result, onExport }: { result: ResultItem; onExport: (fmt: string) => void }) {
  const exportMenu = (
    <Menu
      align="right"
      width={200}
      trigger={(open, toggle) => (
        <button
          onClick={toggle}
          className={`flex h-7 items-center gap-1 rounded-md px-2 text-[12px] text-fg-2 hover:bg-surface-3 ${open ? "bg-surface-3" : ""}`}
        >
          <Download className="h-3.5 w-3.5" strokeWidth={1.75} /> Export <ChevronDown className="h-3 w-3" />
        </button>
      )}
      items={[
        { label: "CSV", icon: FileText, onSelect: () => onExport("csv") },
        { label: "Excel", icon: FileSpreadsheet, onSelect: () => onExport("xlsx") },
        { label: "JSON", icon: FileJson, onSelect: () => onExport("json") },
        { label: "Markdown", icon: FileText, onSelect: () => onExport("md") },
        { kind: "separator" },
        { label: "Copy to clipboard", icon: Clipboard, onSelect: () => onExport("clipboard") },
      ]}
    />
  );

  if (result.kind !== "table") {
    return (
      <div className="group">
        <div className="text-[14px] leading-relaxed">
          {result.title && <div className="mb-1 font-medium">{result.title}</div>}
          <Markdown text={result.text || ""} />
        </div>
        <div className="mt-1 opacity-60 transition group-hover:opacity-100">{exportMenu}</div>
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-line">
      <div className="flex h-9 items-center gap-2 rounded-t-xl border-b border-line-soft bg-surface pl-3 pr-1.5 text-[12px]">
        <span className="font-medium text-fg">{result.title || "Table"}</span>
        <span className="text-fg-3">{result.rows?.length ?? 0} rows</span>
        <span className="flex-1" />
        {exportMenu}
      </div>
      <div className="scroll-x scroll-y max-h-72 overflow-auto rounded-b-xl">
        <table className="selectable w-full border-collapse text-[12.5px]">
          <thead className="sticky top-0 bg-white">
            <tr>
              {result.columns?.map((c) => (
                <th key={c} className="whitespace-nowrap border-b border-line px-3 py-2 text-left font-medium text-fg-2">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {result.rows?.map((r, i) => (
              <tr key={i} className="border-b border-line-soft last:border-0 hover:bg-surface">
                {r.map((v, j) => (
                  <td key={j} className="whitespace-nowrap px-3 py-1.5 tabular-nums">
                    {String(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
