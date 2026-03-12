import { StatusResponse } from "../api/client";

/**
 * Single source of truth for the suitability score shown on both the
 * generating animation screen and the results screen.
 *
 * Formula:
 *   base = keyword_coverage*50 + experience_depth*25 + extraction_clarity*25
 *   penalise 10pts per severe truthfulness/fabrication flag
 *   cap: no more than raw_suitability_score + 35 pts improvement
 *   cap: if raw_suitability_score < 55, ceiling is 70
 */
export function computeSuitabilityScore(status: StatusResponse): number {
  const kwCoverage = status.keyword_coverage ?? 0;
  const expDepth = Math.min((status.experience_count ?? 0) / 3, 1);
  const clarity = status.extraction_confidence ?? 0;

  const base = kwCoverage * 50 + expDepth * 25 + clarity * 25;
  const severeFlags = (status.validation_flags ?? []).filter((f) =>
    f.toLowerCase().includes("truthfulness") || f.toLowerCase().includes("fabricat")
  ).length;
  const uncapped = Math.max(0, Math.min(100, Math.round(base - severeFlags * 10)));

  const rawInput = status.raw_suitability_score;
  if (rawInput == null) return uncapped;
  return Math.min(uncapped, rawInput + 35, rawInput < 55 ? 70 : 100);
}

export function scoreLabel(score: number): string {
  if (score >= 85) return "Excellent fit";
  if (score >= 70) return "Strong match";
  if (score >= 55) return "Good match";
  if (score >= 40) return "Moderate fit";
  return "Weak match";
}
