import { useEffect, useMemo, useRef, useState } from "react";
import { useSaveDepartments, type Department } from "@/lib/api";

/**
 * Owns the editable departments draft state for a slug.
 *
 * Lifted out of DepartmentsPanel so that other parts of the editor (e.g. an
 * inline picker on the node inspector) can dispatch into the same draft
 * without prop-drilling through three layers or remounting the panel.
 *
 * Dirty preservation: only resets to a new server state when the current
 * draft equals the *previous* server state (i.e. the user has no unsaved
 * changes). Slug changes should remount whatever consumes this hook.
 */
export function useDepartmentEditor(
  slug: string,
  initial: Department[],
) {
  const [drafts, setDrafts] = useState<Department[]>(initial);
  const lastInitialRef = useRef(initial);

  useEffect(() => {
    const wasClean = JSON.stringify(drafts) === JSON.stringify(lastInitialRef.current);
    lastInitialRef.current = initial;
    if (wasClean) setDrafts(initial);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initial]);

  const save = useSaveDepartments();
  const dirty = useMemo(
    () => JSON.stringify(drafts) !== JSON.stringify(initial),
    [drafts, initial],
  );

  const duplicateNames = useMemo(() => {
    const seen = new Map<string, number>();
    drafts.forEach((d) => seen.set(d.name, (seen.get(d.name) ?? 0) + 1));
    return new Set(
      [...seen.entries()].filter(([, n]) => n > 1).map(([name]) => name),
    );
  }, [drafts]);

  /** Compute a new drafts array with the requested mapping applied without
   * mutating local state. Used internally by mapDeptNamesToNode and by the
   * autosave variant.
   */
  const _withMapping = (
    arr: Department[], names: string[], nodeId: string | undefined,
  ): Department[] => {
    const remaining = new Set(names);
    return arr.map((d) => {
      if (!remaining.has(d.name)) return d;
      remaining.delete(d.name);
      return { ...d, topology_node_id: nodeId };
    });
  };

  const _hasDuplicateNames = (arr: Department[]): boolean => {
    const seen = new Set<string>();
    for (const d of arr) {
      if (seen.has(d.name)) return true;
      seen.add(d.name);
    }
    return false;
  };

  /**
   * Map a set of departments (by name) onto a single topology node AND
   * immediately persist. Used for explicit commit-intent gestures (picker
   * submit, map-click after Assign). If multiple departments share a name,
   * only the FIRST one matches per incoming name — duplicates remain
   * unassigned and surface as duplicate warnings until the editor renames
   * them. Skips the save when the resulting array still has duplicate names
   * — those would 422 from the backend anyway, so we leave the dirty state
   * for the editor to resolve in the dept tab.
   *
   * Computes the new array directly (rather than relying on setState +
   * a follow-up save) so we don't race React's state batching.
   */
  const mapAndSave = (names: string[], nodeId: string) => {
    if (names.length === 0) return;
    const next = _withMapping(drafts, names, nodeId);
    setDrafts(next);
    if (_hasDuplicateNames(next)) return;
    save.mutate({ slug, departments: next });
  };

  /** Unmap a single department by name AND immediately persist. */
  const unmapAndSave = (name: string) => {
    const next = _withMapping(drafts, [name], undefined);
    setDrafts(next);
    if (_hasDuplicateNames(next)) return;
    save.mutate({ slug, departments: next });
  };

  return {
    drafts, setDrafts,
    save, dirty, duplicateNames,
    mapAndSave, unmapAndSave,
  };
}
