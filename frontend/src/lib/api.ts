export type ChangeUnit = "financial_units" | "percentage_points";
export type EvidenceUnit = "financial_units" | "percent" | "percentage_points";
export type Direction =
  | "increase"
  | "decrease"
  | "unchanged"
  | "undefined"
  | "not_applicable";
export type Severity = "low" | "medium" | "high";
export type ForecastModelName =
  | "NAIVE_LAST_VALUE"
  | "LINEAR_TREND"
  | "SEASONAL_NAIVE";

export interface MonthlyKpi {
  period: string;
  revenue: number;
  cogs: number;
  operating_expenses: number;
  gross_profit: number;
  operating_profit: number;
  gross_margin_pct: number | null;
  operating_margin_pct: number | null;
}

export interface MetricChange {
  value: number | null;
  previous_value: number | null;
  absolute_change: number | null;
  percent_change: number | null;
  unit: ChangeUnit;
}

export interface AnalysisChanges {
  revenue: MetricChange;
  cogs: MetricChange;
  operating_expenses: MetricChange;
  gross_profit: MetricChange;
  operating_profit: MetricChange;
  gross_margin_pct: MetricChange;
  operating_margin_pct: MetricChange;
}

export interface LargestMeasuredContributor {
  metric: "revenue" | "cogs" | "operating_expenses";
  impact: number;
  unit: "financial_units";
}

export interface ProfitChangeDecomposition {
  period: string;
  comparison_period: string;
  delta_operating_profit: number;
  revenue_impact: number;
  cogs_impact: number;
  operating_expenses_impact: number;
  largest_measured_contributor: LargestMeasuredContributor;
}

export interface EvidenceItem {
  id: string;
  type: "snapshot" | "comparison" | "decomposition" | "forecast";
  metric: string;
  period: string;
  comparison_period?: string | null;
  value: number | null;
  previous_value?: number | null;
  change?: number | null;
  unit: EvidenceUnit;
  direction: Direction;
  statement: string;
}

export interface StatisticalAnomaly {
  id: string;
  metric: "revenue" | "cogs" | "operating_expenses" | "operating_profit";
  period: string;
  comparison_period: string;
  direction: "increase" | "decrease";
  observed_change: number;
  change_unit: "percent" | "financial_units";
  historical_median_change: number;
  historical_observation_count: number;
  robust_z: number;
  severity: Severity;
  statement: string;
}

export interface BusinessSignal {
  id: string;
  type:
    | "MARGIN_COMPRESSION"
    | "COST_GROWTH_OUTPACING_REVENUE"
    | "PROFIT_DETERIORATION"
    | "PROFIT_RECOVERY"
    | "REVENUE_DECLINE";
  severity: Severity;
  period: string;
  comparison_period: string;
  metrics: string[];
  measured_change: number;
  change_unit: "financial_units" | "percent" | "percentage_points";
  classification:
    | "profit_declined"
    | "positive_to_loss"
    | "loss_deepened"
    | "profit_increased"
    | "loss_to_positive"
    | "loss_narrowed"
    | null;
  statement: string;
  evidence_ids: string[];
}

export interface ForecastModelDiagnostics {
  selected_model: ForecastModelName;
  backtest_points: number;
  mae: number;
  normalized_mae_pct: number | null;
}

export interface ForecastModels {
  revenue: ForecastModelDiagnostics;
  cogs: ForecastModelDiagnostics;
  operating_expenses: ForecastModelDiagnostics;
}

export interface ForecastRange {
  low: number;
  high: number;
}

export interface BaseMetricForecast {
  value: number;
  backtest_mae_range: ForecastRange;
}

export interface ForecastPeriod {
  period: string;
  revenue: BaseMetricForecast;
  cogs: BaseMetricForecast;
  operating_expenses: BaseMetricForecast;
  gross_profit: number;
  operating_profit: number;
  operating_profit_component_range: ForecastRange;
  gross_margin_pct: number | null;
  operating_margin_pct: number | null;
}

export interface ForecastSummary {
  horizon_months: 3;
  models: ForecastModels;
  periods: ForecastPeriod[];
  limitations: string[];
  warnings: string[];
}

export interface AnalysisSummaryResponse {
  status: "ok";
  period_start: string;
  period_end: string;
  latest_period: string;
  previous_period: string;
  latest_snapshot: MonthlyKpi;
  changes: AnalysisChanges;
  profit_change_decomposition: ProfitChangeDecomposition;
  evidence: EvidenceItem[];
  anomalies: StatisticalAnomaly[];
  signals: BusinessSignal[];
  forecast: ForecastSummary;
  series: MonthlyKpi[];
  warnings: string[];
}

export type DecisionFocus =
  | "cost_control"
  | "revenue_attention"
  | "margin_pressure"
  | "profitability"
  | "forecast_risk"
  | "stable_outlook";

export type NextStepAction =
  | "REVIEW_OPERATING_EXPENSES"
  | "REVIEW_COGS"
  | "INVESTIGATE_REVENUE_DECLINE"
  | "MONITOR_MARGIN_PRESSURE"
  | "REVIEW_PROFITABILITY"
  | "REVIEW_FORECAST_RISK"
  | "NO_URGENT_ACTION";

export interface DecisionBrief {
  focus: DecisionFocus;
  headline: string;
  reasoning: string;
  evidence_ids: string[];
  next_step: NextStepAction;
  next_step_text: string;
}

export interface DecisionGenerationMetadata {
  mode: "llm" | "deterministic_fallback";
  ai_used: boolean;
  provider: string | null;
  model: string | null;
  fallback_reason: string | null;
}

export interface DecisionBriefResponse {
  status: "ok";
  decision_brief: DecisionBrief;
  generation: DecisionGenerationMetadata;
  supporting_evidence: EvidenceItem[];
  limitations: string[];
}

export interface ScenarioAdjustments {
  revenue_pct: number;
  cogs_pct: number;
  operating_expenses_pct: number;
}

export interface BaselineSimulationMetrics {
  revenue: BaseMetricForecast;
  cogs: BaseMetricForecast;
  operating_expenses: BaseMetricForecast;
  gross_profit: number;
  operating_profit: number;
  operating_profit_component_range: ForecastRange;
  gross_margin_pct: number | null;
  operating_margin_pct: number | null;
}

export interface ScenarioMetrics {
  revenue: number;
  cogs: number;
  operating_expenses: number;
  gross_profit: number;
  operating_profit: number;
  gross_margin_pct: number | null;
  operating_margin_pct: number | null;
}

export interface ScenarioDifference {
  revenue_difference: number;
  cogs_difference: number;
  operating_expenses_difference: number;
  gross_profit_difference: number;
  operating_profit_difference: number;
  gross_margin_difference_pp: number | null;
  operating_margin_difference_pp: number | null;
}

export interface SimulationPeriod {
  period: string;
  baseline: BaselineSimulationMetrics;
  scenario: ScenarioMetrics;
  difference: ScenarioDifference;
}

export interface SimulationSummary {
  final_period: string;
  baseline_final_operating_profit: number;
  scenario_final_operating_profit: number;
  final_operating_profit_difference: number;
  baseline_final_operating_margin_pct: number | null;
  scenario_final_operating_margin_pct: number | null;
  final_operating_margin_difference_pp: number | null;
  baseline_3_month_operating_profit_total: number;
  scenario_3_month_operating_profit_total: number;
  three_month_operating_profit_difference: number;
}

export interface ScenarioEvidenceItem {
  id: string;
  type:
    | "scenario_operating_profit"
    | "scenario_operating_profit_difference"
    | "scenario_operating_margin"
    | "scenario_cumulative_operating_profit_difference";
  period: string;
  value: number;
  unit: EvidenceUnit;
  statement: string;
}

export interface WhatIfSimulationResponse {
  status: "ok";
  scenario: ScenarioAdjustments;
  forecast_horizon_months: 3;
  baseline_forecast_models: ForecastModels;
  periods: SimulationPeriod[];
  summary: SimulationSummary;
  scenario_evidence: ScenarioEvidenceItem[];
  assumptions: string[];
  limitations: string[];
  warnings: string[];
}

interface ApiErrorPayload {
  status?: "error";
  error?: {
    code?: string;
    message?: string;
    field?: string;
    row?: number;
  };
  detail?: string;
}

const DEFAULT_API_URL = "http://127.0.0.1:8000";
const configuredApiUrl = process.env.NEXT_PUBLIC_DECISIONLENS_API_URL?.trim();

export const API_BASE_URL = (configuredApiUrl || DEFAULT_API_URL).replace(/\/+$/, "");

export class DecisionLensApiError extends Error {
  readonly status: number | null;
  readonly code: string | null;

  constructor(message: string, options?: { status?: number; code?: string }) {
    super(message);
    this.name = "DecisionLensApiError";
    this.status = options?.status ?? null;
    this.code = options?.code ?? null;
  }
}

async function parseError(response: Response): Promise<DecisionLensApiError> {
  let payload: ApiErrorPayload | null = null;

  try {
    payload = (await response.json()) as ApiErrorPayload;
  } catch {
    // The application supplies a safe fallback message below.
  }

  const message =
    payload?.error?.message ||
    payload?.detail ||
    "The DecisionLens service could not complete this request.";

  return new DecisionLensApiError(message, {
    status: response.status,
    code: payload?.error?.code,
  });
}

async function postCsv<T>(
  path: string,
  file: File,
  signal?: AbortSignal,
  fields?: Record<string, string>,
): Promise<T> {
  const formData = new FormData();
  formData.append("file", file);
  Object.entries(fields || {}).forEach(([key, value]) => {
    formData.append(key, value);
  });

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST",
      body: formData,
      signal,
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw error;
    }
    throw new DecisionLensApiError(
      "The analysis service is unavailable. Confirm the backend is running and try again.",
    );
  }

  if (!response.ok) {
    throw await parseError(response);
  }

  return (await response.json()) as T;
}

export async function checkApiHealth(signal?: AbortSignal): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/health`, {
      method: "GET",
      signal,
    });
    return response.ok;
  } catch {
    return false;
  }
}

export function requestAnalysis(
  file: File,
  signal?: AbortSignal,
): Promise<AnalysisSummaryResponse> {
  return postCsv<AnalysisSummaryResponse>("/api/v1/analysis/summary", file, signal);
}

export function requestDecisionBrief(
  file: File,
  signal?: AbortSignal,
): Promise<DecisionBriefResponse> {
  return postCsv<DecisionBriefResponse>("/api/v1/decisions/brief", file, signal);
}

export function requestWhatIfSimulation(
  file: File,
  scenario: ScenarioAdjustments,
  signal?: AbortSignal,
): Promise<WhatIfSimulationResponse> {
  return postCsv<WhatIfSimulationResponse>(
    "/api/v1/simulations/what-if",
    file,
    signal,
    { scenario: JSON.stringify(scenario) },
  );
}

export function friendlyApiError(error: unknown): string {
  if (!(error instanceof DecisionLensApiError)) {
    return "Something unexpected interrupted the request. Please try again.";
  }

  const messages: Record<string, string> = {
    INVALID_FILE_TYPE: "Choose a CSV file and try again.",
    EMPTY_FILE: "The selected CSV is empty. Choose a file with monthly financial data.",
    MALFORMED_CSV: "The file could not be read as a valid CSV. Check its formatting and try again.",
    MISSING_REQUIRED_COLUMNS:
      "The CSV is missing one or more required columns: date, revenue, cogs, and operating_expenses.",
    INVALID_DATE: "Every row needs a valid calendar date.",
    DUPLICATE_MONTH: "The CSV contains more than one row for the same calendar month.",
    MISSING_MONTH: "The CSV must contain consecutive monthly periods without gaps.",
    INSUFFICIENT_HISTORY: "Include at least 12 consecutive monthly periods before analyzing.",
    INVALID_NUMERIC_VALUE:
      "Revenue, COGS, and operating-expense values must all be valid numbers.",
    NEGATIVE_VALUE: "Revenue, COGS, and operating-expense values cannot be negative.",
    FILE_TOO_LARGE: "The CSV is larger than the 5 MB upload limit.",
    INVALID_SCENARIO_ADJUSTMENT:
      "Use a valid scenario percentage between -100% and +500%.",
  };

  return (error.code && messages[error.code]) || error.message;
}
