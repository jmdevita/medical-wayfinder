import { useState } from "react";
import { Check, Loader2, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import {
  useAcceptSuggestion,
  useDiscardSuggestion,
  useGenerateFromPhotos,
  useRegenerateSuggestion,
  type Suggestion,
  type SuggestionSource,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  slug: string;
  fromId: string;
  toId: string;
  /** All suggestions in the sidecar; we filter to this edge here. */
  suggestions: Suggestion[];
  /** Editor's preference (from the Photos section above) for whether to
   * replace edge geometry with the photo-derived polyline on approve. */
  replaceGeometry: boolean;
}

/**
 * Inline drafts panel inside EdgeInspector. One card per source
 * (streetview, user_photos). Each card holds Approve / Regenerate / Discard.
 * The non-active card collapses to a one-liner with a Generate button.
 *
 * Single inspector-resident surface for both Street View and user-photo
 * drafts (the prior modal flow was retired in the docs/30 redesign).
 */
export function DraftsSection({
  slug, fromId, toId, suggestions, replaceGeometry,
}: Props) {
  const sv = suggestions.find(
    (s) => s.from === fromId && s.to === toId
      && (s.source ?? "streetview") === "streetview",
  );
  const photo = suggestions.find(
    (s) => s.from === fromId && s.to === toId && s.source === "user_photos",
  );

  // Most-recent draft is the active one; the other collapses.
  const activeSource: SuggestionSource =
    photo && sv
      ? (new Date(photo.generated_at) > new Date(sv.generated_at) ? "user_photos" : "streetview")
      : photo ? "user_photos"
      : sv ? "streetview"
      : "streetview"; // both null — show streetview generate button by default

  return (
    <div className="space-y-3">
      <DraftCard
        source="streetview"
        active={activeSource === "streetview"}
        suggestion={sv}
        slug={slug}
        fromId={fromId}
        toId={toId}
        replaceGeometry={replaceGeometry}
      />
      <DraftCard
        source="user_photos"
        active={activeSource === "user_photos"}
        suggestion={photo}
        slug={slug}
        fromId={fromId}
        toId={toId}
        replaceGeometry={replaceGeometry}
      />
    </div>
  );
}

interface CardProps {
  source: SuggestionSource;
  active: boolean;
  suggestion: Suggestion | undefined;
  slug: string;
  fromId: string;
  toId: string;
  replaceGeometry: boolean;
}

function DraftCard({
  source, active, suggestion, slug, fromId, toId, replaceGeometry,
}: CardProps) {
  const accept = useAcceptSuggestion();
  const discard = useDiscardSuggestion();
  const regenerate = useRegenerateSuggestion();
  const photoRegen = useGenerateFromPhotos();
  const [collapsed, setCollapsed] = useState(!active);

  const inFlight =
    accept.isPending || discard.isPending ||
    regenerate.isPending || photoRegen.isPending;
  const sourceLabel = source === "user_photos" ? "Photo draft" : "Street View draft";

  const onRegenerate = () => {
    if (source === "user_photos") {
      photoRegen.mutate({ slug, fromId, toId });
    } else {
      regenerate.mutate({ slug, fromId, toId });
    }
  };

  // No suggestion yet → render a single-line Generate button.
  if (!suggestion) {
    return (
      <button
        onClick={onRegenerate}
        disabled={inFlight}
        className={cn(
          "w-full flex items-center gap-2 px-3 h-9 rounded-sm border border-hairline bg-paper text-[11.5px] tracking-wide-2 small-caps text-slate hover:text-ink hover:bg-paper-2 transition-colors",
          inFlight && "opacity-60 cursor-wait",
        )}
      >
        {(regenerate.isPending || photoRegen.isPending) ? (
          <Loader2 size={11} className="animate-spin" strokeWidth={1.5} />
        ) : (
          <Sparkles size={11} className="text-saffron" strokeWidth={1.5} />
        )}
        Generate {sourceLabel.toLowerCase()}
        {regenerate.isError && source === "streetview" && (
          <span className="ml-auto text-rust ff-mono text-[10px]">
            {(regenerate.error as Error)?.message}
          </span>
        )}
        {photoRegen.isError && source === "user_photos" && (
          <span className="ml-auto text-rust ff-mono text-[10px]">
            {(photoRegen.error as Error)?.message}
          </span>
        )}
      </button>
    );
  }

  const verdict = suggestion.coverage?.verdict;
  const verdictClass =
    verdict === "pass" ? "text-moss border-moss/40 bg-moss/10"
    : verdict === "warn" ? "text-ochre border-ochre/40 bg-ochre/10"
    : verdict === "fail" ? "text-rust border-rust/40 bg-rust/10"
    : "text-slate-2 border-hairline bg-paper-2";

  const meta = source === "user_photos"
    ? `drafted from ${suggestion.photo_metadata?.photo_ids.length ?? 0} photos · ${suggestion.photo_metadata?.gps_count ?? 0} GPS`
    : `${suggestion.evidence?.pano_ids.length ?? 0} panos · ${suggestion.evidence?.model ?? "—"}`;

  // Collapsed one-liner.
  if (collapsed) {
    return (
      <button
        onClick={() => setCollapsed(false)}
        className="w-full flex items-center gap-2 px-3 h-9 rounded-sm border border-hairline bg-paper text-[11px] tracking-wide-2 small-caps text-slate hover:text-ink hover:bg-paper-2 transition-colors"
      >
        <span className="text-saffron">{sourceLabel}</span>
        <span className="text-slate-2 normal-case tracking-normal italic ff-display flex-1 text-left truncate">
          "{suggestion.instruction}"
        </span>
        <span className="ff-mono text-[10px] text-slate-2">expand</span>
      </button>
    );
  }

  return (
    <div className="border border-hairline rounded-sm p-3 bg-paper">
      <div className="flex items-center gap-2 mb-2">
        <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron">
          {sourceLabel}
        </span>
        <span className="flex-1 h-px bg-hairline" />
        {verdict && source === "streetview" && (
          <span className={cn(
            "px-2 py-0.5 rounded-sm border ff-mono text-[10px] tracking-wide-2 small-caps",
            verdictClass,
          )}>
            {verdict}
          </span>
        )}
        <button
          onClick={() => setCollapsed(true)}
          className="ff-mono text-[10px] text-slate-2 hover:text-ink"
        >
          collapse
        </button>
      </div>

      <p className="ff-display italic text-[14px] leading-relaxed text-ink">
        "{suggestion.instruction}"
      </p>

      <p className="ff-mono text-[10.5px] text-slate-2 mt-2">{meta}</p>

      {accept.isSuccess && (
        <div className="mt-2 flex items-center gap-2 text-moss text-[11.5px]">
          <Check size={13} strokeWidth={2} /> Approved.
        </div>
      )}

      {(accept.isError || discard.isError) && (
        <p className="ff-mono text-[10.5px] text-rust mt-2">
          {((accept.error || discard.error) as Error)?.message}
        </p>
      )}

      <div className="flex items-center gap-2 mt-3">
        <button
          onClick={() => accept.mutate({
            slug, fromId, toId,
            replaceGeometry: source === "user_photos" ? replaceGeometry : true,
          })}
          disabled={!suggestion.instruction || inFlight || accept.isSuccess}
          className={cn(
            "px-3 h-8 rounded-sm text-[11px] tracking-wide-2 small-caps flex items-center gap-1.5 transition-colors",
            !inFlight && !accept.isSuccess && suggestion.instruction
              ? "bg-saffron text-paper hover:bg-saff-2"
              : "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed",
          )}
        >
          {accept.isPending && <Loader2 size={10} className="animate-spin" strokeWidth={1.5} />}
          Approve
        </button>
        <button
          onClick={onRegenerate}
          disabled={inFlight || accept.isSuccess}
          className="px-3 h-8 text-[11px] tracking-wide-2 small-caps text-slate hover:text-ink flex items-center gap-1.5 disabled:opacity-40"
        >
          {(regenerate.isPending || photoRegen.isPending) ? (
            <Loader2 size={10} className="animate-spin" strokeWidth={1.5} />
          ) : (
            <RefreshCw size={10} strokeWidth={1.5} />
          )}
          Regenerate
        </button>
        <button
          onClick={() => discard.mutate({ slug, fromId, toId })}
          disabled={inFlight}
          className="px-3 h-8 text-[11px] tracking-wide-2 small-caps text-slate hover:text-rust flex items-center gap-1.5 disabled:opacity-40"
        >
          {discard.isPending ? (
            <Loader2 size={10} className="animate-spin" strokeWidth={1.5} />
          ) : (
            <Trash2 size={10} strokeWidth={1.5} />
          )}
          Discard
        </button>
      </div>
    </div>
  );
}
