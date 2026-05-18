import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

interface Props {
  num: string;
  title: string;
  children: ReactNode;
  className?: string;
}

export function Section({ num, title, children, className }: Props) {
  return (
    <section className={cn("mb-10", className)}>
      <div className="flex items-baseline gap-3 mb-4">
        <span className="ff-mono text-[10px] tracking-wide-3 text-saffron">{num}</span>
        <span className="ff-display italic text-[20px] leading-none">{title}</span>
        <span className="flex-1 h-px bg-hairline ml-2" />
      </div>
      {children}
    </section>
  );
}
