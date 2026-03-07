import { useState } from "react";
import { getScoreColor, getBarColor, CONCERNS_LIST } from "../constants";

export function ScoreCircle({ score }) {
  const r = 54, c = 2 * Math.PI * r;
  const off = c - (score / 100) * c;
  const col = getScoreColor(score);
  return (
    <div className="score-circle-wrap" data-testid="score-circle">
      <svg width="140" height="140" viewBox="0 0 140 140">
        <circle cx="70" cy="70" r={r} fill="none" stroke="var(--border)" strokeWidth="10" />
        <circle cx="70" cy="70" r={r} fill="none" stroke={col} strokeWidth="10"
          strokeDasharray={c} strokeDashoffset={off} strokeLinecap="round"
          transform="rotate(-90 70 70)" style={{ transition: "stroke-dashoffset 1.2s ease" }} />
      </svg>
      <div className="score-number" style={{ color: col }}>{score}<span className="score-total">/100</span></div>
    </div>
  );
}

export function ProgressBar({ pct, label }) {
  return (
    <div className="progress-bar-wrap" data-testid={`progress-${label}`}>
      <div className="progress-bar-bg">
        <div className="progress-bar-fill" style={{ width: `${Math.min(100, pct)}%`, background: getBarColor(pct), transition: "width 0.8s ease" }} />
      </div>
    </div>
  );
}

export function TierBadge({ tier, score }) {
  const c = getScoreColor(score);
  return <span className="tier-badge" style={{ background: c + "22", color: c, borderColor: c }} data-testid="tier-badge">{tier}</span>;
}

export function BreakdownRow({ icon, label, score, max, details }) {
  const pct = (score / max) * 100;
  return (
    <div className="bd-row" data-testid={`breakdown-${label.replace(/\s+/g, "-").toLowerCase()}`}>
      <div className="bd-header">
        <i className={icon}></i>
        <span className="bd-label">{label}</span>
        <span className="bd-score">{score} / {max}</span>
      </div>
      <ProgressBar pct={pct} label={label} />
      {details?.length > 0 && (
        <ul className="bd-details">
          {details.map((d, i) => <li key={i}>{d}</li>)}
        </ul>
      )}
    </div>
  );
}

export function ConcernCard({ concern, data, rank }) {
  const [open, setOpen] = useState(false);
  const ic = CONCERNS_LIST.find(c => c.key === concern)?.icon || "fa-solid fa-circle";
  const rankLabels = ["Best Match", "2nd Match", "3rd Match"];
  const rankColors = ["#22c55e", "#eab308", "#f97316"];
  return (
    <div className={`concern-result ${rank === 0 ? "concern-best" : ""}`} data-testid={`concern-result-${concern.replace(/\s+/g, "-").toLowerCase()}`}>
      <div className="concern-header" onClick={() => setOpen(!open)}>
        <div className="concern-left">
          <i className={ic}></i>
          <span className="concern-cname">{concern}</span>
          {rank != null && (
            <span className="concern-rank-badge" style={{ background: rankColors[rank] + "22", color: rankColors[rank], borderColor: rankColors[rank] }}>
              {rankLabels[rank]}
            </span>
          )}
          <span className="concern-pct" style={{ color: getBarColor(data.score) }}>{data.score}%</span>
        </div>
        <i className={`fa-solid fa-circle-info info-toggle ${open ? "open" : ""}`}></i>
      </div>
      <ProgressBar pct={data.score} label={concern} />
      {open && (
        <div className="concern-detail">
          <ul className="concern-explain">
            {data.explanation?.map((e, i) => <li key={i}>{e}</li>)}
          </ul>
          {data.supporting_ingredients?.length > 0 && (
            <p className="concern-support"><strong>Supporting:</strong> {data.supporting_ingredients.join(", ")}</p>
          )}
          <p className="concern-advisory"><strong>Advisory:</strong> {data.advisory}</p>
        </div>
      )}
    </div>
  );
}

export function SkinTypeDetails({ details, score, betterSuited, formNotes }) {
  return (
    <div className="skin-type-details" data-testid="skin-type-details">
      {details?.why_bullets?.length > 0 && (
        <div className="st-section">
          <h4><i className="fa-solid fa-circle-info"></i> Why this score?</h4>
          <ul>{details.why_bullets.map((b, i) => <li key={i} className={b.startsWith("Warning") ? "warning" : "good"}>{b}</li>)}</ul>
        </div>
      )}
      {details?.helpful_ingredients?.length > 0 && (
        <div className="st-section">
          <h4><i className="fa-solid fa-thumbs-up"></i> Helpful Ingredients</h4>
          <ul>{details.helpful_ingredients.map((h, i) => <li key={i}>{h}</li>)}</ul>
        </div>
      )}
      {details?.look_for?.length > 0 && (
        <div className="st-section">
          <h4><i className="fa-solid fa-lightbulb"></i> Look For</h4>
          <p>{details.look_for[0]}</p>
        </div>
      )}
      {formNotes?.length > 0 ? (
        <div className="st-section form-notes" data-testid="formulation-notes">
          <h4><i className="fa-solid fa-triangle-exclamation"></i> Formulation Notes (Red Flags)</h4>
          <ul>{formNotes.map((n, i) => <li key={i}>{n}</li>)}</ul>
        </div>
      ) : (
        <div className="st-section form-notes-clean" data-testid="formulation-notes-clean">
          <h4><i className="fa-solid fa-circle-check"></i> Formulation Notes</h4>
          <p>No red flags detected. No comedogenic, irritant, or harmful ingredients found.</p>
        </div>
      )}
      {score < 50 && betterSuited?.length > 0 && (
        <p className="better-suited"><i className="fa-solid fa-arrow-right"></i> Better suited for: {betterSuited.join(", ")} skin</p>
      )}
    </div>
  );
}
