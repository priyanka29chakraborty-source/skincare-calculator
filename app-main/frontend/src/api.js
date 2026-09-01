import axios from "axios";

import { API } from "./constants";

/**
 * Shared axios client.
 *
 * Two problems this solves:
 *
 * 1. No timeout was configured anywhere, so a backend that never responds left
 *    the "Analysing..." spinner running forever with no way out. On a free-tier
 *    host the first request after idle can take 30-60s to wake the service,
 *    which looks identical to a hang.
 *
 * 2. Every failure produced the same "Analysis failed" message, so a user could
 *    not tell a rate limit from an outage from their own bad input - and
 *    neither could we, from a support message.
 */

// Generous, because a cold start is a real and recoverable case. Long enough to
// let the backend wake, short enough that a genuine outage does not hang.
const DEFAULT_TIMEOUT_MS = 75000;

export const api = axios.create({ timeout: DEFAULT_TIMEOUT_MS });

/** Turn any axios failure into something a person can act on. */
export function describeError(e) {
  // The server said something specific - prefer it.
  const serverMessage = e?.response?.data?.error;
  if (serverMessage) return serverMessage;

  if (e?.code === "ECONNABORTED" || /timeout/i.test(e?.message || "")) {
    return (
      "This is taking longer than expected. The server may be waking up after " +
      "a period of inactivity - please try again in a moment."
    );
  }

  const status = e?.response?.status;
  if (status === 429) {
    return "You have made a lot of requests in a short time. Please wait a minute and try again.";
  }
  if (status === 413) {
    return "That ingredient list is too long. Please shorten it and try again.";
  }
  if (status >= 500) {
    return "Something went wrong on our side. Please try again - if it keeps happening, the issue is not with your input.";
  }
  if (status === 400 || status === 422) {
    return "Some of the details entered could not be read. Please check the price, size and ingredient list.";
  }

  // No response at all: the request never reached the server. Offline, DNS,
  // CORS, or the backend is down. Distinguishing these from the browser is not
  // possible, so say what is actionable.
  if (!e?.response) {
    return (
      "Could not reach the server. Check your internet connection and try " +
      "again - if you are connected, the service may be temporarily down."
    );
  }
  return "Something went wrong. Please try again.";
}

export { API };
