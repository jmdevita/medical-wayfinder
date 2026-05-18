/**
 * Public-demo banner. Rendered above the TopBar in the root layout when the
 * backend reports `demo_mode: true` from /api/settings/current (set by the
 * deployment's ATLAS_DEMO_MODE=true env var).
 *
 * Why this design:
 *  - Saffron accent (Atlas's "attention" colour) instead of a red/amber alert
 *    bar — this isn't an error state, it's a normal deployment mode
 *  - Single-line, dismissable, sticky at top so users can scroll past it
 *  - Explains the reset cadence and that LLM/Maps features are disabled,
 *    so a 503 on those routes is expected rather than a bug
 *
 * If the query is still loading or demo_mode is false, render nothing — we
 * don't want a layout-shifting placeholder.
 */

import { useState } from "react";
import { AlertCircle, X } from "lucide-react";
import { useCurrentSettings } from "@/lib/api";

const STORAGE_KEY = "atlas:demo-banner-dismissed";

export function DemoBanner() {
  const { data: settings } = useCurrentSettings();
  // Default to dismissed=false on first paint, but read localStorage in an
  // initializer so we don't re-flash the banner if the user already closed it
  // in this session.
  const [dismissed, setDismissed] = useState<boolean>(
    () => {
      if (typeof window === "undefined") return false;
      return window.sessionStorage.getItem(STORAGE_KEY) === "1";
    },
  );

  if (!settings?.demo_mode || dismissed) {
    return null;
  }

  const handleDismiss = () => {
    setDismissed(true);
    try {
      window.sessionStorage.setItem(STORAGE_KEY, "1");
    } catch {
      // sessionStorage can throw in private-browsing on some browsers; the
      // banner just won't be remembered across reloads. Not worth surfacing.
    }
  };

  return (
    <div
      role="status"
      className="bg-saffron/10 border-b border-saffron/30 px-7 py-2 flex items-center gap-3 text-[12.5px]"
    >
      <AlertCircle size={14} strokeWidth={1.75} className="text-saffron flex-shrink-0" />
      <span className="text-ink leading-snug">
        <span className="ff-mono text-saffron tracking-wide-2 small-caps mr-2">Demo</span>
        You're on the public demo of Atlas. Everything you change here is reset
        daily. LLM-powered and Google Street View features are disabled (you'll
        see a 503 when you try them) — see the full feature set in the{" "}
        <a
          href="https://github.com/jmdevita/medical-wayfinder"
          target="_blank"
          rel="noreferrer"
          className="underline decoration-saffron/50 underline-offset-2 hover:decoration-saffron"
        >
          repo
        </a>
        .
      </span>
      <button
        type="button"
        onClick={handleDismiss}
        aria-label="Dismiss demo banner"
        className="ml-auto p-1 rounded-sm hover:bg-saffron/15 text-ink/60 hover:text-ink transition-colors"
      >
        <X size={14} strokeWidth={1.75} />
      </button>
    </div>
  );
}
