import { createFileRoute } from "@tanstack/react-router";
import { EditorView } from "@/views/EditorView";

interface EditorSearch {
  slug?: string;
  /** Deep-link a specific topology node to be selected on load. */
  node?: string;
}

export const Route = createFileRoute("/editor")({
  validateSearch: (search: Record<string, unknown>): EditorSearch => ({
    slug: typeof search.slug === "string" ? search.slug : undefined,
    node: typeof search.node === "string" ? search.node : undefined,
  }),
  component: EditorView,
});
