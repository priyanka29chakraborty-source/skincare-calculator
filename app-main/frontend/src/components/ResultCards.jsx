import { useState } from "react";
import { getBarColor } from "../constants";
import { ScoreCircle, TierBadge, BreakdownRow, ProgressBar, ConcernCard, SkinTypeDetails } from "./ScoreComponents";
import AlternativesCard from "./AlternativesCard";
import BestPriceCard from "./BestPriceCard";

// Score chip label — uses value_tier from backend to avoid logical contradictions
function getValueChip(valueTier, ratio) {
  switch (valueTier) {
    case 'underpriced':
      return { label: 'Excellent Value', subtitle: 'Good formula, priced below category average.', color: '#267C36' };
    case 'fair':
      return { label: 'Acceptable & Fairly Priced', subtitle: `Good formula, ~${(ratio || 1).toFixed(1)}× category price.`, color: '#2D7FD3' };
    case 'slightly_overpriced':
      return { label: 'Acceptable but Slightly Overpriced', subtitle: 'Formula is decent but priced above category average.', color: '#E6A817' };
    case 'overpriced':
      return { label: 'Overpriced for Actives Inside', subtitle: 'Active ingredient value does not justify the price point.', color: '#D06030' };
    default:
      return { label: 'Analysed', subtitle: '', color: '#7A7168' };
  }
}

// Ingredient breakdown table
function IngredientBreakdownTable({ actives }) {
  if (!actives || actives.length === 0) return null;
  return (
    <div className="ingredient-breakdown-table" style={{ marginTop: "1rem", overflowX: "auto" }}>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: "0.82rem" }}>
        <thead>
          <tr style={{ background: "var(--bg-deep)", borderBottom: "2px solid var(--border)" }}>
            <th style={{ padding: "6px 10px", textAlign: "left" }}>#</th>
            <th style={{ padding: "6px 10px", textAlign: "left" }}>Active Ingredient</th>
            <th style={{ padding: "6px 10px", textAlign: "center" }}>Evidence</th>
            <th style={{ padding: "6px 10px", textAlign: "left" }}>What It Does</th>
            <th style={{ padding: "6px 10px", textAlign: "center" }}>Concentration Est.</th>

          </tr>
        </thead>
        <tbody>
          {actives.map((a, i) => (
            <tr key={i} style={{ borderBottom: "1px solid var(--border)", background: i % 2 === 0 ? "transparent" : "var(--bg-deep)" }}>
              <td style={{ padding: "5px 10px", color: "var(--text-sub)" }} title="Position in ingredient list">#{a.position}</td>
              <td style={{ padding: "5px 10px", fontWeight: 500 }}>
                {a.name}
                {a.targets?.length > 0 && (
                  <div style={{ marginTop: "2px", display: "flex", flexWrap: "wrap", gap: "3px" }}>
                    {a.targets.filter(t => t && t.trim()).map((t, ti) => (
                      <span key={ti} style={{ fontSize: "10px", background: "var(--rose)", border: "1px solid var(--dusty-rose-light)", padding: "2px 6px", borderRadius: "4px", color: "var(--dusty-rose-dark)", fontWeight: 500 }}>{t}</span>
                    ))}
                  </div>
                )}
              </td>
              <td style={{ padding: "5px 10px", textAlign: "center" }}>
                <span style={{
                  fontSize: "0.75rem", fontWeight: 600,
                  color: a.evidence?.toLowerCase().startsWith("strong") ? "#267C36" : a.evidence?.toLowerCase().startsWith("moderate") ? "#C9A96E" : "#BF8888"
                }} title={a.evidence}>{
                  a.evidence?.toLowerCase().startsWith("strong") ? "Strong" :
                  a.evidence?.toLowerCase().startsWith("moderate") ? "Moderate" :
                  a.evidence?.toLowerCase().startsWith("limited") ? "Limited" :
                  a.evidence?.toLowerCase().startsWith("early") ? "Emerging" : "Minimal"
                }</span>
              </td>
              <td style={{ padding: "5px 10px", color: "var(--text-sub)", fontSize: "0.78rem", maxWidth: "200px" }}>
                {a.primary_benefits || a.functional_category || "—"}
              </td>
              <td style={{ padding: "5px 10px", textAlign: "center", color: "var(--text-sub)", fontSize: "0.78rem" }}>{a.concentration}</td>

            </tr>
          ))}
        </tbody>
      </table>
      <p style={{ fontSize: "0.72rem", color: "var(--text-sub)", marginTop: "8px", fontStyle: "italic" }}>
        ℹ️ Concentration estimates are based on INCI position and may not reflect actual formulation.
      </p>
    </div>
  );
}


// ── Sunscreen Analysis Card ──────────────────────────────────────────────────
function SunscreenAnalysisCard({ data }) {
  const [open, setOpen] = useState(false);
  if (!data) return null;

  const sa = data.sunscreen_analysis;
  if (!sa) return null;

  const overallScore = sa.overall_score ?? 0;
  const sunburnScore = sa.sunburn_score ?? 0;
  const spf = sa.spf_estimate || '—';
  const pa  = sa.pa_estimate  || '—';
  const broad = sa.broad_spectrum;
  const uvb = sa.uvb_covered;
  const uva1 = sa.uva1_covered;
  const uva2 = sa.uva2_covered;
  const reefSafe = sa.reef_safe !== false;
  const filters = sa.filters_detected || [];
  const warnings = sa.warnings || [];
  const flags = sa.flags || [];
  const breakdown = sa.score_breakdown || {};

  const pillStyle = (active, color) => ({
    display: 'inline-flex', alignItems: 'center', gap: '4px',
    padding: '3px 10px', borderRadius: '20px', fontSize: '11px', fontWeight: 600,
    background: active ? color + '22' : '#f0e8df',
    color: active ? color : 'var(--text-sub)',
    border: `1px solid ${active ? color + '55' : 'var(--border)'}`,
  });

  const overallColor = overallScore >= 85 ? 'var(--sage)' :
                       overallScore >= 70 ? '#2D7FD3' :
                       overallScore >= 55 ? 'var(--gold)' :
                       overallScore >= 40 ? 'var(--orange)' : 'var(--red)';

  const overallLabel = overallScore >= 85 ? 'Excellent' :
                       overallScore >= 70 ? 'Good' :
                       overallScore >= 55 ? 'Average' :
                       overallScore >= 40 ? 'Weak' : 'Poor';

  return (
    <div className="sc-card result-card" data-testid="card-sunscreen-analysis"
         style={{ "--anim-delay": "0.2s", borderTop: "3px solid var(--dusty-rose)" }}>
      <h2 className="card-title">
        <i className="fa-solid fa-sun"></i> Sunscreen Analysis
      </h2>

      {/* Top row: overall + SPF estimate + PA estimate */}
      <div style={{ display: 'flex', gap: '12px', marginBottom: '16px', flexWrap: 'wrap' }}>
        {/* Overall sunscreen quality */}
        <div style={{
          flex: '1 1 120px', background: overallColor + '11', border: `1.5px solid ${overallColor}33`,
          borderRadius: '12px', padding: '12px 14px', textAlign: 'center'
        }}>
          <div style={{ fontSize: '28px', fontWeight: 700, color: overallColor, lineHeight: 1 }}>
            {overallScore}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-sub)', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Overall Quality
          </div>
          <div style={{ fontSize: '11px', fontWeight: 600, color: overallColor, marginTop: '4px' }}>
            {overallLabel}
          </div>
        </div>

        {/* SPF Estimate */}
        <div style={{
          flex: '1 1 100px', background: '#fff8f0', border: '1.5px solid var(--gold)',
          borderRadius: '12px', padding: '12px 14px', textAlign: 'center'
        }}>
          <div style={{ fontSize: '15px', fontWeight: 700, color: 'var(--gold)', lineHeight: 1.2 }}>
            {spf}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-sub)', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            SPF Estimate*
          </div>
        </div>

        {/* PA Estimate */}
        <div style={{
          flex: '1 1 100px', background: '#f0f8ff', border: '1.5px solid #5BA4CF',
          borderRadius: '12px', padding: '12px 14px', textAlign: 'center'
        }}>
          <div style={{ fontSize: '15px', fontWeight: 700, color: '#2D7FD3', lineHeight: 1.2 }}>
            {pa}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-sub)', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            PA Estimate*
          </div>
        </div>

        {/* Sunburn (UVB) sub-score */}
        <div style={{
          flex: '1 1 100px', background: '#fff5f5', border: '1.5px solid #e07070',
          borderRadius: '12px', padding: '12px 14px', textAlign: 'center'
        }}>
          <div style={{ fontSize: '22px', fontWeight: 700, color: '#C0392B', lineHeight: 1 }}>
            {sunburnScore}
          </div>
          <div style={{ fontSize: '10px', color: 'var(--text-sub)', marginTop: '2px', textTransform: 'uppercase', letterSpacing: '0.5px' }}>
            Sunburn (UVB)
          </div>
        </div>
      </div>

      {/* UV coverage pills */}
      <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginBottom: '12px' }}>
        <span style={pillStyle(uvb,  '#2D7FD3')}><i className={`fa-solid fa-circle fa-xs`}></i> UVB</span>
        <span style={pillStyle(uva1, '#267C36')}><i className="fa-solid fa-circle fa-xs"></i> UVA1</span>
        <span style={pillStyle(uva2, '#A87373')}><i className="fa-solid fa-circle fa-xs"></i> UVA2</span>
        <span style={pillStyle(broad, '#5B4FBE')}>
          <i className={`fa-solid ${broad ? 'fa-check' : 'fa-xmark'}`}></i> {broad ? 'Broad Spectrum' : 'Not Broad Spectrum'}
        </span>
        <span style={pillStyle(reefSafe, '#267C36')}>
          <i className="fa-solid fa-fish"></i> {reefSafe ? 'Reef Safe' : 'Not Reef Safe'}
        </span>
      </div>

      {/* Score breakdown bar */}
      <div style={{ marginBottom: '14px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: 'var(--text-sub)', marginBottom: '4px' }}>
          <span>Score Breakdown</span>
          <span style={{ fontSize: '10px' }}>max 100</span>
        </div>
        <div style={{ display: 'flex', gap: '3px', height: '8px', borderRadius: '6px', overflow: 'hidden', background: 'var(--border)' }}>
          {[
            { label: 'UV Coverage', val: breakdown.uv_coverage ?? 0, max: 40, color: '#2D7FD3' },
            { label: 'Filter Strength', val: breakdown.filter_strength ?? 0, max: 30, color: '#267C36' },
            { label: 'Photostability', val: breakdown.photostability ?? 0, max: 20, color: '#C9A96E' },
            { label: 'Formulation', val: breakdown.formulation ?? 0, max: 10, color: '#A87373' },
          ].map(seg => (
            <div key={seg.label} title={`${seg.label}: ${seg.val}/${seg.max}`}
              style={{ width: `${(seg.val / 100) * 100}%`, background: seg.color, minWidth: seg.val > 0 ? '4px' : '0' }} />
          ))}
        </div>
        <div style={{ display: 'flex', gap: '12px', flexWrap: 'wrap', marginTop: '6px' }}>
          {[
            { label: 'UV Coverage', val: breakdown.uv_coverage ?? 0, max: 40, color: '#2D7FD3' },
            { label: 'Filter Strength', val: breakdown.filter_strength ?? 0, max: 30, color: '#267C36' },
            { label: 'Photostability', val: breakdown.photostability ?? 0, max: 20, color: '#C9A96E' },
            { label: 'Formulation', val: breakdown.formulation ?? 0, max: 10, color: '#A87373' },
          ].map(seg => (
            <span key={seg.label} style={{ fontSize: '10px', color: seg.color, fontWeight: 600 }}>
              {seg.label}: {seg.val}/{seg.max}
            </span>
          ))}
        </div>
      </div>

      {/* Warnings/flags */}
      {[...warnings, ...flags].length > 0 && (
        <div style={{ marginBottom: '12px' }}>
          {[...warnings, ...flags].map((w, i) => (
            <div key={i} style={{
              fontSize: '12px', padding: '7px 10px', borderRadius: '8px', marginBottom: '5px',
              background: w.startsWith('🚨') ? '#fff0f0' : '#fffaf0',
              border: `1px solid ${w.startsWith('🚨') ? '#f5c6cb' : '#fde8b0'}`,
              color: w.startsWith('🚨') ? '#721C24' : '#856404'
            }}>{w}</div>
          ))}
        </div>
      )}

      {/* Filters detected — collapsible */}
      {filters.length > 0 && (
        <div>
          <button onClick={() => setOpen(!open)} style={{
            background: 'none', border: 'none', padding: '6px 0',
            fontSize: '12px', color: 'var(--text-sub)', cursor: 'pointer',
            display: 'flex', alignItems: 'center', gap: '6px'
          }}>
            <i className={`fa-solid fa-chevron-${open ? 'up' : 'down'} fa-xs`}></i>
            UV Filters Detected ({filters.length})
          </button>
          {open && (
            <div style={{ display: 'flex', gap: '6px', flexWrap: 'wrap', marginTop: '4px' }}>
              {filters.map((f, i) => (
                <span key={i} style={{
                  fontSize: '11px', padding: '3px 9px', borderRadius: '12px',
                  background: 'var(--rose)', color: 'var(--dusty-rose-dark)',
                  border: '1px solid var(--border)'
                }}>{f}</span>
              ))}
            </div>
          )}
        </div>
      )}

      <p style={{ fontSize: '10px', color: 'var(--text-sub)', marginTop: '12px', fontStyle: 'italic' }}>
        * Estimates based on filter type and position. Not lab-tested values.
        PA rating requires PPD test. SPF requires in-vitro/in-vivo testing.
      </p>
    </div>
  );
}

export default function ResultCards({ result, concerns, skinType, currency, alternatives, altLoading, bestPrice, bestPriceLoading, fetchInput }) {
  const [showBreakdown, setShowBreakdown] = useState(false);
  const [showIngTable, setShowIngTable] = useState(false);
  const valueChip = getValueChip(
    result.price_analysis?.value_tier,
    result.price_analysis?.ratio
  );

  return (
    <>
      {/* CARD 1: MAIN WORTH SCORE */}
      <div className="sc-card result-card card-1" data-testid="card-main-worth" style={{ "--anim-delay": "0s" }}>
        <h2 className="card-title"><i className="fa-solid fa-chart-line"></i> Main Worth Score</h2>
        <div className="score-header">
          <ScoreCircle score={result.main_worth_score} />
          <div className="score-meta">
            <TierBadge tier={result.main_worth_tier} score={result.main_worth_score} />
            {result.price_analysis?.value_tier && result.price_analysis.value_tier !== 'fair' && (
              <div style={{ color: valueChip.color, fontSize: "0.75rem", fontWeight: 600, marginBottom: "4px" }}>
                {result.price_analysis.value_tier === 'overpriced' ? 'But Overpriced vs Category Avg' :
                 result.price_analysis.value_tier === 'slightly_overpriced' ? 'But Slightly Overpriced' :
                 result.price_analysis.value_tier === 'underpriced' ? 'Good Value for Money' : null}
              </div>
            )}
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
          {showBreakdown ? "Hide" : "Show"} Analysis Details {showBreakdown ? <i className="fa-solid fa-chevron-up"></i> : <i className="fa-solid fa-chevron-down"></i>}
        </button>
        <div className={"breakdown" + (showBreakdown ? " open" : "")} data-testid="breakdown-details">
            <BreakdownRow icon="fa-solid fa-chart-bar" label="Active Ingredients (What's Inside)" score={result.component_scores?.A} max={45} details={result.component_details?.A} />
            <BreakdownRow icon="fa-solid fa-flask" label="Formula Quality (How Well Made)" score={result.component_scores?.B} max={20} details={result.component_details?.B} />
            <BreakdownRow icon="fa-solid fa-check-circle" label="Claims vs Reality (Honesty Score)" score={result.component_scores?.C} max={15} details={result.component_details?.C} />
            <BreakdownRow icon="fa-solid fa-shield-halved" label="Safety Profile" score={result.component_scores?.D} max={10} details={result.component_details?.D} />
            <BreakdownRow icon="fa-solid fa-coins" label="Price Fairness" score={result.component_scores?.E} max={10} details={result.component_details?.E} />
          </div>

        {result.red_flags?.length > 0 && (
          <div className="red-flags-section" data-testid="red-flags-section">
            <h4 className="red-flags-title"><i className="fa-solid fa-triangle-exclamation"></i> Worth Red Flags</h4>
            <ul className="red-flags-list">
              {result.red_flags.map((rf, i) => <li key={i} data-testid={`red-flag-${i}`}>{rf}</li>)}
            </ul>
          </div>
        )}

        {/* Ingredient Breakdown Table */}
        {result.identified_actives?.length > 0 && (
          <div style={{ marginTop: "1rem" }}>
            <button className="breakdown-toggle" onClick={() => setShowIngTable(!showIngTable)} aria-expanded={showIngTable} style={{ fontSize: "0.82rem" }}>
              <i className="fa-solid fa-table"></i> {showIngTable ? "Hide" : "Show"} Active Ingredient Table ({result.identified_actives.length})
              {showIngTable ? <i className="fa-solid fa-chevron-up" style={{ marginLeft: "6px" }}></i> : <i className="fa-solid fa-chevron-down" style={{ marginLeft: "6px" }}></i>}
            </button>
            <div className={"breakdown" + (showIngTable ? " open" : "")}>
              <IngredientBreakdownTable actives={result.identified_actives} />
            </div>
          </div>
        )}

        {/* Active Classes Buckets */}

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

      {/* CARD 2B: SUNSCREEN ANALYSIS — only shown when Sun Protection concern selected */}
      {result.skin_concern_fit?.['Sun Protection']?.sunscreen_analysis && (
        <SunscreenAnalysisCard data={result.skin_concern_fit['Sun Protection']} />
      )}

      {/* CARD 3: SKIN TYPE COMPAT */}
      <div className="sc-card result-card card-3" data-testid="card-skin-type" style={{ "--anim-delay": "0.3s" }}>
        <h2 className="card-title"><i className="fa-solid fa-user-check"></i> {skinType} Skin Compatibility</h2>
        <div className="compat-score-row">
          <span className="compat-pct" style={{ color: getBarColor(result.skin_type_compatibility) }}>{result.skin_type_compatibility}%</span>
          <ProgressBar pct={result.skin_type_compatibility} label="compat" />
        </div>
        {result.skin_type_risk_level && (
          <div style={{ marginTop: "8px", marginBottom: "6px" }}>
            {result.skin_type_risk_level === "low" && (
              <span style={{ fontSize: "0.78rem", background: "#D4EDDA", color: "#155724", padding: "3px 10px", borderRadius: "12px", fontWeight: 600 }}>✓ Low sensitivity risk overall.</span>
            )}
            {result.skin_type_risk_level === "moderate" && (
              <span style={{ fontSize: "0.78rem", background: "#FFF3CD", color: "#856404", padding: "3px 10px", borderRadius: "12px", fontWeight: 600 }}>⚠ Some ingredients may not suit acne-prone or sensitive areas.</span>
            )}
            {result.skin_type_risk_level === "high" && (
              <span style={{ fontSize: "0.78rem", background: "#F8D7DA", color: "#721C24", padding: "3px 10px", borderRadius: "12px", fontWeight: 600 }}>⚠ Important: multiple acne or sensitivity risks detected. See notes below.</span>
            )}
          </div>
        )}
        <SkinTypeDetails details={result.skin_type_details} score={result.skin_type_compatibility} betterSuited={result.better_suited} formNotes={result.skin_type_details?.formulation_notes} riskLevel={result.skin_type_risk_level} />
      </div>

      {/* CARD 4A: ALTERNATIVES */}
      <AlternativesCard result={result} concerns={concerns} alternatives={alternatives} altLoading={altLoading} currency={currency} />

      {/* CARD 4B: BEST PRICE */}
      <BestPriceCard bestPrice={bestPrice} bestPriceLoading={bestPriceLoading} currency={currency} fetchInput={fetchInput} />

      <div className="disclaimer" data-testid="disclaimer">
        This tool works best with products that clearly disclose their ingredient list and active concentrations. Educational information only, not medical advice. Consult a dermatologist for personalized recommendations.
      </div>
    </>
  );
}
