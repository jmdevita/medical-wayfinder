import { Loader2 } from "lucide-react";
import { useCurrentSettings, useTestConnection } from "@/lib/api";
import { useAtlasStore } from "@/lib/store";
import { Section } from "@/components/ui/Section";
import { StatusDot } from "@/components/ui/StatusDot";
import { cn } from "@/lib/utils";

export function SettingsView() {
  const { data: cfg } = useCurrentSettings();

  return (
    <div className="h-full overflow-y-auto">
      <div className="px-12 py-10 max-w-[1100px] mx-auto rise">
        <div className="mb-10">
          <div className="flex items-baseline gap-3 mb-3">
            <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron">Atlas / Settings</span>
            <span className="h-px flex-1 bg-hairline" />
          </div>
          <h1 className="ff-display text-[44px] leading-tight tracking-tight">
            Workspace, <span className="italic">keys</span>, and where things ship to.
          </h1>
        </div>

        <Section num="01" title="Models & APIs">
          <p className="text-[12px] text-slate mb-4 italic ff-display max-w-[640px]">
            All four jobs share the same OpenAI-compatible endpoint configured in
            <span className="ff-mono not-italic mx-1 text-ink">training/.env</span>. Click "Test
            connection" to ping it with a 2-token request and see actual latency.
          </p>
          <div className="grid grid-cols-2 gap-4">
            <KeyCard
              cardKey="dept-extract"
              title="Department extraction"
              sub="Fetches hospital pages, extracts departments via LLM"
              host={cfg?.base_url ?? "—"}
              model={cfg?.model ?? "—"}
            />
            <KeyCard
              cardKey="edge-draft"
              title="Edge prose drafting"
              sub="Routes between nodes via OSM footways (no LLM)"
              host="(no API call)"
              model="footway graph"
              disabled
            />
            <KeyCard
              cardKey="alias-expand"
              title="Alias expansion"
              sub="Expands department aliases EN+ES via LLM"
              host={cfg?.base_url ?? "—"}
              model={cfg?.model ?? "—"}
            />
            <KeyCard
              cardKey="multimodal-map"
              title="Multimodal map ingest"
              sub="Future: read PDF maps with a vision model"
              host="(not configured)"
              model="—"
              disabled
            />
          </div>
        </Section>

        <Section num="02" title="Publishing">
          <div className="space-y-2">
            <PubRow
              target="GitHub · jmdevita/medical-wayfinder"
              href="https://github.com/jmdevita/medical-wayfinder"
              sub="Publish writes to health_wayfinder/assets/facilities/ (via the atlas/data/facilities symlink) in the GitHub-tracked repo. Always on."
              status="active"
            />
          </div>
        </Section>

        <Section num="03" title="Storage">
          <div className="grid grid-cols-2 gap-4">
            <PathCard label="Facilities directory" path={cfg?.facilities_dir ?? "—"} hint="Published facility + topology JSON" />
            <PathCard label="Drafts directory"     path={cfg?.bootstrap_dir  ?? "—"} hint="In-progress drafts (OSM seed + edits)" />
          </div>
        </Section>

        <Section num="04" title="CORS origins">
          <p className="text-[12px] text-slate mb-3 italic ff-display">
            Browsers allowed to call the API. Set <span className="ff-mono not-italic text-ink">ATLAS_CORS_ORIGINS</span> to a comma-separated list when deploying.
          </p>
          <div className="space-y-1">
            {(cfg?.cors_origins ?? []).map((origin) => (
              <div key={origin} className="ff-mono text-[11.5px] text-slate bg-paper-2 border border-hairline rounded-sm px-3 py-1.5">
                {origin}
              </div>
            ))}
            {!cfg?.cors_origins.length && (
              <div className="ff-mono text-[11.5px] text-rust bg-rust/5 border border-rust/30 rounded-sm px-3 py-1.5">
                Empty — no browser will be able to reach the API. Set ATLAS_CORS_ORIGINS.
              </div>
            )}
          </div>
        </Section>
      </div>
    </div>
  );
}

interface KeyCardProps {
  cardKey: string;
  title: string;
  sub: string;
  host: string;
  model: string;
  disabled?: boolean;
}

function KeyCard({ cardKey, title, sub, host, model, disabled }: KeyCardProps) {
  const test = useTestConnection();
  // Persist the last result in the global store so it survives unmount when
  // the user navigates away from /settings and back.
  const stored = useAtlasStore((s) => s.connectionTests[cardKey]);
  const setStored = useAtlasStore((s) => s.setConnectionTest);

  const onTest = () => {
    test.mutate(
      {},
      {
        onSuccess: (res) =>
          setStored(cardKey, {
            ok: res.ok,
            latencyMs: res.latency_ms ?? undefined,
            error: res.error ?? undefined,
            sample: res.sample ?? undefined,
            testedAt: Date.now(),
          }),
      },
    );
  };

  // Source of truth for the dot/label is whichever exists: the in-flight
  // mutation (transient) or the persisted last result (after unmount/remount).
  const inFlight = test.isPending;
  const result = stored;
  const dot = inFlight
    ? "#A98024"
    : !result
      ? "#928D82"
      : result.ok
        ? "#516B53"
        : "#9A3412";
  const label = inFlight
    ? "Testing…"
    : !result
      ? "Not tested"
      : result.ok
        ? `OK · ${result.latencyMs}ms`
        : "Failed";

  return (
    <div className="bg-paper border border-hairline rounded-sm p-4">
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className="ff-display text-[16px] leading-tight">{title}</h3>
          <p className="text-[11px] ff-mono text-slate-2 mt-1 leading-relaxed">{sub}</p>
        </div>
        <span className="flex items-center gap-1.5 ff-mono text-[10px] tracking-wide-2 small-caps">
          <StatusDot color={dot} pulse={inFlight} /> {label}
        </span>
      </div>
      <div className="ff-mono text-[10.5px] text-slate bg-paper-2 px-2.5 py-1.5 border border-hairline rounded-sm overflow-hidden text-ellipsis whitespace-nowrap">
        {host}
      </div>
      <div className="ff-mono text-[10px] text-slate-2 mt-1 truncate">model: {model}</div>
      <div className="mt-3 flex items-center gap-3 text-[10.5px] tracking-wide-2 small-caps">
        <button
          onClick={onTest}
          disabled={disabled || inFlight}
          className={cn(
            "flex items-center gap-1.5 transition-colors",
            disabled
              ? "text-slate-3 cursor-not-allowed"
              : inFlight
                ? "text-slate-2"
                : "text-saffron hover:text-saff-2",
          )}
        >
          {inFlight && <Loader2 size={11} className="animate-spin" strokeWidth={1.5} />}
          Test connection
        </button>
      </div>
      {result?.error && (
        <p className="mt-2 ff-mono text-[10.5px] text-rust leading-snug">{result.error}</p>
      )}
      {result?.ok && result.sample && (
        <p className="mt-2 ff-mono text-[10.5px] text-slate leading-snug">
          sample: <span className="italic">"{result.sample}"</span>
        </p>
      )}
    </div>
  );
}

type PubStatus = "active" | "planned" | "off";

const PUB_META: Record<PubStatus, { dot: string; label: string }> = {
  active:  { dot: "#516B53", label: "Active" },
  planned: { dot: "#A98024", label: "Planned" },
  off:     { dot: "#928D82", label: "Off" },
};

function PubRow({
  target,
  sub,
  status,
  href,
}: {
  target: string;
  sub: string;
  status: PubStatus;
  /** Optional outbound link. When provided, the `target` label renders as a
   *  hyperlink that opens in a new tab. */
  href?: string;
}) {
  const meta = PUB_META[status];
  return (
    <div className="flex items-center gap-4 px-4 py-3 bg-paper border border-hairline rounded-sm">
      <StatusDot color={meta.dot} />
      <div className="flex-1">
        <div className="ff-display text-[15px] leading-tight">
          {href ? (
            <a
              href={href}
              target="_blank"
              rel="noreferrer"
              className="hover:text-saffron hover:underline underline-offset-2 decoration-saffron/60 transition-colors"
            >
              {target}
            </a>
          ) : (
            target
          )}
        </div>
        <div className="text-[11.5px] text-slate mt-0.5">{sub}</div>
      </div>
      <span className="ff-mono text-[10px] tracking-wide-2 small-caps text-slate-2">{meta.label}</span>
    </div>
  );
}

function PathCard({ label, path, hint }: { label: string; path: string; hint: string }) {
  return (
    <div className="bg-paper border border-hairline rounded-sm p-4">
      <div className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron mb-1">{label}</div>
      <div className="ff-mono text-[11px] text-slate bg-paper-2 border border-hairline rounded-sm px-2.5 py-1.5 break-all">
        {path}
      </div>
      <p className="text-[11.5px] text-slate-2 mt-2 italic ff-display">{hint}</p>
    </div>
  );
}

