import { ChevronDown, LogOut, Search } from "lucide-react";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import { api, useFacilities, useWhoAmI } from "@/lib/api";
import { useAtlasStore } from "@/lib/store";
import { cn } from "@/lib/utils";

interface Props {
  workspace: string;
}

// Routes whose primary content depends on the `?slug=` search param. Only
// these get the inline facility switcher in the TopBar — on /facilities and
// /settings there's no view to swap.
const SLUG_ROUTES = new Set(["/editor", "/preview"]);

export function TopBar({ workspace }: Props) {
  const activeFacility = useAtlasStore((s) => s.activeFacility);
  const setActiveFacility = useAtlasStore((s) => s.setActiveFacility);
  const { data: who } = useWhoAmI();
  const { data: facilities } = useFacilities();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const navigate = useNavigate();

  const showSwitcher = SLUG_ROUTES.has(pathname) && (facilities?.length ?? 0) > 0;

  return (
    <header className="border-b border-hairline bg-paper relative grain">
      <div className="px-7 h-[58px] flex items-center gap-6">
        <div className="flex items-baseline gap-2.5">
          <span className="ff-display italic text-[19px] leading-none">Wayfinder</span>
          <span className="text-saffron text-[10px] tracking-wide-4 uppercase ff-mono">Atlas</span>
        </div>

        <div className="h-5 w-px bg-hairline" />

        <span className="flex items-center gap-2 px-2.5 py-1">
          <span className="w-1.5 h-1.5 rounded-full bg-moss" />
          <span className="text-[12.5px] text-ink">{workspace}</span>
        </span>

        {showSwitcher && (
          <div className="ml-auto relative flex items-center">
            <select
              value={activeFacility?.id ?? ""}
              onChange={(ev) => {
                const nextSlug = ev.target.value;
                if (!nextSlug || nextSlug === activeFacility?.id) return;
                const f = facilities!.find((x) => x.id === nextSlug);
                if (f) setActiveFacility(f);
                // Stay on the current route (/editor or /preview), swap slug.
                // Drop any aux params (e.g. ?node=...) since they're per-facility.
                navigate({
                  to: pathname,
                  search: { slug: nextSlug },
                });
              }}
              className="appearance-none pl-3 pr-7 h-8 rounded-sm bg-paper-2 border border-hairline text-[12.5px] text-ink hover:border-ink focus:outline-none focus:border-ink cursor-pointer"
              title="Switch facility"
            >
              {!activeFacility && <option value="">Pick a facility</option>}
              {facilities!.map((f) => (
                <option key={f.id} value={f.id}>{f.name}</option>
              ))}
            </select>
            <ChevronDown size={12} className="absolute right-2 text-slate-2 pointer-events-none" strokeWidth={1.5} />
          </div>
        )}

        <div
          className={cn(
            "flex items-center gap-2 px-3 h-8 rounded-sm bg-paper-2 border border-hairline w-[360px] opacity-60",
            showSwitcher ? "" : "ml-auto",
          )}
          title="Search isn't wired yet — coming with the command palette."
        >
          <Search size={14} className="text-slate-2" strokeWidth={1.5} />
          <input
            disabled
            className="bg-transparent flex-1 text-[12.5px] outline-none placeholder:text-slate-2 cursor-not-allowed"
            placeholder="Search · soon"
          />
        </div>

        <div className="flex items-center gap-3">
          {who?.auth_enforced && !who.authenticated ? (
            <a
              href="/api/auth/login"
              className="px-3 h-8 border border-hairline rounded-sm text-[11.5px] tracking-wide-2 small-caps text-ink hover:bg-paper-2 flex items-center gap-1.5"
            >
              Sign in with GitHub
            </a>
          ) : (
            <div className="flex items-center gap-2">
              <div
                className="h-7 w-7 rounded-full bg-saffron text-paper grid place-items-center text-[11px] ff-display italic"
                title={who?.login ?? "dev"}
              >
                {(who?.login ?? "d")[0].toUpperCase()}
              </div>
              {who?.auth_enforced && (
                <button
                  onClick={async () => {
                    await api.logout();
                    window.location.href = "/api/auth/login";
                  }}
                  className="text-slate hover:text-ink"
                  title="Sign out"
                >
                  <LogOut size={13} strokeWidth={1.5} />
                </button>
              )}
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
