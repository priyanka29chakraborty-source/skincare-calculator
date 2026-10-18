import React from "react";
import { CircleCheck, Lock, ShieldCheck } from "lucide-react";

import { Badge, Button, Card, Meter } from "./ds";

/**
 * A paid section before it is unlocked.
 *
 * Paid fields are stripped server-side, so this must be an explicit state.
 * A locked value is UNKNOWN, not bad: the bars are neutral stripes, never red,
 * and nothing here implies a poor result to create urgency.
 */
export default function LockedCard({
  title, access, lines, onUnlock, ctaLabel = "Unlock with 1 credit", message,
  note = "Locked means unknown — not bad. One credit covers this product for good.",
}) {
  const preview = access?.preview || {};
  return (
    <Card eyebrow="Personal fit" title={title}
          aside={<Badge><Lock aria-hidden="true" style={{ width: 12, height: 12 }} />Locked</Badge>}
          data-testid="locked-card">
      <div className="stack" style={{ "--stack-gap": "16px" }}>
        {(lines || []).map((line) => <Meter key={line} label={line} unknown />)}
      </div>
      {preview.concerns_assessed > 0 && (
        <p className="locked-found">
          <CircleCheck aria-hidden="true" />
          <span>
            Already assessed for <strong>{(preview.concern_names || []).join(", ")}</strong>
            {preview.routine_issues_found > 0 && <> — and found <strong>{preview.routine_issues_found} routine {preview.routine_issues_found === 1 ? "issue" : "issues"}</strong></>}.
          </span>
        </p>
      )}
      {(message || access?.message) && <p className="t-body-m c-secondary" style={{ marginTop: 16 }}>{message || access.message}</p>}
      <Button variant="accent" size="lg" block icon={<Lock />} onClick={onUnlock} data-testid="unlock-cta" style={{ marginTop: 20 }}>
        {ctaLabel}
      </Button>
      <p className="t-caption c-tertiary" style={{ textAlign: "center", marginTop: 10 }}>
        {note}
      </p>
      {access?.safety_note && (
        <p className="locked-safety"><ShieldCheck aria-hidden="true" />{access.safety_note}</p>
      )}
    </Card>
  );
}
