import type { ReactNode } from "react";
import { SmallCaps } from "./SmallCaps";

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="mb-5">
      <SmallCaps className="block mb-1.5">{label}</SmallCaps>
      {children}
    </div>
  );
}
