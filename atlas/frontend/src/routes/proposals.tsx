import { createFileRoute } from "@tanstack/react-router";
import { ProposalsView } from "@/views/ProposalsView";

export const Route = createFileRoute("/proposals")({
  component: ProposalsView,
});
