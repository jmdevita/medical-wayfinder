import type { FacilityStatus, NodeType } from "./types";

export const TYPE_COLOR: Record<NodeType, string> = {
  parking:  "#1E3A5F",
  entrance: "#B8530A",
  landmark: "#A98024",
  junction: "#6B6862",
  transit:  "#5B3A4E",
  floor:    "#928D82",
};

export const TYPE_LABEL: Record<NodeType, string> = {
  parking:  "Parking",
  entrance: "Entrance",
  landmark: "Landmark",
  junction: "Junction",
  transit:  "Transit",
  floor:    "Floor",
};

export interface StatusMeta {
  label: string;
  dot: string;
  text: string;
  bg: string;
}

export const STATUS_META: Record<FacilityStatus, StatusMeta> = {
  published: { label: "Published", dot: "#516B53", text: "text-moss",    bg: "bg-moss/8" },
  review:    { label: "In review", dot: "#A98024", text: "text-ochre",   bg: "bg-ochre/10" },
  draft:     { label: "Draft",     dot: "#B8530A", text: "text-saffron", bg: "bg-saffron/10" },
  bootstrap: { label: "Located",   dot: "#928D82", text: "text-slate",   bg: "bg-slate-2/15" },
};
