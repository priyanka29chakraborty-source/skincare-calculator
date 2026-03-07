import { useState } from "react";
import { getBarColor } from "../constants";
import { ScoreCircle, TierBadge, BreakdownRow, ProgressBar, ConcernCard, SkinTypeDetails } from "./ScoreComponents";
import AlternativesCard from "./AlternativesCard";
import BestPriceCard from "./BestPriceCard";

export default function ResultCards({ result, concerns, skinType, currency, alternatives, altLoading, bestPrice, bestPriceLoading, fetchInput }) {
  const [showBreakdown, setShowBreakdown] = useState(false);

  return (
    <>
      {/* CARD 1: MAIN WORTH SCORE */}
      <div className="sc-card result-card card-1" data-testid="card-main-worth" style={{ "--anim-delay": "0s" }}>
        <h2 className="card-title"><i className="fa-solid fa-chart-line"></i> Main Worth Score</h2>
        <div className="score-header">
          <ScoreCircle score={result.main_worth_score} />
          <div className="score-meta">
            <TierBadge tier={result.main_worth_tier} score={result.main_worth_score} />
            <p className="score-title-text">{result.score_title}</p>
            {result.worth_multipliers_applied?.length > 0 && (
              <p className="multipliers">Bonus: {result.worth_multipliers_applied.join(", ")}</p>
            )}
          </div>
        </div>

        <div className="price-grid-sep" data-testid="price-grid">
          <div className="pg-box"><div className="pg-val">{result.price_analysis?.price_per_ml}</div><div className="pg-lbl">per ml</div></div>
          <div className="pg-box"><div className="pg-val">{result.price_analysis?.category_avg}</div><div className="pg-lbl">category avg</div></div>
          <div className="pg-box"><div className="pg-val" style={{ color: "#267C36" }}>{result.price_analysis?.vs_average}</div><div className="pg-lbl">vs average</div></div>
          <div className="pg-box pg-bot"><div className="pg-val">{result.price_analysis?.price_per_active}</div><div className="pg-lbl">per active</div></div>
          <div className="pg-box pg-bot"><div className="pg-val">{result.price_analysis?.active_count}</div><div className="pg-lbl">actives found</div></div>
          <div className="pg-box pg-bot"><div className="pg-val">{result.price_analysis?.active_ratio}</div><div className="pg-lbl">active ratio <i className="fa-solid fa-circle-info" title="% of total ingredients that are true therapeutic actives" style={{ fontSize: "0.65rem", color: "var(--text-sub)", cursor: "help" }}></i></div></div>
        </div>
        {result.price_analysis?.price_note && <div className="price-note" data-testid="price-note"><i className="fa-solid fa-info-circle"></i> {result.price_analysis.price_note}</div>}
        {result.price_analysis?.global_markup_detected && <div className="markup-alert" data-testid="markup-alert"><i className="fa-solid fa-exclamation-triangle"></i> Global Markup Detected</div>}

        <button className="breakdown-toggle" data-testid="breakdown-toggle" onClick={() => setShowBreakdown(!showBreakdown)} aria-expanded={showBreakdown}>
          {showBreakdown ? "Hide" : "Show"} Detailed Breakdown {showBreakdown ? <i className="fa-solid fa-chevron-up"></i> : <i className="fa-solid fa-chevron-down"></i>}
        </button>
        {showBreakdown && (
          <div className="breakdown" data-testid="breakdown-details">
            <BreakdownRow icon="fa-solid fa-chart-bar" label="Active Ingredient Value" score={result.component_scores?.A} max={45} details={result.component_details?.A} />
            <BreakdownRow icon="fa-solid fa-flask" label="Functional Formula Quality" score={result.component_scores?.B} max={20} details={result.component_details?.B} />
            <BreakdownRow icon="fa-solid fa-check-circle" label="Claim-Reality Accuracy" score={result.component_scores?.C} max={15} details={result.component_details?.C} />
            <BreakdownRow icon="fa-solid fa-shield-halved" label="Safety & Suitability" score={result.component_scores?.D} max={10} details={result.component_details?.D} />
            <BreakdownRow icon="fa-solid fa-coins" label="Price Rationality" score={result.component_scores?.E} max={10} details={result.component_details?.E} />
          </div>
        )}

        {result.red_flags?.length > 0 && (
          <div className="red-flags-section" data-testid="red-flags-section">
            <h4 className="red-flags-title"><i className="fa-solid fa-triangle-exclamation"></i> Worth Red Flags</h4>
            <ul className="red-flags-list">
              {result.red_flags.map((rf, i) => <li key={i} data-testid={`red-flag-${i}`}>{rf}</li>)}
            </ul>
          </div>
        )}
      </div>

      {/* CARD 2: CONCERN FIT */}
      {Object.keys(result.skin_concern_fit || {}).length > 0 && (
        <div className="sc-card result-card card-2" data-testid="card-concern-fit" style={{ "--anim-delay": "0.15s" }}>
          <h2 className="card-title"><i className="fa-solid fa-bullseye"></i> Skin Concern Fit</h2>
          <p className="ampm-label" data-testid="ampm-label"><i className="fa-regular fa-clock"></i> {result.am_pm_recommendation}</p>
          {Object.entries(result.skin_concern_fit).map(([concern, data]) => (
            <ConcernCard key={concern} concern={concern} data={data} />
          ))}
        </div>
      )}

      {/* CARD 3: SKIN TYPE COMPAT */}
      <div className="sc-card result-card card-3" data-testid="card-skin-type" style={{ "--anim-delay": "0.3s" }}>
        <h2 className="card-title"><i className="fa-solid fa-user-check"></i> {skinType} Skin Compatibility</h2>
        <div className="compat-score-row">
          <span className="compat-pct" style={{ color: getBarColor(result.skin_type_compatibility) }}>{result.skin_type_compatibility}%</span>
          <ProgressBar pct={result.skin_type_compatibility} label="compat" />
        </div>
        <SkinTypeDetails details={result.skin_type_details} score={result.skin_type_compatibility} betterSuited={result.better_suited} formNotes={result.skin_type_details?.formulation_notes} />
      </div>

      {/* CARD 4A: ALTERNATIVES */}
      <AlternativesCard result={result} concerns={concerns} alternatives={alternatives} altLoading={altLoading} currency={currency} />

      {/* CARD 4B: BEST PRICE */}
      <BestPriceCard bestPrice={bestPrice} bestPriceLoading={bestPriceLoading} currency={currency} fetchInput={fetchInput} />

      <div className="disclaimer" data-testid="disclaimer">
        Product formulations may change. Always verify ingredients before purchasing. Educational information only, not medical advice. Consult a dermatologist for personalized recommendations.
      </div>
    </>
  );
}
