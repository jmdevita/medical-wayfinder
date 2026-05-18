/**
 * SSE-backed hook for tailing a job's progress.
 *
 * Backend job lifecycle: pending → running (many `progress` events) → complete | failed.
 * The stream replays buffered events when a consumer connects, then tails live
 * ones, so opening this slightly after the POST is safe.
 */

import { useEffect, useState } from "react";

export type JobStatus = "pending" | "running" | "complete" | "failed";

export interface JobSnapshot {
  id: string;
  kind: string;
  status: JobStatus;
  stage: string;
  pct: number;
  msg: string;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: number;
  finished_at: number | null;
}

export interface JobState {
  status: JobStatus;
  stage: string;
  pct: number;
  msg: string;
  result: Record<string, unknown> | null;
  error: string | null;
}

const INITIAL: JobState = {
  status: "pending",
  stage: "",
  pct: 0,
  msg: "",
  result: null,
  error: null,
};

export function useJobStream(jobId: string | null): JobState {
  const [state, setState] = useState<JobState>(INITIAL);

  useEffect(() => {
    if (!jobId) {
      setState(INITIAL);
      return;
    }
    setState(INITIAL);

    const es = new EventSource(`/api/jobs/${jobId}/stream`);

    es.addEventListener("snapshot", (e) => {
      const snap = JSON.parse((e as MessageEvent).data) as JobSnapshot;
      setState({
        status: snap.status,
        stage: snap.stage,
        pct: snap.pct,
        msg: snap.msg,
        result: snap.result,
        error: snap.error,
      });
    });

    es.addEventListener("progress", (e) => {
      const data = JSON.parse((e as MessageEvent).data) as {
        stage: string; pct: number; msg: string;
      };
      setState((prev) => ({ ...prev, status: "running", ...data }));
    });

    es.addEventListener("complete", (e) => {
      const data = JSON.parse((e as MessageEvent).data) as {
        result: Record<string, unknown>;
      };
      setState((prev) => ({ ...prev, status: "complete", pct: 1, result: data.result }));
      es.close();
    });

    es.addEventListener("failed", (e) => {
      const data = JSON.parse((e as MessageEvent).data) as { error: string };
      setState((prev) => ({ ...prev, status: "failed", error: data.error }));
      es.close();
    });

    es.onerror = () => {
      // EventSource auto-retries; only report a hard failure once we know the
      // backend isn't reachable. For now, leave state as-is and let the user
      // open jobs list to debug.
    };

    return () => es.close();
  }, [jobId]);

  return state;
}
