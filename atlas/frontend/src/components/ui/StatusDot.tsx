import { cn } from "@/lib/utils";

interface Props {
  color?: string;
  size?: number;
  pulse?: boolean;
  className?: string;
}

export function StatusDot({ color = "#B8530A", size = 8, pulse = false, className }: Props) {
  return (
    <span
      className={cn("inline-block rounded-full", pulse && "pulse-dot", className)}
      style={{ width: size, height: size, background: color }}
    />
  );
}
