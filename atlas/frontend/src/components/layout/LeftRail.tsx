import { Link, useRouterState } from "@tanstack/react-router";
import { Map as MapIcon, Compass, Phone, Inbox, Settings as Cog, type LucideIcon } from "lucide-react";
import { useAtlasStore } from "@/lib/store";
import { useProposalsList, useWhoAmI } from "@/lib/api";
import { cn } from "@/lib/utils";

interface RailItemProps {
  to: string;
  search?: Record<string, string | undefined>;
  active: boolean;
  num: string;
  label: string;
  Icon: LucideIcon;
  badge?: number;
}

function RailItem({ to, search, active, num, label, Icon, badge }: RailItemProps) {
  return (
    <Link
      to={to}
      search={search as never}
      className={cn(
        "group relative flex flex-col items-center w-full py-4 transition-colors",
        active ? "text-ink" : "text-slate hover:text-ink",
      )}
    >
      {active && <span className="absolute left-0 top-3 bottom-3 w-[2px] bg-saffron" />}
      <div className="relative">
        <Icon size={20} strokeWidth={active ? 1.6 : 1.4} />
        {badge !== undefined && badge > 0 && (
          <span className="absolute -top-1 -right-2 min-w-[14px] h-[14px] px-1 bg-saffron text-paper rounded-full ff-mono text-[8.5px] tracking-wide-2 grid place-items-center">
            {badge}
          </span>
        )}
      </div>
      <span
        className={cn(
          "mt-1.5 ff-mono text-[9px] tracking-wide-3 small-caps",
          active ? "text-ink" : "text-slate-2",
        )}
      >
        {label}
      </span>
      <span className="absolute right-3 top-3 ff-mono text-[8px] tracking-wide-2 text-slate-3">{num}</span>
    </Link>
  );
}

export function LeftRail() {
  const path = useRouterState({ select: (s) => s.location.pathname });
  const is = (p: string) => path === p || (p !== "/" && path.startsWith(p));
  const slug = useAtlasStore((s) => s.activeFacility?.id);
  const slugSearch = slug ? { slug } : undefined;

  const { data: who } = useWhoAmI();
  const isAdmin = who?.role === "admin";
  // Only admins poll the queue — contributors and viewers don't have
  // permission to read it and don't need the badge.
  const { data: proposals } = useProposalsList({ enabled: isAdmin });
  const pendingCount = (proposals ?? []).filter((p) => p.status === "pending").length;

  return (
    <nav className="w-[78px] border-r border-hairline bg-paper relative">
      <RailItem to="/"         active={path === "/"}                       num="01" Icon={MapIcon} label="Facilities" />
      <RailItem to="/editor"   search={slugSearch} active={is("/editor")}   num="02" Icon={Compass} label="Editor" />
      <RailItem to="/preview"  search={slugSearch} active={is("/preview")}  num="03" Icon={Phone}   label="Preview" />
      {isAdmin && (
        <RailItem to="/proposals" active={is("/proposals")}                  num="04" Icon={Inbox}  label="Review" badge={pendingCount} />
      )}
      <RailItem to="/settings" active={is("/settings")}                     num={isAdmin ? "05" : "04"} Icon={Cog}     label="Settings" />
      <div className="absolute bottom-4 left-0 right-0 flex justify-center">
        <div className="text-[8px] ff-mono tracking-wide-3 text-slate-3 [writing-mode:vertical-rl] rotate-180">
          v2.0 · MOCKUP
        </div>
      </div>
    </nav>
  );
}
