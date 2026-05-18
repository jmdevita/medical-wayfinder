import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { Compass, Layers, Mic, Loader2 } from "lucide-react";
import { Route as PreviewRoute } from "@/routes/preview";
import { useFacilities, useFacility, useFacilityOsm, type OsmResponse } from "@/lib/api";
import { useAtlasStore } from "@/lib/store";
import { findRoute, type RouteResult } from "@/lib/routing";
import type { Topology, TopologyNode } from "@/lib/types";
import { Field } from "@/components/ui/Field";
import { SmallCaps } from "@/components/ui/SmallCaps";
import { cn } from "@/lib/utils";

interface Department {
  name: string;
  building?: string;
  floor?: string;
  topology_node_id?: string;
  aliases?: string[];
}

type Lang = "en" | "es";

const previewStrings: Record<Lang, {
  userQuery: (dept: string) => string;
  userQueryEmpty: string;
  pickDestination: string;
  headingPrefix: string;
  inBuilding: (b: string) => string;
  stepOf: (i: number, n: number) => string;
  noRoute: string;
  walkMin: (m: string) => string;
  noInstruction: (from: string, to: string) => string;
  alreadyThere: string;
  noPath: string;
  authoredCaption: string;
}> = {
  en: {
    userQuery: (d) => `I need ${d.toLowerCase()}`,
    userQueryEmpty: "I'm looking for a department",
    pickDestination: "Pick a destination to start.",
    headingPrefix: "Heading to ",
    inBuilding: (b) => ` in ${b}`,
    stepOf: (i, n) => `Step ${String(i).padStart(2, "0")} of ${String(n).padStart(2, "0")}`,
    noRoute: "No route",
    walkMin: (m) => `~${m} min walk`,
    noInstruction: (f, t) => `No instruction authored — go from ${f} to ${t}.`,
    alreadyThere: "You're already at the destination.",
    noPath: "No path between origin and destination yet.",
    authoredCaption: "Authored step · on-device model rephrases at runtime",
  },
  es: {
    userQuery: (d) => `Necesito ir a ${d.toLowerCase()}`,
    userQueryEmpty: "Estoy buscando un departamento",
    pickDestination: "Elija un destino para empezar.",
    headingPrefix: "Vamos a ",
    inBuilding: (b) => ` en ${b}`,
    stepOf: (i, n) => `Paso ${String(i).padStart(2, "0")} de ${String(n).padStart(2, "0")}`,
    noRoute: "Sin ruta",
    walkMin: (m) => `~${m} min a pie`,
    noInstruction: (f, t) => `Sin instrucción — vaya de ${f} a ${t}.`,
    alreadyThere: "Ya está en el destino.",
    noPath: "Aún no hay ruta entre el origen y el destino.",
    authoredCaption: "Texto fuente · el modelo en el dispositivo lo traduce al ejecutar",
  },
};

export function PreviewView() {
  const search = PreviewRoute.useSearch();
  const { data: facilities } = useFacilities();
  const fallbackSlug = facilities?.[0]?.id;
  const slug = search.slug ?? fallbackSlug ?? null;

  // Mirror EditorView: keep TopBar's Publish button live for deep links.
  const setActiveFacility = useAtlasStore((s) => s.setActiveFacility);
  const activeId = useAtlasStore((s) => s.activeFacility?.id);
  useEffect(() => {
    if (!slug || !facilities) return;
    if (activeId === slug) return;
    const f = facilities.find((x) => x.id === slug);
    if (f) setActiveFacility(f);
  }, [slug, facilities, activeId, setActiveFacility]);

  const { data: detail, isPending, isError, error } = useFacility(slug);

  if (!slug || (isPending && !detail)) {
    return <Centered><Loader2 size={28} className="text-saffron animate-spin mx-auto mb-3" /><p className="ff-mono text-[11px] tracking-wide-2 small-caps text-slate-2">Loading…</p></Centered>;
  }
  if (isError) {
    return <Centered><p className="ff-mono text-[10px] tracking-wide-3 small-caps text-rust mb-2">Failed</p><p className="ff-display text-[18px]">{error?.message}</p></Centered>;
  }
  if (!detail || !detail.topology) {
    return <Centered><p className="ff-display text-[18px] mb-2">{(detail?.facility.name as string) ?? slug} has no topology.</p><Link to="/" className="ff-mono text-[11px] small-caps text-saffron">← back</Link></Centered>;
  }

  return (
    <PreviewLoaded
      slug={slug}
      facility={detail.facility as { name: string; departments?: Department[] }}
      topology={detail.topology}
    />
  );
}

function PreviewLoaded({
  slug,
  facility,
  topology,
}: {
  slug: string;
  facility: { name: string; departments?: Department[] };
  topology: Topology;
}) {
  // Same OSM bundle the editor uses — building footprints + footways. The
  // phone mini-map paints these underneath the route polyline so the preview
  // resembles the production map view instead of a flat dot grid.
  const { data: osm } = useFacilityOsm(slug);
  const departments = (facility.departments ?? []).filter((d) => d.topology_node_id);
  const origins = topology.nodes.filter((n) => n.type === "parking" || n.type === "transit");

  const [originId, setOriginId] = useState<string>(origins[0]?.id ?? topology.nodes[0]?.id ?? "");
  const [destDept, setDestDept] = useState<Department | null>(departments[0] ?? null);
  const [accessibility, setAccessibility] = useState(false);
  const [language, setLanguage] = useState<Lang>("en");

  // Reset selections when the facility changes.
  useEffect(() => {
    setOriginId(origins[0]?.id ?? topology.nodes[0]?.id ?? "");
    setDestDept(departments[0] ?? null);
  // We deliberately key on facility identity via topology reference.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [topology]);

  const originNode = topology.nodes.find((n) => n.id === originId) ?? null;
  const destNode   = topology.nodes.find((n) => n.id === destDept?.topology_node_id) ?? null;

  const route = useMemo<RouteResult | null>(() => {
    if (!originNode || !destNode) return null;
    return findRoute(topology, originNode.id, destNode.id, { accessibility });
  }, [topology, originNode, destNode, accessibility]);

  return (
    <div className="h-full flex bg-paper">
      <aside className="w-[300px] border-r border-hairline px-5 py-6 overflow-y-auto">
        <PanelHeader num="01" title="Simulator" />
        <p className="text-[12px] text-slate leading-relaxed mb-6 italic ff-display">
          A live phone preview of the Wayfinder app, running against the topology you're editing.
          Change the origin or accessibility flag to feel the difference at the patient's end.
        </p>

        <Field label="Patient origin">
          <select
            value={originId}
            onChange={(e) => setOriginId(e.target.value)}
            className="w-full bg-paper-2 border border-hairline rounded-sm px-3 h-9 text-[12.5px]"
          >
            <optgroup label="Parking">
              {topology.nodes.filter((n) => n.type === "parking").map((n) => (
                <option key={n.id} value={n.id}>{n.label}</option>
              ))}
            </optgroup>
            <optgroup label="Transit">
              {topology.nodes.filter((n) => n.type === "transit").map((n) => (
                <option key={n.id} value={n.id}>{n.label}</option>
              ))}
            </optgroup>
            <optgroup label="Other">
              {topology.nodes.filter((n) => n.type !== "parking" && n.type !== "transit").map((n) => (
                <option key={n.id} value={n.id}>{n.label}</option>
              ))}
            </optgroup>
          </select>
        </Field>

        <Field label={`Destination department (${departments.length})`}>
          <select
            value={destDept?.name ?? ""}
            onChange={(e) => setDestDept(departments.find((d) => d.name === e.target.value) ?? null)}
            className="w-full bg-paper-2 border border-hairline rounded-sm px-3 h-9 text-[12.5px]"
          >
            {departments.map((d) => (
              <option key={d.name} value={d.name}>{d.name}{d.floor ? ` · ${d.floor}` : ""}</option>
            ))}
            {departments.length === 0 && <option value="">No mapped departments</option>}
          </select>
        </Field>

        <Field label="Language">
          <div className="flex gap-1">
            {(["en", "es"] as const).map((k) => (
              <button
                key={k}
                onClick={() => setLanguage(k)}
                className={cn(
                  "flex-1 h-9 text-[11.5px] tracking-wide-2 small-caps rounded-sm border transition-colors",
                  language === k ? "bg-ink text-paper border-ink" : "border-hairline text-slate hover:text-ink",
                )}
              >
                {k === "en" ? "English" : "Español"}
              </button>
            ))}
          </div>
        </Field>

        <Field label="Accessibility mode">
          <button
            onClick={() => setAccessibility(!accessibility)}
            className={cn(
              "w-full px-3 h-9 rounded-sm border flex items-center justify-between transition-colors",
              accessibility ? "bg-moss/10 border-moss text-moss" : "border-hairline text-slate hover:text-ink",
            )}
          >
            <span className="text-[12px]">Wheelchair / mobility</span>
            <span className={cn("w-9 h-5 rounded-full p-0.5 transition-colors", accessibility ? "bg-moss" : "bg-hairline")}>
              <span className={cn("block w-4 h-4 bg-paper rounded-full transition-transform", accessibility && "translate-x-4")} />
            </span>
          </button>
        </Field>

        <div className="pt-4 mt-2 border-t border-hairline">
          <SmallCaps className="block mb-2">Trace · this route</SmallCaps>
          <div className="space-y-1.5 text-[11px]">
            <TraceRow label="Resolved dept"      val={destDept?.name ?? "—"} />
            <TraceRow label="Entrance"           val={destDept?.topology_node_id ?? "—"} mono />
            <TraceRow label="Edges used"         val={String(route?.edges.length ?? 0)} mono />
            <TraceRow label="Total walk"         val={route ? `${route.totalWalkMin.toFixed(1)} min` : "—"} />
            <TraceRow label="Total distance"     val={route ? `${route.totalDistanceM} m` : "—"} mono />
            <TraceRow label="Routing"            val="In-browser Dijkstra" mono tone="moss" />
            {accessibility && (
              <TraceRow
                label="Stair edges hidden"
                val={String(topology.edges.filter((e) => e.accessibility_features?.includes("stairs")).length)}
                mono
              />
            )}
          </div>
        </div>
      </aside>

      <div className="flex-1 flex items-center justify-center plate-dots overflow-y-auto py-10">
        <PhoneFrame
          facility={facility}
          topology={topology}
          origin={originNode}
          destDept={destDept}
          route={route}
          osm={osm}
          language={language}
        />
      </div>

      <aside className="w-[320px] border-l border-hairline px-5 py-6 overflow-y-auto">
        <PanelHeader num="02" title="Why this answer?" />
        <p className="text-[12px] italic ff-display text-ink-2 leading-relaxed mb-5">
          The orchestrator picked these pieces of context. This is what would land in the model's
          prompt right now.
        </p>

        {destDept ? (
          <CtxBlock title="Department record" sub="from facility.json">
            <div className="ff-mono text-[10.5px] text-slate space-y-0.5">
              <div><span className="text-saffron">name</span>: {destDept.name}</div>
              {destDept.building && <div><span className="text-saffron">building</span>: {destDept.building}</div>}
              {destDept.floor    && <div><span className="text-saffron">floor</span>: {destDept.floor}</div>}
              <div><span className="text-saffron">topology_node_id</span>: {destDept.topology_node_id}</div>
              {destDept.aliases && destDept.aliases.length > 0 && (
                <div className="pt-1 text-slate-2"><span className="text-saffron">aliases</span>: {destDept.aliases.slice(0, 4).join(", ")}{destDept.aliases.length > 4 ? `, +${destDept.aliases.length - 4}` : ""}</div>
              )}
            </div>
          </CtxBlock>
        ) : (
          <CtxBlock title="No destination" sub="pick a mapped department">
            <p className="text-[11.5px] text-slate italic">Choose a department on the left to compute a route.</p>
          </CtxBlock>
        )}

        {route && route.edges.length > 0 && (
          <CtxBlock title={`Route · ${route.edges.length} step${route.edges.length === 1 ? "" : "s"}`} sub="Dijkstra over topology">
            {route.edges.map((e, i) => (
              <RouteStep
                key={i}
                n={String(i + 1).padStart(2, "0")}
                text={e.instruction || `(no instruction yet — ${labelOf(topology, e.origin)} → ${labelOf(topology, e.arrival)})`}
                empty={!e.instruction}
              />
            ))}
          </CtxBlock>
        )}
        {route && route.edges.length === 0 && originId === destDept?.topology_node_id && (
          <CtxBlock title="Already there" sub="origin equals destination">
            <p className="text-[11.5px] text-slate italic">You're standing at {originNode?.label}.</p>
          </CtxBlock>
        )}
        {!route && originNode && destNode && (
          <CtxBlock title="No path" sub="topology gap">
            <p className="text-[11.5px] text-rust italic">Couldn't find a walkable path from {originNode.label} to {destNode.label}. Add an edge in the editor.</p>
          </CtxBlock>
        )}

        <CtxBlock title="Model trace" sub="on-device · Gemma 4 E2B">
          <div className="ff-mono text-[10px] text-slate space-y-0.5 leading-relaxed">
            <div><span className="text-moss">[ok]</span> system prompt cached</div>
            <div><span className="text-moss">[ok]</span> facility data injected</div>
            <div><span className={route ? "text-moss" : "text-ochre"}>{route ? "[ok]" : "[note]"}</span> route block {route ? "injected" : "missing"}</div>
            <div><span className="text-slate-2">[stub]</span> JSON schema validation pending</div>
          </div>
        </CtxBlock>
      </aside>
    </div>
  );
}

function labelOf(topology: Topology, id: string): string {
  return topology.nodes.find((n) => n.id === id)?.label ?? id;
}

// ----------- presentational pieces -----------

function PanelHeader({ num, title }: { num: string; title: string }) {
  return (
    <div className="flex items-baseline gap-2 mb-4">
      <span className="ff-mono text-[9.5px] tracking-wide-3 small-caps text-saffron">{num} / {title}</span>
      <span className="flex-1 h-px bg-hairline" />
    </div>
  );
}

function TraceRow({ label, val, mono, tone }: { label: string; val: string; mono?: boolean; tone?: "moss" }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-slate flex-shrink-0">{label}</span>
      <span className={cn(mono && "ff-mono", tone === "moss" ? "text-moss" : "text-ink", "truncate text-right")}>{val}</span>
    </div>
  );
}

function CtxBlock({ title, sub, children }: { title: string; sub: string; children: React.ReactNode }) {
  return (
    <div className="mb-5 pb-5 border-b border-hairline last:border-b-0">
      <div className="flex items-baseline gap-2 mb-2">
        <span className="ff-display italic text-[14px]">{title}</span>
        <span className="ff-mono text-[9.5px] tracking-wide-2 text-slate-2">{sub}</span>
      </div>
      {children}
    </div>
  );
}

function RouteStep({ n, text, empty }: { n: string; text: string; empty?: boolean }) {
  return (
    <div className="flex gap-3 mb-2 last:mb-0">
      <span className="ff-mono text-[10px] text-saffron mt-0.5 flex-shrink-0">{n}</span>
      <span className={cn("text-[11.5px] leading-snug", empty ? "ff-mono text-ochre italic" : "italic ff-display text-ink-2")}>
        {empty ? text : `"${text}"`}
      </span>
    </div>
  );
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full grid place-items-center">
      <div className="text-center max-w-md px-6">{children}</div>
    </div>
  );
}

// ----------- the phone frame -----------

interface PhoneFrameProps {
  facility: { name: string };
  topology: Topology;
  origin: TopologyNode | null;
  destDept: Department | null;
  route: RouteResult | null;
  osm: OsmResponse | undefined;
  language: Lang;
}

function PhoneFrame({ facility, topology, origin, destDept, route, osm, language }: PhoneFrameProps) {
  // Pick a "current" step to render large in the carousel; default to first.
  const [stepIdx, setStepIdx] = useState(0);
  const [dragDx, setDragDx] = useState(0);
  useEffect(() => setStepIdx(0), [route]);

  const totalSteps = route?.edges.length ?? 0;
  const safeIdx = Math.min(stepIdx, Math.max(totalSteps - 1, 0));
  const currentEdge = route?.edges[safeIdx];
  const t = previewStrings[language];
  const userQuery = destDept ? t.userQuery(destDept.name) : t.userQueryEmpty;

  // Swipe handling: track pointer-down x, follow with rubber-band offset, commit
  // on release if the drag passed ~25% of the card width.
  const dragStartRef = useRef<{ x: number; id: number } | null>(null);
  const swipe = totalSteps > 1
    ? {
        onPointerDown: (e: React.PointerEvent) => {
          dragStartRef.current = { x: e.clientX, id: e.pointerId };
          (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
        },
        onPointerMove: (e: React.PointerEvent) => {
          if (!dragStartRef.current) return;
          setDragDx(e.clientX - dragStartRef.current.x);
        },
        onPointerUp: (e: React.PointerEvent) => {
          if (!dragStartRef.current) return;
          const dx = e.clientX - dragStartRef.current.x;
          dragStartRef.current = null;
          setDragDx(0);
          const threshold = 60;
          if (dx <= -threshold && safeIdx < totalSteps - 1) setStepIdx(safeIdx + 1);
          else if (dx >= threshold && safeIdx > 0) setStepIdx(safeIdx - 1);
        },
        onPointerCancel: () => {
          dragStartRef.current = null;
          setDragDx(0);
        },
      }
    : {};

  return (
    <div className="rise">
      <div className="relative" style={{ width: 340 }}>
        <div className="rounded-[40px] bg-ink p-[8px] shadow-[0_30px_70px_-20px_rgba(28,25,23,0.45),0_0_0_1px_rgba(28,25,23,0.1)]">
          <div className="rounded-[34px] bg-paper overflow-hidden phone-screen relative" style={{ height: 700 }}>
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[110px] h-[28px] bg-ink rounded-b-[18px] z-20" />

            <div className="px-7 pt-2.5 pb-1 flex items-center justify-between text-[10.5px] ff-mono text-ink relative z-10">
              <span>9:41</span>
              <span className="opacity-60">●●● · 5G · 87%</span>
            </div>

            <div className="px-5 pt-5 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="w-7 h-7 rounded-full bg-saffron grid place-items-center">
                  <Compass size={14} strokeWidth={1.5} className="text-paper" />
                </div>
                <div>
                  <div className="text-[10px] tracking-wide-2 small-caps text-slate-2 truncate max-w-[180px]">{facility.name}</div>
                  <div className="ff-display text-[15px] leading-none">Wayfinder</div>
                </div>
              </div>
              <button className="w-7 h-7 grid place-items-center text-slate-2">
                <Layers size={15} strokeWidth={1.5} />
              </button>
            </div>

            <div className="px-5 pt-5 space-y-3">
              <div className="flex justify-end">
                <div className="max-w-[80%] px-3 py-2 bg-ink text-paper rounded-2xl rounded-tr-sm text-[12.5px]">
                  {userQuery}
                </div>
              </div>

              <div className="flex justify-start">
                <div className="max-w-[88%] px-3.5 py-2.5 bg-paper-2 border border-hairline rounded-2xl rounded-tl-sm text-[12.5px] leading-relaxed">
                  {destDept ? (
                    <>
                      {t.headingPrefix}<span className="ff-display italic">{destDept.name}</span>
                      {destDept.building && t.inBuilding(destDept.building)}.
                    </>
                  ) : (
                    <>{t.pickDestination}</>
                  )}
                </div>
              </div>
            </div>

            <div className="mt-4 px-5">
              <div className="flex items-center gap-2 mb-2">
                <span className="ff-mono text-[9px] tracking-wide-3 small-caps text-saffron">
                  {totalSteps > 0 ? t.stepOf(safeIdx + 1, totalSteps) : t.noRoute}
                </span>
                <span className="flex-1 h-px bg-hairline" />
                <span className="ff-mono text-[9px] text-slate-2">
                  {route ? t.walkMin(route.totalWalkMin.toFixed(1)) : "—"}
                </span>
              </div>
              {totalSteps > 1 && route ? (
                <div
                  className="overflow-hidden touch-pan-y cursor-grab active:cursor-grabbing select-none -mx-1.5"
                  {...swipe}
                >
                  <div
                    className="flex"
                    style={{
                      transform: `translateX(calc(${-safeIdx * 100}% + ${dragDx}px))`,
                      transition: dragDx ? "none" : "transform 260ms cubic-bezier(0.22, 0.61, 0.36, 1)",
                    }}
                  >
                    {route.edges.map((edge, i) => (
                      <div key={i} className="w-full flex-shrink-0 px-1.5">
                        <div className="bg-paper border border-hairline rounded-2xl overflow-hidden">
                        <div className="aspect-[4/3] relative bg-paper-2">
                          <RouteSparkline topology={topology} origin={origin} route={route} highlightIdx={i} osm={osm} />
                        </div>
                        <div className="p-3.5 min-h-[88px]">
                          <p className="ff-display text-[15.5px] leading-snug text-ink">
                            {edge.instruction
                              ? `"${edge.instruction}"`
                              : <span className="ff-mono text-[12px] text-ochre italic">{t.noInstruction(labelFromId(route, i, "from"), labelFromId(route, i, "to"))}</span>}
                          </p>
                          {edge.instruction && language === "es" && (
                            <p className="ff-mono text-[8.5px] tracking-wide-2 small-caps text-slate-2 mt-2">
                              {t.authoredCaption}
                            </p>
                          )}
                        </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              ) : (
                <div className="bg-paper border border-hairline rounded-2xl overflow-hidden">
                  <div className="aspect-[4/3] relative bg-paper-2">
                    <RouteSparkline topology={topology} origin={origin} route={route} highlightIdx={safeIdx} osm={osm} />
                  </div>
                  <div className="p-3.5 min-h-[88px]">
                    {currentEdge ? (
                      <>
                        <p className="ff-display text-[15.5px] leading-snug text-ink">
                          {currentEdge.instruction
                            ? `"${currentEdge.instruction}"`
                            : <span className="ff-mono text-[12px] text-ochre italic">{t.noInstruction(labelFromId(route, safeIdx, "from"), labelFromId(route, safeIdx, "to"))}</span>}
                        </p>
                        {currentEdge.instruction && language === "es" && (
                          <p className="ff-mono text-[8.5px] tracking-wide-2 small-caps text-slate-2 mt-2">
                            {t.authoredCaption}
                          </p>
                        )}
                      </>
                    ) : route?.edges.length === 0 ? (
                      <p className="ff-display italic text-[14.5px] text-slate">{t.alreadyThere}</p>
                    ) : (
                      <p className="ff-display italic text-[14.5px] text-slate">{t.noPath}</p>
                    )}
                  </div>
                </div>
              )}
              {totalSteps > 1 && (
                <div className="mt-2 flex items-center gap-1 justify-center">
                  {Array.from({ length: totalSteps }).map((_, i) => (
                    <button
                      key={i}
                      onClick={() => setStepIdx(i)}
                      className={cn("w-1.5 h-1.5 rounded-full", i === safeIdx ? "bg-saffron" : "bg-slate-3")}
                    />
                  ))}
                </div>
              )}
            </div>

            <div className="absolute bottom-5 left-1/2 -translate-x-1/2">
              <button className="w-14 h-14 rounded-full bg-saffron grid place-items-center text-paper shadow-[0_10px_22px_-6px_rgba(184,83,10,0.6)]">
                <Mic size={22} strokeWidth={1.5} />
              </button>
            </div>
          </div>
        </div>

        <div className="absolute -left-32 top-32 w-28 text-right">
          <div className="ff-mono text-[9px] tracking-wide-3 small-caps text-saffron">A</div>
          <div className="ff-display italic text-[11px] text-slate mt-1 leading-tight">
            Header pulls the live facility name from the loaded topology.
          </div>
        </div>
        <div className="absolute -right-36 top-[330px] w-32">
          <div className="ff-mono text-[9px] tracking-wide-3 small-caps text-saffron">B</div>
          <div className="ff-display italic text-[11px] text-slate mt-1 leading-tight">
            Step card renders the actual edge instruction. Saffron path traces the Dijkstra route.
          </div>
        </div>
        <div className="absolute -right-32 bottom-24 w-28">
          <div className="ff-mono text-[9px] tracking-wide-3 small-caps text-saffron">C</div>
          <div className="ff-display italic text-[11px] text-slate mt-1 leading-tight">
            Mic for re-orientation: "I see a fountain..."
          </div>
        </div>
      </div>
    </div>
  );
}

function labelFromId(route: RouteResult | null, idx: number, which: "from" | "to"): string {
  if (!route) return "—";
  const edge = route.edges[idx];
  if (!edge) return "—";
  return which === "from" ? edge.origin : edge.arrival;
}

interface SparklineProps {
  topology: Topology;
  origin: TopologyNode | null;
  route: RouteResult | null;
  highlightIdx: number;
  osm: OsmResponse | undefined;
}

// Fixed viewBox + padding for the phone mini-map.
const VB_W = 200;
const VB_H = 150;
const VB_PAD = 12;

/** Tiny SVG of the campus + route projected into a 200×150 viewBox. */
function RouteSparkline({ topology, origin, route, highlightIdx, osm }: SparklineProps) {
  // Walk the route into a sequence of node ids: [origin, arrival_0, ...]
  const routeCoords: Array<{ lat: number; lng: number }> = (() => {
    if (!route || route.edges.length === 0) return [];
    const ids: string[] = [route.edges[0].origin];
    for (const e of route.edges) ids.push(e.arrival);
    return ids
      .map((id) => topology.nodes.find((n) => n.id === id))
      .filter((n): n is TopologyNode => !!n)
      .map((n) => ({ lat: n.lat, lng: n.lng }));
  })();

  // Bounds: union of building footprints (when present) so the route lands in
  // the campus context, not zoomed in on its own corner. Falls back to the
  // route or origin if OSM hasn't loaded yet.
  const bounds = computeBounds([
    ...(osm?.features ?? []).flatMap((f) => f.polygon ?? []).map(([lat, lng]) => ({ lat, lng })),
    ...routeCoords,
    ...(origin ? [{ lat: origin.lat, lng: origin.lng }] : []),
  ]);

  // No bounds at all → empty-state grid (route hasn't loaded, no OSM).
  if (!bounds) {
    return (
      <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="absolute inset-0 w-full h-full">
        <rect width={VB_W} height={VB_H} fill="#EDE6D2" />
        <pattern id="phone-dots-empty" width="6" height="6" patternUnits="userSpaceOnUse">
          <circle cx="0.5" cy="0.5" r="0.5" fill="#D9D2C2" />
        </pattern>
        <rect width={VB_W} height={VB_H} fill="url(#phone-dots-empty)" opacity="0.7" />
      </svg>
    );
  }

  const project = (lat: number, lng: number): [number, number] => [
    VB_PAD + ((lng - bounds.minLng) / bounds.spanLng) * (VB_W - VB_PAD * 2),
    VB_PAD + (1 - (lat - bounds.minLat) / bounds.spanLat) * (VB_H - VB_PAD * 2),
  ];

  const polyToD = (poly: [number, number][]): string =>
    poly.map(([lat, lng], i) => {
      const [x, y] = project(lat, lng);
      return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
    }).join(" ");

  const routePts = routeCoords.map((c) => project(c.lat, c.lng));
  const routeD = routePts
    .map((p, i) => `${i === 0 ? "M" : "L"} ${p[0].toFixed(1)} ${p[1].toFixed(1)}`)
    .join(" ");

  return (
    <svg viewBox={`0 0 ${VB_W} ${VB_H}`} className="absolute inset-0 w-full h-full">
      {/* Paper base + dot grid */}
      <rect width={VB_W} height={VB_H} fill="#EDE6D2" />
      <pattern id="phone-dots" width="6" height="6" patternUnits="userSpaceOnUse">
        <circle cx="0.5" cy="0.5" r="0.5" fill="#D9D2C2" />
      </pattern>
      <rect width={VB_W} height={VB_H} fill="url(#phone-dots)" opacity="0.7" />

      {/* Building footprints — paper-3 fills behind everything. Parking gets
          a slightly darker tint so it reads as a different surface. */}
      {(osm?.features ?? []).map((feat, i) => {
        if (!Array.isArray(feat.polygon) || feat.polygon.length < 3) return null;
        const isParking = feat.amenity === "parking" || feat.building === "parking";
        return (
          <path
            key={`b${i}`}
            d={polyToD(feat.polygon) + " Z"}
            fill={isParking ? "#DAD2BC" : "#E5DCC4"}
            stroke="#928D82"
            strokeWidth={0.4}
          />
        );
      })}

      {/* OSM footways — faint sky lines so the route polyline still reads as
          the dominant path. Mirrors the editor's footways layer. */}
      {(osm?.footways ?? []).map((way, i) => {
        if (!Array.isArray(way) || way.length < 2) return null;
        return (
          <path
            key={`f${i}`}
            d={polyToD(way)}
            stroke="#1E3A5F"
            strokeWidth={0.5}
            fill="none"
            opacity={0.35}
          />
        );
      })}

      {/* Route polyline (saffron) — drawn over the campus */}
      {routePts.length >= 2 && (
        <path d={routeD} stroke="#B8530A" strokeWidth="2" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      )}

      {/* Origin / step / arrival dots */}
      {routePts.length >= 2 ? (
        routePts.map((p, i) => {
          const isStart = i === 0;
          const isEnd = i === routePts.length - 1;
          const isCurrent = i === highlightIdx + 1;
          return (
            <circle
              key={`d${i}`}
              cx={p[0]}
              cy={p[1]}
              r={isStart || isEnd ? 4 : isCurrent ? 4 : 3}
              fill={isStart ? "#1E3A5F" : isEnd ? "#B8530A" : isCurrent ? "#B8530A" : "#928D82"}
              stroke="#F4EFE5"
              strokeWidth={isStart || isEnd ? 2 : 1.5}
              opacity={isStart || isEnd || isCurrent ? 1 : 0.65}
            />
          );
        })
      ) : origin ? (
        // Empty route but we know where the patient stands.
        (() => {
          const [x, y] = project(origin.lat, origin.lng);
          return <circle cx={x} cy={y} r={5} fill="#1E3A5F" stroke="#F4EFE5" strokeWidth={2} />;
        })()
      ) : null}
    </svg>
  );
}

function computeBounds(coords: Array<{ lat: number; lng: number }>): {
  minLat: number; maxLat: number; minLng: number; maxLng: number;
  spanLat: number; spanLng: number;
} | null {
  if (coords.length === 0) return null;
  let minLat = Infinity, maxLat = -Infinity, minLng = Infinity, maxLng = -Infinity;
  for (const c of coords) {
    if (c.lat < minLat) minLat = c.lat;
    if (c.lat > maxLat) maxLat = c.lat;
    if (c.lng < minLng) minLng = c.lng;
    if (c.lng > maxLng) maxLng = c.lng;
  }
  return {
    minLat, maxLat, minLng, maxLng,
    spanLat: Math.max(maxLat - minLat, 1e-6),
    spanLng: Math.max(maxLng - minLng, 1e-6),
  };
}
