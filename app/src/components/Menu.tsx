import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";


export type MenuItem =
  | { kind?: "item"; label: string; icon?: any; hint?: string; onSelect: () => void; danger?: boolean }
  | { kind: "toggle"; label: string; icon?: any; checked: boolean; onSelect: () => void }
  | { kind: "separator" }
  | { kind: "label"; label: string };

export function Menu({
  trigger,
  items,
  align = "left",
  side = "bottom",
  width = 240,
}: {
  trigger: (open: boolean, toggle: () => void) => React.ReactNode;
  items: MenuItem[];
  align?: "left" | "right";
  side?: "top" | "bottom";
  width?: number;
}) {
  const [open, setOpen] = useState(false);
  const [flip, setFlip] = useState(false); // not enough room on the asked-for side: open the other way
  const ref = useRef<HTMLDivElement>(null);
  const toggle = () => {
    if (!open && ref.current) {
      const r = ref.current.getBoundingClientRect();
      const need = items.length * 34 + 24;
      setFlip(side === "bottom" ? window.innerHeight - r.bottom < need && r.top > need : r.top < need);
    }
    setOpen((o) => !o);
  };
  const at = flip ? (side === "bottom" ? "top" : "bottom") : side;

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    window.addEventListener("mousedown", onDown);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("mousedown", onDown);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative inline-block">
      {trigger(open, toggle)}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: at === "bottom" ? -4 : 4, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, transition: { duration: 0.1 } }}
            transition={{ duration: 0.14, ease: [0.2, 0.8, 0.2, 1] }}
            style={{ width }}
            className={`absolute z-50 rounded-2xl bg-white p-1.5 shadow-pop ${align === "left" ? "left-0" : "right-0"} ${
              at === "bottom" ? "top-[calc(100%+6px)]" : "bottom-[calc(100%+6px)]"
            }`}
          >
            {items.map((it, i) => {
              if (it.kind === "separator") return <div key={i} className="mx-2 my-1 h-px bg-line-soft" />;
              if (it.kind === "label")
                return (
                  <div key={i} className="px-2.5 pb-1 pt-2 text-[12px] text-fg-3">
                    {it.label}
                  </div>
                );
              const Icon = it.icon;
              return (
                <button
                  key={i}
                  onClick={() => {
                    it.onSelect();
                    if (it.kind !== "toggle") setOpen(false);
                  }}
                  className={`flex w-full items-center gap-2.5 rounded-xl px-2.5 py-2 text-left text-[13.5px] hover:bg-surface-2 ${
                    "danger" in it && it.danger ? "text-bad" : "text-fg"
                  }`}
                >
                  {Icon && <Icon className="h-4 w-4 shrink-0 text-fg-2" strokeWidth={1.75} />}
                  <span className="flex-1">{it.label}</span>
                  {it.kind === "toggle" ? (
                    <span
                      className={`relative h-[18px] w-[30px] shrink-0 rounded-full transition-colors ${
                        it.checked ? "bg-fg" : "bg-surface-3"
                      }`}
                    >
                      <span
                        className={`absolute top-[2px] h-[14px] w-[14px] rounded-full bg-white shadow transition-all ${
                          it.checked ? "left-[14px]" : "left-[2px]"
                        }`}
                      />
                    </span>
                  ) : (
                    "hint" in it && it.hint && <span className="text-[12px] text-fg-3">{it.hint}</span>
                  )}
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

