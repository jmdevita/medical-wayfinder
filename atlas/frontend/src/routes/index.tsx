import { createFileRoute } from "@tanstack/react-router";
import { FacilitiesView } from "@/views/FacilitiesView";

export const Route = createFileRoute("/")({
  component: FacilitiesView,
});
