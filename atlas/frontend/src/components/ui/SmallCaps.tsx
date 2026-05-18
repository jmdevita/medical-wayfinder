import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export function SmallCaps({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span className={cn("small-caps text-[10px] tracking-wide-3 text-slate-2", className)}>
      {children}
    </span>
  );
}
