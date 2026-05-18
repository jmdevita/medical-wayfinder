import { useEffect, useState } from "react";
import { Command } from "cmdk";
import { useNavigate, useRouterState } from "@tanstack/react-router";
import {
  ArrowRight,
  Compass,
  Eye,
  LogOut,
  Map as MapIcon,
  MousePointer,
  Plus,
  RefreshCw,
  Redo2,
  Save,
  Settings as Cog,
  Sparkles,
  Undo2,
  Workflow,
  type LucideIcon,
} from "lucide-react";
import { api, useDraftEdges, useFacilities, useRerouteEdges, useWhoAmI } from "@/lib/api";
import { useAtlasStore } from "@/lib/store";

/**
 * Window events the palette dispatches when an action needs context that
 * only lives inside a route view (the active draft, the publish modal, etc.).
 * The matching listeners live in EditorView. Keep these names in sync.
 *
 * `togglePalette` is the inverse direction: the cmd-bar dispatches it so
 * other components can request the palette without synthesizing a fake
 * keydown.
 */
export const PALETTE_EVENT = {
  save: "atlas:save-current-tab",
  publish: "atlas:open-publish",
  validate: "atlas:open-validate",
  togglePalette: "atlas:toggle-palette",
  undo: "atlas:undo",
  redo: "atlas:redo",
} as const;

interface PaletteCommand {
  id: string;
  title: string;
  group: "Tools" | "Editor" | "Navigate" | "Facilities" | "Account";
  // Extra search tokens (synonyms, abbreviations) that don't show in the title.
  keywords?: string;
  Icon: LucideIcon;
  run: () => void;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const navigate = useNavigate();
  const pathname = useRouterState({ select: (s) => s.location.pathname });

  const activeFacility = useAtlasStore((s) => s.activeFacility);
  const setActiveFacility = useAtlasStore((s) => s.setActiveFacility);
  const setEditorTool = useAtlasStore((s) => s.setEditorTool);

  const { data: facilities } = useFacilities();
  const { data: who } = useWhoAmI();
  const draftEdges = useDraftEdges();
  const reroute = useRerouteEdges();

  // ⌘K (or Ctrl+K) toggles the palette; Esc closes via cmdk's built-in handler.
  // Also subscribe to the togglePalette window event so other components (e.g.
  // the cmd-bar Palette button) can open us without synthesizing a keydown.
  useEffect(() => {
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key.toLowerCase() === "k" && (ev.metaKey || ev.ctrlKey)) {
        ev.preventDefault();
        setOpen((o) => !o);
      }
    };
    const onToggle = () => setOpen((o) => !o);
    document.addEventListener("keydown", onKey);
    window.addEventListener(PALETTE_EVENT.togglePalette, onToggle);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener(PALETTE_EVENT.togglePalette, onToggle);
    };
  }, []);

  // Helper that runs an action, then closes the palette.
  const run = (fn: () => void) => () => {
    fn();
    setOpen(false);
  };

  const onEditor = pathname === "/editor";
  const slug = activeFacility?.id ?? null;

  const commands: PaletteCommand[] = [];

  // --- Tools (editor only) ---
  if (onEditor) {
    commands.push(
      {
        id: "tool-select",
        title: "Tool: Select",
        group: "Tools",
        keywords: "v cursor pointer",
        Icon: MousePointer,
        run: run(() => setEditorTool("select")),
      },
      {
        id: "tool-add-node",
        title: "Tool: Add Node",
        group: "Tools",
        keywords: "n create point landmark",
        Icon: Plus,
        run: run(() => setEditorTool("addNode")),
      },
      {
        id: "tool-add-edge",
        title: "Tool: Add Edge",
        group: "Tools",
        keywords: "e connection link curve",
        Icon: Workflow,
        run: run(() => setEditorTool("addEdge")),
      },
    );
  }

  // --- Editor actions (editor only, gated on having a slug) ---
  if (onEditor && slug) {
    commands.push(
      {
        id: "editor-undo",
        title: "Undo last edit",
        group: "Editor",
        keywords: "cmd+z back revert",
        Icon: Undo2,
        run: run(() => window.dispatchEvent(new Event(PALETTE_EVENT.undo))),
      },
      {
        id: "editor-redo",
        title: "Redo",
        group: "Editor",
        keywords: "cmd+shift+z forward",
        Icon: Redo2,
        run: run(() => window.dispatchEvent(new Event(PALETTE_EVENT.redo))),
      },
      {
        id: "editor-save",
        title: "Save current tab",
        group: "Editor",
        keywords: "cmd+s write persist",
        Icon: Save,
        run: run(() => window.dispatchEvent(new Event(PALETTE_EVENT.save))),
      },
      {
        id: "editor-validate",
        title: "Validate topology",
        group: "Editor",
        keywords: "lint check dry run",
        Icon: Eye,
        run: run(() => window.dispatchEvent(new Event(PALETTE_EVENT.validate))),
      },
      {
        id: "editor-publish",
        title: "Open Publish dialog",
        group: "Editor",
        keywords: "ship release deploy cmd+enter",
        Icon: ArrowRight,
        run: run(() => window.dispatchEvent(new Event(PALETTE_EVENT.publish))),
      },
      {
        id: "editor-draft-edges",
        title: "Draft missing edges (OSM)",
        group: "Editor",
        keywords: "auto route footway sidewalks",
        Icon: Sparkles,
        run: run(() => {
          draftEdges.mutate({ slug, max_dist: 800 });
        }),
      },
      {
        id: "editor-reroute",
        title: "Re-route stale edges",
        group: "Editor",
        keywords: "snap recompute geometry",
        Icon: RefreshCw,
        run: run(() => {
          reroute.mutate({ slug });
        }),
      },
    );
  }

  // --- Navigation ---
  commands.push(
    {
      id: "nav-facilities",
      title: "Go to Facilities",
      group: "Navigate",
      keywords: "home list",
      Icon: MapIcon,
      run: run(() => navigate({ to: "/" })),
    },
    {
      id: "nav-editor",
      title: "Go to Editor",
      group: "Navigate",
      keywords: "topology nodes edges",
      Icon: Compass,
      run: run(() => navigate({ to: "/editor", search: slug ? { slug } : {} })),
    },
    {
      id: "nav-preview",
      title: "Go to Preview",
      group: "Navigate",
      keywords: "phone patient",
      Icon: Eye,
      run: run(() => navigate({ to: "/preview", search: slug ? { slug } : {} })),
    },
    {
      id: "nav-settings",
      title: "Go to Settings",
      group: "Navigate",
      keywords: "config llm",
      Icon: Cog,
      run: run(() => navigate({ to: "/settings" })),
    },
  );

  // --- Switch facility ---
  if (facilities) {
    for (const f of facilities) {
      const isActive = f.id === slug;
      commands.push({
        id: `facility-${f.id}`,
        title: `Switch facility → ${f.name}${isActive ? " (current)" : ""}`,
        group: "Facilities",
        keywords: `${f.id} ${f.name}`,
        Icon: MapIcon,
        run: run(() => {
          setActiveFacility(f);
          // Stay on a slug-aware route; if we're not on one, jump to /editor.
          const target = pathname === "/preview" ? "/preview" : "/editor";
          navigate({ to: target, search: { slug: f.id } });
        }),
      });
    }
  }

  // --- Account ---
  if (who?.auth_enforced && who.authenticated) {
    commands.push({
      id: "auth-logout",
      title: "Sign out",
      group: "Account",
      keywords: "logout exit",
      Icon: LogOut,
      run: run(async () => {
        await api.logout();
        window.location.href = "/api/auth/login";
      }),
    });
  }

  // Group commands in render order so cmdk can render <Command.Group>s.
  const groups: Record<PaletteCommand["group"], PaletteCommand[]> = {
    Tools: [],
    Editor: [],
    Navigate: [],
    Facilities: [],
    Account: [],
  };
  for (const c of commands) groups[c.group].push(c);

  return (
    <Command.Dialog
      open={open}
      onOpenChange={setOpen}
      label="Command palette"
      className="atlas-cmdk-root"
      overlayClassName="atlas-cmdk-overlay"
      contentClassName="atlas-cmdk-content"
    >
      <Command.Input
        placeholder="Search commands…"
        className="atlas-cmdk-input"
      />
      <Command.List className="atlas-cmdk-list">
        <Command.Empty className="atlas-cmdk-empty">
          No matching commands.
        </Command.Empty>

        {(Object.keys(groups) as Array<PaletteCommand["group"]>).map((g) => {
          const items = groups[g];
          if (items.length === 0) return null;
          return (
            <Command.Group key={g} heading={g} className="atlas-cmdk-group">
              {items.map((cmd) => (
                <Command.Item
                  key={cmd.id}
                  value={`${cmd.title} ${cmd.keywords ?? ""}`}
                  onSelect={cmd.run}
                  className="atlas-cmdk-item"
                >
                  <cmd.Icon size={13} strokeWidth={1.5} />
                  <span>{cmd.title}</span>
                </Command.Item>
              ))}
            </Command.Group>
          );
        })}
      </Command.List>
      <div className="atlas-cmdk-foot">
        <span><kbd>↑↓</kbd> navigate</span>
        <span><kbd>↵</kbd> run</span>
        <span><kbd>esc</kbd> close</span>
      </div>
    </Command.Dialog>
  );
}
