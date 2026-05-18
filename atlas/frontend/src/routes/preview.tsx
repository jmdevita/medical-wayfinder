import { createFileRoute } from "@tanstack/react-router";
import { PreviewView } from "@/views/PreviewView";

interface PreviewSearch {
  slug?: string;
}

export const Route = createFileRoute("/preview")({
  validateSearch: (search: Record<string, unknown>): PreviewSearch => ({
    slug: typeof search.slug === "string" ? search.slug : undefined,
  }),
  component: PreviewView,
});
