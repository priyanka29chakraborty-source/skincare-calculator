import { API, api } from "./api";

const ALLOWED = new Set([
  "analysis_completed",
  "personal_opened",
  "checkout_started",
  "checkout_completed",
  "routine_saved",
  "comparison_completed",
  "result_reopened",
  "refund_requested",
  "pdf_saved",
]);

export function track(name) {
  if (!ALLOWED.has(name)) return;
  api.post(`${API}/events`, { name }).catch(() => {});
}
