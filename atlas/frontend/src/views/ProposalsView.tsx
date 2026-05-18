import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { AlertTriangle, Check, Loader2, X as XIcon } from "lucide-react";
import {
  useApproveProposal,
  useProposalsList,
  useRejectProposal,
  useWhoAmI,
  type ProposalSummary,
} from "@/lib/api";
import { cn } from "@/lib/utils";

/**
 * Admin-only review queue. Lists every proposal in `pending` or
 * `needs_changes` status across both contributor personal drafts and
 * facility_editor shared-bootstrap submissions. Approve runs the existing
 * publish flow; reject writes a `needs_changes` sidecar with an optional
 * note so the author can iterate.
 */
export function ProposalsView() {
  const { data: who, isPending: whoLoading } = useWhoAmI();
  const list = useProposalsList();

  if (whoLoading) {
    return <Centered><Loader2 size={20} className="animate-spin text-saffron" /></Centered>;
  }

  if (!who || who.role !== "admin") {
    return (
      <Centered>
        <p className="ff-mono text-[10px] tracking-wide-3 small-caps text-rust mb-2">
          Admin only
        </p>
        <p className="ff-display text-[18px] mb-2">Proposals are reviewed by the workspace admin.</p>
        <Link to="/" className="ff-mono text-[11px] small-caps text-saffron">← back</Link>
      </Centered>
    );
  }

  const proposals = list.data ?? [];
  const pending = proposals.filter((p) => p.status === "pending");
  const needsChanges = proposals.filter((p) => p.status === "needs_changes");

  return (
    <div className="h-full overflow-y-auto bg-paper">
      <div className="max-w-[920px] mx-auto px-8 py-10">
        <div className="mb-8">
          <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron">
            Atlas / Proposals
          </span>
          <h1 className="ff-display text-[36px] mt-1 mb-2">Pending review</h1>
          <p className="text-[13px] text-slate leading-relaxed max-w-[560px]">
            Every proposal goes through here before reaching the on-device
            app. Approve runs the same publish flow you'd run yourself; reject
            keeps the author's draft intact so they can iterate.
          </p>
        </div>

        {list.isPending && <p className="ff-mono text-[11px] text-slate-2">Loading…</p>}
        {list.isError && (
          <p className="ff-mono text-[11px] text-rust">{(list.error as Error).message}</p>
        )}

        {!list.isPending && proposals.length === 0 && (
          <div className="border border-hairline rounded-sm px-6 py-10 text-center">
            <p className="ff-display italic text-[18px] text-slate mb-1">Nothing to review.</p>
            <p className="text-[12px] text-slate-2">
              Contributors and facility_editors will show up here when they submit.
            </p>
          </div>
        )}

        {pending.length > 0 && (
          <Section title="Awaiting review" count={pending.length}>
            {pending.map((p) => (
              <ProposalCard key={`${p.slug}-${p.author}`} p={p} />
            ))}
          </Section>
        )}

        {needsChanges.length > 0 && (
          <Section title="Needs changes" count={needsChanges.length} subdued>
            {needsChanges.map((p) => (
              <ProposalCard key={`${p.slug}-${p.author}`} p={p} />
            ))}
          </Section>
        )}
      </div>
    </div>
  );
}

function Section({
  title,
  count,
  subdued,
  children,
}: {
  title: string;
  count: number;
  subdued?: boolean;
  children: React.ReactNode;
}) {
  return (
    <section className="mb-10">
      <div className="flex items-baseline gap-2 mb-3">
        <span
          className={cn(
            "ff-mono text-[10px] tracking-wide-3 small-caps",
            subdued ? "text-slate-2" : "text-saffron",
          )}
        >
          {title} · {count}
        </span>
        <span className="flex-1 h-px bg-hairline" />
      </div>
      <div className="space-y-3">{children}</div>
    </section>
  );
}

function ProposalCard({ p }: { p: ProposalSummary }) {
  const approve = useApproveProposal();
  const reject = useRejectProposal();
  const [showRejectNote, setShowRejectNote] = useState(false);
  const [note, setNote] = useState("");

  const isAwaiting = p.status === "pending";
  const inFlight = approve.isPending || reject.isPending;

  return (
    <article className="border border-hairline rounded-sm bg-paper-2 p-5">
      <header className="flex items-start gap-4 mb-3">
        <div className="flex-1">
          <div className="flex items-baseline gap-2 mb-1">
            <span className="ff-display text-[18px] italic">{p.slug}</span>
            <span className="ff-mono text-[10px] tracking-wide-2 text-slate-2">
              by {p.author}
            </span>
            <span className="ff-mono text-[10px] tracking-wide-2 text-slate-3">
              · {p.source === "personal_draft" ? "personal draft" : "shared facility"}
            </span>
          </div>
          <p className="text-[13px] leading-snug">{p.message || <span className="italic text-slate-2">(no message)</span>}</p>
          {p.review_note && (
            <p className="ff-mono text-[10.5px] text-ochre mt-2">
              Last note: {p.review_note}
            </p>
          )}
        </div>
        <span className="ff-mono text-[10px] text-slate-2">
          {formatTimestamp(p.submitted_at)}
        </span>
      </header>

      {p.issues.length > 0 && (
        <div className="space-y-1 mb-3">
          {p.issues.map((iss, i) => (
            <div key={i} className="flex items-start gap-2 px-2.5 py-1.5 bg-rust/5 border border-rust/30 rounded-sm">
              <AlertTriangle size={12} className="text-rust mt-0.5 flex-shrink-0" strokeWidth={1.5} />
              <span className="text-[11.5px] leading-snug">{iss}</span>
            </div>
          ))}
        </div>
      )}
      {p.warnings.length > 0 && (
        <div className="space-y-1 mb-3">
          {p.warnings.map((w, i) => (
            <div key={i} className="flex items-start gap-2 px-2.5 py-1.5 bg-ochre/8 border border-ochre/30 rounded-sm">
              <AlertTriangle size={12} className="text-ochre mt-0.5 flex-shrink-0" strokeWidth={1.5} />
              <span className="text-[11.5px] leading-snug">{w}</span>
            </div>
          ))}
        </div>
      )}

      {showRejectNote && (
        <div className="mb-3">
          <textarea
            value={note}
            onChange={(e) => setNote(e.target.value)}
            placeholder="Optional — what should the author change?"
            rows={2}
            className="w-full bg-paper border border-hairline rounded-sm p-2 text-[12px] resize-none ff-display focus:border-saffron outline-none"
          />
        </div>
      )}

      <footer className="flex items-center justify-end gap-2">
        {(approve.isError || reject.isError) && (
          <span className="ff-mono text-[10px] text-rust mr-auto">
            {((approve.error || reject.error) as Error)?.message}
          </span>
        )}
        {showRejectNote ? (
          <>
            <button
              onClick={() => setShowRejectNote(false)}
              disabled={inFlight}
              className="px-3 h-8 text-[11px] tracking-wide-2 small-caps text-slate hover:text-ink"
            >
              Cancel
            </button>
            <button
              onClick={() =>
                reject.mutate(
                  { slug: p.slug, author: p.author, reviewNote: note.trim() || undefined },
                  { onSuccess: () => { setShowRejectNote(false); setNote(""); } },
                )
              }
              disabled={inFlight}
              className="px-3 h-8 bg-rust text-paper text-[11px] tracking-wide-2 small-caps rounded-sm flex items-center gap-1.5"
            >
              {reject.isPending && <Loader2 size={12} className="animate-spin" strokeWidth={1.5} />}
              <XIcon size={12} strokeWidth={1.5} /> Confirm reject
            </button>
          </>
        ) : (
          <>
            <button
              onClick={() => setShowRejectNote(true)}
              disabled={inFlight || !isAwaiting}
              className="px-3 h-8 text-[11px] tracking-wide-2 small-caps text-rust hover:bg-rust/10 rounded-sm disabled:opacity-50"
            >
              Reject
            </button>
            <button
              onClick={() => approve.mutate({ slug: p.slug, author: p.author, force: p.issues.length > 0 })}
              disabled={inFlight || !isAwaiting}
              className={cn(
                "px-3 h-8 text-[11px] tracking-wide-2 small-caps rounded-sm flex items-center gap-1.5",
                isAwaiting && !inFlight
                  ? "bg-ink text-paper hover:bg-ink-2"
                  : "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed",
              )}
            >
              {approve.isPending && <Loader2 size={12} className="animate-spin" strokeWidth={1.5} />}
              <Check size={12} strokeWidth={1.5} />
              {p.issues.length > 0 ? "Approve (force)" : "Approve & publish"}
            </button>
          </>
        )}
      </footer>
    </article>
  );
}

function formatTimestamp(iso: string): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function Centered({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full grid place-items-center">
      <div className="text-center max-w-md px-6">{children}</div>
    </div>
  );
}
