import { useEffect } from "react";
import { motion } from "framer-motion";
import { X } from "lucide-react";

/** A panel that slides up over the conversation (saved tasks, metrics, permissions). × or Esc closes it. */
export function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.15 }}
      className="absolute inset-0 z-40 flex flex-col bg-black/10"
      onMouseDown={(e) => e.target === e.currentTarget && onClose()}
    >
      <motion.div
        initial={{ y: 24, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        exit={{ y: 24, opacity: 0 }}
        transition={{ duration: 0.2, ease: [0.2, 0.8, 0.2, 1] }}
        className="mt-12 flex min-h-0 flex-1 flex-col rounded-t-[22px] bg-white shadow-pop"
      >
        <div className="flex h-12 shrink-0 items-center px-4">
          <span className="flex-1 text-[15px] font-semibold tracking-tight">{title}</span>
          <button
            onClick={onClose}
            title="Close"
            className="flex h-8 w-8 items-center justify-center rounded-lg text-fg-2 hover:bg-surface-2"
          >
            <X className="h-[18px] w-[18px]" strokeWidth={1.75} />
          </button>
        </div>
        <div className="scroll-y min-h-0 flex-1 px-4 pb-6">{children}</div>
      </motion.div>
    </motion.div>
  );
}
