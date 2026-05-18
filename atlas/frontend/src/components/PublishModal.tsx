import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ArrowRight, AlertTriangle, Check, Loader2, X as XIcon } from "lucide-react";
import {
  usePublish,
  usePublishDryRun,
  useSubmitProposal,
  useWhoAmI,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onClose: () => void;
  slug: string | null;
  facilityName: string | null;
}

/**
 * Dual-purpose modal: same UX, different terminal action depending on the
 * caller's role.
 *
 *   admin             → Publish (writes to FACILITIES_DIR, which is symlinked to the Flutter assets dir)
 *   facility_editor   → Submit for review (writes proposal.json into bootstrap dir)
 *   contributor       → Submit for review (writes proposal.json into personal-draft dir)
 *
 * The validation checklist (publish dry-run) renders in all modes so the
 * author sees what the admin will see at review time. Force-publish is
 * admin-only — non-admin proposals can pass validation issues forward to
 * the admin's queue but never bypass them.
 */
export function PublishModal({ open, onClose, slug, facilityName }: Props) {
  const { data: who } = useWhoAmI();
  const role = who?.role ?? "viewer";
  const isAdmin = role === "admin";

  const dryRun = usePublishDryRun(open ? slug : null);
  const publish = usePublish();
  const submit = useSubmitProposal();
  const qc = useQueryClient();
  const [forceMode, setForceMode] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!open) {
      publish.reset();
      submit.reset();
      setForceMode(false);
      setMessage("");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  useEffect(() => {
    if (open && slug) {
      qc.invalidateQueries({ queryKey: ["publish-dry-run", slug] });
    }
  }, [open, slug, qc]);

  if (!open || !slug) return null;

  const issues = dryRun.data?.issues ?? [];
  const warnings = dryRun.data?.warnings ?? [];
  const ok = dryRun.data?.ok ?? false;
  const canPublish = isAdmin && (ok || forceMode);
  const canSubmit = !isAdmin && message.trim().length > 0;

  const inFlight = publish.isPending || submit.isPending;
  const succeeded = publish.isSuccess || submit.isSuccess;

  return (
    <div className="fixed inset-0 z-[1000] flex items-center justify-center p-6 bg-ink/40 backdrop-blur-sm rise">
      <div className="bg-paper rounded-sm crisp-shadow-strong w-[600px] max-w-full overflow-hidden">
        <header className="flex items-center justify-between px-6 h-12 border-b border-hairline">
          <div className="flex items-baseline gap-2">
            <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron">
              Atlas / {isAdmin ? "Publish" : "Submit for review"}
            </span>
            <span className="ff-display italic text-[15px]">{facilityName ?? slug}</span>
          </div>
          <button onClick={onClose} disabled={inFlight} className="text-slate hover:text-ink disabled:opacity-40">
            <XIcon size={16} strokeWidth={1.5} />
          </button>
        </header>

        <div className="px-6 py-5 space-y-4">
          {publish.isSuccess && (
            <div className="border border-moss/40 bg-moss/8 rounded-sm p-4 flex items-start gap-3">
              <Check size={18} className="text-moss mt-0.5" strokeWidth={2} />
              <div className="flex-1">
                <p className="ff-display text-[16px] mb-1">Published.</p>
                <p className="ff-mono text-[10.5px] text-slate leading-relaxed">
                  Wrote to <span className="text-ink">{publish.data?.facility_path.split("/").slice(-3).join("/")}</span>.
                </p>
                {(publish.data?.warnings.length ?? 0) > 0 && (
                  <p className="ff-mono text-[10.5px] text-ochre mt-1">
                    {publish.data?.warnings.join(" · ")}
                  </p>
                )}
              </div>
            </div>
          )}

          {submit.isSuccess && (
            <div className="border border-moss/40 bg-moss/8 rounded-sm p-4 flex items-start gap-3">
              <Check size={18} className="text-moss mt-0.5" strokeWidth={2} />
              <div className="flex-1">
                <p className="ff-display text-[16px] mb-1">Submitted for review.</p>
                <p className="ff-mono text-[10.5px] text-slate leading-relaxed">
                  Admin will see your changes in the Proposals queue. You'll keep your draft until they approve or request changes.
                </p>
              </div>
            </div>
          )}

          {publish.isError && (
            <div className="border border-rust/40 bg-rust/5 rounded-sm p-4">
              <p className="ff-mono text-[10.5px] tracking-wide-2 small-caps text-rust mb-1">Publish failed</p>
              <p className="ff-mono text-[10.5px] text-rust leading-relaxed">{(publish.error as Error).message}</p>
            </div>
          )}
          {submit.isError && (
            <div className="border border-rust/40 bg-rust/5 rounded-sm p-4">
              <p className="ff-mono text-[10.5px] tracking-wide-2 small-caps text-rust mb-1">Submit failed</p>
              <p className="ff-mono text-[10.5px] text-rust leading-relaxed">{(submit.error as Error).message}</p>
            </div>
          )}

          {!succeeded && (
            <>
              <div className="flex items-baseline gap-2 mb-2">
                <span className="ff-mono text-[10px] tracking-wide-3 small-caps text-saffron">01 / Validation</span>
                <span className="flex-1 h-px bg-hairline" />
                {dryRun.isFetching && <Loader2 size={11} className="animate-spin text-saffron" strokeWidth={1.5} />}
              </div>

              {dryRun.isPending ? (
                <p className="ff-mono text-[11px] text-slate-2">Running dry-run…</p>
              ) : ok ? (
                <div className="flex items-start gap-3 p-3 bg-moss/8 border border-moss/30 rounded-sm">
                  <Check size={16} className="text-moss mt-0.5" strokeWidth={2} />
                  <div>
                    <p className="ff-display text-[15px]">Ready to ship.</p>
                    <p className="text-[11.5px] text-slate-2 mt-0.5 ff-display italic">
                      Topology, departments, and edge instructions all check out.
                    </p>
                  </div>
                </div>
              ) : (
                <ul className="space-y-1.5">
                  {issues.map((issue, i) => (
                    <li key={i} className="flex items-start gap-2 px-3 py-2 bg-paper-2 border border-hairline rounded-sm">
                      <AlertTriangle size={13} className="text-ochre mt-0.5 flex-shrink-0" strokeWidth={1.5} />
                      <span className="text-[12px] leading-snug">{issue}</span>
                    </li>
                  ))}
                </ul>
              )}

              {!dryRun.isPending && warnings.length > 0 && (
                <div className="space-y-1.5 pt-1">
                  <p className="ff-mono text-[10px] tracking-wide-3 small-caps text-ochre">
                    Quality warnings · don't block publish
                  </p>
                  {warnings.map((w, i) => (
                    <div key={i} className="flex items-start gap-2 px-3 py-2 bg-ochre/8 border border-ochre/30 rounded-sm">
                      <AlertTriangle size={13} className="text-ochre mt-0.5 flex-shrink-0" strokeWidth={1.5} />
                      <span className="text-[12px] leading-snug text-ink-2">{w}</span>
                    </div>
                  ))}
                </div>
              )}

              {!isAdmin && (
                <div className="pt-2 border-t border-hairline">
                  <label className="block ff-mono text-[10px] tracking-wide-3 small-caps text-saffron mb-1.5">
                    02 / Message for the admin
                  </label>
                  <textarea
                    value={message}
                    onChange={(e) => setMessage(e.target.value)}
                    placeholder="What changed? Mention the building or department so the admin can review faster."
                    rows={3}
                    maxLength={2000}
                    className="w-full bg-paper border border-hairline rounded-sm p-2.5 text-[12px] leading-relaxed resize-none ff-display focus:border-saffron outline-none"
                  />
                </div>
              )}

              {isAdmin && issues.length > 0 && (
                <label className="flex items-start gap-2 text-[11.5px] cursor-pointer pt-2 border-t border-hairline">
                  <input
                    type="checkbox"
                    checked={forceMode}
                    onChange={(e) => setForceMode(e.target.checked)}
                    className="mt-1 accent-rust"
                  />
                  <span className="text-ink-2">
                    <span className="ff-display italic">Publish anyway (force)</span>
                    <span className="block text-slate-2 text-[10.5px] ff-display italic mt-0.5">
                      Use sparingly — for example, when shipping a known-incomplete clinic to a beta channel.
                    </span>
                  </span>
                </label>
              )}
            </>
          )}
        </div>

        <footer className="flex items-center justify-end gap-2 px-6 h-12 border-t border-hairline">
          {!succeeded ? (
            <>
              <button
                onClick={onClose}
                disabled={inFlight}
                className="px-3 h-9 text-[11px] tracking-wide-2 small-caps text-slate hover:text-ink"
              >
                Cancel
              </button>
              {isAdmin ? (
                <button
                  onClick={() => publish.mutate({ slug, force: forceMode })}
                  disabled={!canPublish || inFlight || dryRun.isPending}
                  className={cn(
                    "px-4 h-9 rounded-sm text-[11.5px] tracking-wide-2 small-caps flex items-center gap-2 transition-colors",
                    canPublish && !inFlight && !dryRun.isPending
                      ? "bg-ink text-paper hover:bg-ink-2"
                      : "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed",
                  )}
                >
                  {publish.isPending && <Loader2 size={13} className="animate-spin" strokeWidth={1.5} />}
                  {forceMode ? "Force publish" : "Publish"}
                  <ArrowRight size={13} strokeWidth={1.5} />
                </button>
              ) : (
                <button
                  onClick={() => submit.mutate({ slug, message: message.trim() })}
                  disabled={!canSubmit || inFlight}
                  className={cn(
                    "px-4 h-9 rounded-sm text-[11.5px] tracking-wide-2 small-caps flex items-center gap-2 transition-colors",
                    canSubmit && !inFlight
                      ? "bg-ink text-paper hover:bg-ink-2"
                      : "bg-paper-2 text-slate-2 border border-hairline cursor-not-allowed",
                  )}
                >
                  {submit.isPending && <Loader2 size={13} className="animate-spin" strokeWidth={1.5} />}
                  Submit for review
                  <ArrowRight size={13} strokeWidth={1.5} />
                </button>
              )}
            </>
          ) : (
            <button
              onClick={onClose}
              className="px-4 h-9 bg-ink text-paper rounded-sm text-[11.5px] tracking-wide-2 small-caps"
            >
              Close
            </button>
          )}
        </footer>
      </div>
    </div>
  );
}
