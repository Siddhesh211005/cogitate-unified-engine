import type { WarmState } from "@/types/rater";

export function getWarmStateLabel(state: WarmState | null): string | null {
  switch (state) {
    case "warming":
      return "Preparing workbook...";
    case "ready":
      return "Workbook ready for Test Calculate";
    case "failed":
      return "Warm start failed (cold fallback mode)";
    case "fallback-cold":
      return "Cold fallback mode";
    case "disabled":
      return "Warm start disabled";
    case "expired":
      return "Warm session expired";
    default:
      return state ? `Warm state: ${state}` : null;
  }
}

export function getWarmToneClass(state: WarmState | null): string {
  if (state === "ready") {
    return "border-green-200 bg-green-50 text-green-900";
  }
  if (state === "failed" || state === "unknown") {
    return "border-red-200 bg-red-50 text-red-900";
  }
  return "border-blue-200 bg-blue-50 text-blue-900";
}
