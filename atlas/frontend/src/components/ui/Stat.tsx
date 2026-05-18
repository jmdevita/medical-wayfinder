import { cn } from "@/lib/utils";

interface StatProps {
  n: number | string;
  label: string;
  warn?: boolean;
  alert?: boolean;
}

export function Stat({ n, label, warn, alert }: StatProps) {
  return (
    <div className="flex flex-col items-start">
      <span className={cn(
        "num-display text-[22px] leading-none",
        alert && "text-rust",
        !alert && warn && "text-ochre",
      )}>
        {typeof n === "number" ? String(n).padStart(2, "0") : n}
      </span>
      <span className="ff-mono text-[9px] tracking-wide-3 small-caps text-slate-2 mt-1">{label}</span>
    </div>
  );
}

interface StatBigProps {
  n: string;
  label: string;
  sub: string;
  tone?: "rust" | "ink";
}

export function StatBig({ n, label, sub, tone = "ink" }: StatBigProps) {
  return (
    <div className="border-l-2 border-hairline pl-4">
      <div className={cn("num-display text-[44px] leading-none", tone === "rust" ? "text-rust" : "text-ink")}>{n}</div>
      <div className="text-[12px] mt-1 small-caps tracking-wide-2 text-ink">{label}</div>
      <div className="text-[10.5px] ff-mono text-slate-2 mt-0.5">{sub}</div>
    </div>
  );
}
