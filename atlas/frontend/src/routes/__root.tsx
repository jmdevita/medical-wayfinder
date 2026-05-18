import { Outlet, createRootRouteWithContext } from "@tanstack/react-router";
import type { QueryClient } from "@tanstack/react-query";
import { TopBar } from "@/components/layout/TopBar";
import { LeftRail } from "@/components/layout/LeftRail";
import { CommandPalette } from "@/components/CommandPalette";
import { DemoBanner } from "@/components/DemoBanner";

interface RouterContext {
  queryClient: QueryClient;
}

export const Route = createRootRouteWithContext<RouterContext>()({
  component: RootLayout,
});

function RootLayout() {
  return (
    <div className="h-screen flex flex-col bg-paper">
      <DemoBanner />
      <TopBar workspace="Medical Wayfinder · main" />
      <div className="flex-1 flex overflow-hidden">
        <LeftRail />
        <main className="flex-1 overflow-hidden">
          <Outlet />
        </main>
      </div>
      <CommandPalette />
    </div>
  );
}
