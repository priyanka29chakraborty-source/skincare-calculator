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

function getFitLevel(score) {
  if (score >= 80) return { label: 'Strong fit', bars: 5 };
  if (score >= 60) return { label: 'Good fit',   bars: 4 };
  if (score >= 40) return { label: 'Moderate fit', bars: 3 };
  if (score >= 20) return { label: 'Low fit',    bars: 2 };
  return              { label: 'Very Low fit', bars: 1 };
}

function FitBars({ bars, color }) {
  return (
    <span style={{ letterSpacing: '2px', fontSize: '13px' }}>
      {[1,2,3,4,5].map(i => (
        <span key={i} style={{ color: i <= bars ? color : 'var(--border)', fontWeight: 700 }}>▮</span>
      ))}
    </span>
  );
}

export function ConcernCard({ concern, data }) {
  const [open, setOpen] = useState(false);
  const ic = CONCERNS_LIST.find(c => c.key === concern)?.icon || "fa-solid fa-circle";
  const fit = getFitLevel(data.score);
  const barColor = getBarColor(data.score);
  return (
    <div className="concern-result" data-testid={`concern-result-${concern.replace(/\s+/g, "-").toLowerCase()}`}>
      <div className="concern-header" onClick={() => setOpen(!open)}>
        <div className="concern-left">
          <i className={ic}></i>
          <span className="concern-cname">{concern}</span>
          <FitBars bars={fit.bars} color={barColor} />
          <span style={{ fontSize: '0.75rem', color: barColor, fontWeight: 600, marginLeft: '4px' }}>{fit.label}</span>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
          <span title={`${data.score}/100 — most products fall between 20–60`} style={{ fontSize: '0.75rem', color: 'var(--text-sub)', cursor: 'help' }}>{data.score}/100</span>
          <i className={`fa-solid fa-circle-info info-toggle ${open ? "open" : ""}`}></i>
        </div>
      </div>
      <ProgressBar pct={data.score} label={concern} />
      <div className={"concern-detail" + (open ? " open" : "")}>
        <p style={{ fontSize: '0.75rem', color: 'var(--text-sub)', fontStyle: 'italic', marginBottom: '6px' }}>
          {data.score}/100 = {fit.label.toLowerCase()} vs an ideal formula for this concern. Most products fall between 20–60.
        </p>
        <ul className="concern-explain">
          {data.explanation?.map((e, i) => <li key={i}>{e}</li>)}
        </ul>
        {data.supporting_ingredients?.length > 0 && (
          <p className="concern-support"><strong>Supporting:</strong> {data.supporting_ingredients.join(", ")}</p>
        )}
        <p className="concern-advisory"><strong>Advisory:</strong> {data.advisory}</p>
      </div>
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
          <h4><i className="fa-solid fa-triangle-exclamation"></i> Potential Sensitivity Risks</h4>
          <p style={{ fontSize: "0.78rem", color: "var(--text-sub)", marginBottom: "8px", lineHeight: 1.5 }}>
            These ingredients are safe for many people but can cause issues for acne-prone or sensitive skin. Review based on your own history.
          </p>
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
