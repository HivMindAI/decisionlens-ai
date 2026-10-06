"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";

import {
  friendlyApiError,
  requestWhatIfSimulation,
  type ScenarioAdjustments,
  type WhatIfSimulationResponse,
} from "@/lib/api";

type AdjustmentField = keyof ScenarioAdjustments;

type ScenarioInputs = Record<AdjustmentField, string>;

interface ScenarioFormError {
  message: string;
  field?: AdjustmentField;
}

const initialInputs: ScenarioInputs = {
  revenue_pct: "0",
  cogs_pct: "0",
  operating_expenses_pct: "0",
};

const adjustmentFields: Array<{
  name: AdjustmentField;
  label: string;
  detail: string;
}> = [
  {
    name: "revenue_pct",
    label: "Revenue",
    detail: "Applied to each baseline forecast period",
  },
  {
    name: "cogs_pct",
    label: "COGS",
    detail: "Applied to each baseline forecast period",
  },
  {
    name: "operating_expenses_pct",
    label: "Operating expenses",
    detail: "Applied to each baseline forecast period",
  },
];

const numberFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 0,
});

export function ScenarioSimulator({ file }: { file: File }) {
  const [inputs, setInputs] = useState<ScenarioInputs>(initialInputs);
  const [result, setResult] = useState<WhatIfSimulationResponse | null>(null);
  const [error, setError] = useState<ScenarioFormError | null>(null);
  const [running, setRunning] = useState(false);
  const requestControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => requestControllerRef.current?.abort();
  }, []);

  function updateInput(field: AdjustmentField, value: string) {
    setInputs((current) => ({ ...current, [field]: value }));
    setError(null);
    setResult(null);
  }

  function resetScenario() {
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;
    setInputs(initialInputs);
    setResult(null);
    setError(null);
    setRunning(false);
  }

  async function runScenario(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const validation = validateScenario(inputs);
    if ("error" in validation) {
      setError(validation.error);
      return;
    }

    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setError(null);
    setRunning(true);

    try {
      const response = await requestWhatIfSimulation(
        file,
        validation.scenario,
        controller.signal,
      );
      setResult(response);
    } catch (requestError) {
      if (!isAbortError(requestError)) {
        setError({ message: friendlyApiError(requestError) });
      }
    } finally {
      if (requestControllerRef.current === controller) {
        requestControllerRef.current = null;
        setRunning(false);
      }
    }
  }

  return (
    <section aria-labelledby="scenario-simulator-title" className="workspace-section">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between sm:gap-8">
        <div>
          <p className="section-eyebrow">Scenario planning</p>
          <h2
            id="scenario-simulator-title"
            className="mt-2 text-xl font-semibold tracking-[-0.025em] text-[var(--ink)] sm:text-2xl"
          >
            What-if decision simulator
          </h2>
        </div>
        <p className="max-w-2xl text-sm leading-6 text-[var(--muted)] sm:text-right">
          Test percentage adjustments against the verified baseline forecast. Results are
          calculated by the DecisionLens backend.
        </p>
      </div>

      <form className="mt-6" onSubmit={runScenario} noValidate>
        <div className="grid gap-3 md:grid-cols-3">
          {adjustmentFields.map((field) => {
            const inputId = `scenario-${field.name}`;
            const hintId = `${inputId}-hint`;
            const hasError = error?.field === field.name;

            return (
              <div
                key={field.name}
                className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-4"
              >
                <label
                  htmlFor={inputId}
                  className="text-sm font-semibold text-[var(--ink)]"
                >
                  {field.label}
                </label>
                <div className="relative mt-3">
                  <input
                    id={inputId}
                    name={field.name}
                    type="number"
                    min="-100"
                    max="500"
                    step="0.1"
                    inputMode="decimal"
                    value={inputs[field.name]}
                    onChange={(event) => updateInput(field.name, event.target.value)}
                    disabled={running}
                    aria-describedby={hintId}
                    aria-invalid={hasError}
                    className="h-11 w-full rounded-lg border border-[var(--border-strong)] bg-white px-3 pr-10 font-mono text-base font-semibold text-[var(--ink)] tabular-nums disabled:cursor-not-allowed disabled:opacity-60"
                  />
                  <span
                    aria-hidden="true"
                    className="pointer-events-none absolute inset-y-0 right-3 flex items-center text-sm font-medium text-[var(--muted)]"
                  >
                    %
                  </span>
                </div>
                <p id={hintId} className="mt-2 text-xs leading-5 text-[var(--muted)]">
                  {field.detail}
                </p>
              </div>
            );
          })}
        </div>

        <div className="mt-4 flex flex-col gap-4 border-t border-[var(--border-soft)] pt-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium text-[var(--muted-strong)]">
              Positive values increase a metric. Negative values decrease it.
            </p>
            <p className="mt-1 text-xs text-[var(--muted)]">
              Accepted range: -100% through +500%.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap items-center gap-2">
            <button type="submit" className="primary-button" disabled={running}>
              {running ? (
                <>
                  <span className="loading-spinner mr-2 border-white/35 border-t-white" aria-hidden="true" />
                  Running scenario…
                </>
              ) : (
                "Run scenario"
              )}
            </button>
            <button type="button" className="text-button" onClick={resetScenario}>
              Reset scenario
            </button>
          </div>
        </div>

        {error && (
          <div
            className="mt-4 rounded-lg border border-[#e5b9b5] bg-[#fff4f3] px-4 py-3 text-sm leading-6 text-[#8d3029]"
            role="alert"
          >
            {error.message}
          </div>
        )}

        {running && (
          <p className="sr-only" role="status">
            Calculating scenario results.
          </p>
        )}
      </form>

      {result && <ScenarioResults result={result} />}
    </section>
  );
}

function ScenarioResults({ result }: { result: WhatIfSimulationResponse }) {
  const { summary } = result;
  const scenarioMatchesBaseline = Object.values(result.scenario).every(
    (adjustment) => adjustment === 0,
  );

  return (
    <div className="mt-7 border-t border-[var(--border)] pt-7" aria-live="polite">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="section-eyebrow">Scenario result</p>
          <h3 className="mt-2 text-lg font-semibold tracking-[-0.02em] text-[var(--ink)]">
            Final forecast month · {formatPeriod(summary.final_period)}
          </h3>
        </div>
        <p className="text-xs leading-5 text-[var(--muted)] sm:max-w-lg sm:text-right">
          Revenue {formatAdjustment(result.scenario.revenue_pct)} · COGS{" "}
          {formatAdjustment(result.scenario.cogs_pct)} · Operating expenses{" "}
          {formatAdjustment(result.scenario.operating_expenses_pct)}
        </p>
      </div>

      {scenarioMatchesBaseline && (
        <div className="mt-5 rounded-lg border border-[#bcd8cc] bg-[var(--accent-soft)] px-4 py-3 text-sm font-semibold text-[var(--deep-green)]">
          Scenario matches baseline. All submitted adjustments are zero, so the projected
          results and differences remain unchanged.
        </div>
      )}

      <div className="mt-5 grid overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--border)] lg:grid-cols-[1fr_1fr_0.9fr]">
        <ComparisonColumn
          label="Baseline"
          operatingProfit={summary.baseline_final_operating_profit}
          operatingMargin={summary.baseline_final_operating_margin_pct}
        />
        <ComparisonColumn
          label="Scenario"
          operatingProfit={summary.scenario_final_operating_profit}
          operatingMargin={summary.scenario_final_operating_margin_pct}
          emphasized
        />
        <div className="bg-[var(--accent-soft)] p-5 sm:p-6">
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--accent-strong)]">
            Final-month difference
          </p>
          <p
            className={`mt-5 font-mono text-2xl font-semibold tracking-[-0.03em] tabular-nums ${differenceTone(summary.final_operating_profit_difference)}`}
          >
            {formatSignedFinancial(summary.final_operating_profit_difference)}
          </p>
          <p className="mt-1 text-xs text-[var(--muted)]">financial units</p>
          <p
            className={`mt-5 font-mono text-lg font-semibold tabular-nums ${differenceTone(summary.final_operating_margin_difference_pp)}`}
          >
            {formatSignedPercentagePoints(
              summary.final_operating_margin_difference_pp,
            )}
          </p>
          <p className="mt-1 text-xs text-[var(--muted)]">
            operating-margin difference
          </p>
        </div>
      </div>

      <ThreeMonthComparison result={result} />
      <PeriodComparison result={result} />
      <ScenarioAssumptions result={result} />

      {result.scenario_evidence.length > 0 && (
        <details className="group mt-4 rounded-lg border border-[var(--border)] bg-[var(--surface-muted)]">
          <summary className="flex list-none items-center justify-between gap-4 px-4 py-3 text-sm font-medium text-[var(--ink)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus)]">
            How this was calculated
            <span
              aria-hidden="true"
              className="text-lg text-[var(--muted)] transition-transform group-open:rotate-45"
            >
              +
            </span>
          </summary>
          <ul className="space-y-2 border-t border-[var(--border)] px-4 py-4 text-sm leading-6 text-[var(--muted-strong)]">
            {result.scenario_evidence.map((evidence) => (
              <li key={evidence.id} className="flex gap-2">
                <span
                  aria-hidden="true"
                  className="mt-[0.65rem] h-1 w-1 shrink-0 rounded-full bg-[var(--accent-strong)]"
                />
                <span>{evidence.statement}</span>
              </li>
            ))}
          </ul>
        </details>
      )}

      {result.warnings.length > 0 && (
        <div
          className="mt-4 rounded-lg border border-[#ead7a5] bg-[#fff8e6] px-4 py-3 text-sm leading-6 text-[#755819]"
          role="status"
        >
          <p className="font-semibold">Scenario notes</p>
          <ul className="mt-1 list-disc space-y-1 pl-5">
            {result.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function ComparisonColumn({
  label,
  operatingProfit,
  operatingMargin,
  emphasized = false,
}: {
  label: string;
  operatingProfit: number;
  operatingMargin: number | null;
  emphasized?: boolean;
}) {
  return (
    <div className={`p-5 sm:p-6 ${emphasized ? "bg-[#fbfdfb]" : "bg-white"}`}>
      <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
        {label}
      </p>
      <div className="mt-5">
        <p className="font-mono text-2xl font-semibold tracking-[-0.03em] text-[var(--ink)] tabular-nums">
          {formatFinancial(operatingProfit)}
        </p>
        <p className="mt-1 text-xs text-[var(--muted)]">Operating profit · financial units</p>
      </div>
      <div className="mt-5 border-t border-[var(--border-soft)] pt-4">
        <p className="font-mono text-lg font-semibold text-[var(--ink)] tabular-nums">
          {formatPercent(operatingMargin)}
        </p>
        <p className="mt-1 text-xs text-[var(--muted)]">Operating margin</p>
      </div>
    </div>
  );
}

function ThreeMonthComparison({ result }: { result: WhatIfSimulationResponse }) {
  const { summary } = result;

  return (
    <div className="mt-5 rounded-xl border border-[var(--border)] bg-white p-5 sm:p-6">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
            Three-month impact
          </p>
          <h4 className="mt-2 text-base font-semibold text-[var(--ink)]">
            Cumulative projected operating profit
          </h4>
        </div>
        <p className="text-xs text-[var(--muted)]">All three forecast periods combined</p>
      </div>
      <dl className="mt-5 grid gap-4 sm:grid-cols-3">
        <ComparisonTotal
          label="Baseline total"
          value={summary.baseline_3_month_operating_profit_total}
        />
        <ComparisonTotal
          label="Scenario total"
          value={summary.scenario_3_month_operating_profit_total}
        />
        <ComparisonTotal
          label="Difference"
          value={summary.three_month_operating_profit_difference}
          signed
        />
      </dl>
    </div>
  );
}

function ComparisonTotal({
  label,
  value,
  signed = false,
}: {
  label: string;
  value: number;
  signed?: boolean;
}) {
  return (
    <div className="border-l-2 border-[var(--border)] pl-4 last:border-[var(--accent-strong)]">
      <dt className="text-xs font-medium text-[var(--muted)]">{label}</dt>
      <dd
        className={`mt-2 font-mono text-lg font-semibold tabular-nums ${
          signed ? differenceTone(value) : "text-[var(--ink)]"
        }`}
      >
        {signed ? formatSignedFinancial(value) : formatFinancial(value)}
      </dd>
      <dd className="mt-1 text-xs text-[var(--muted)]">financial units</dd>
    </div>
  );
}

function PeriodComparison({ result }: { result: WhatIfSimulationResponse }) {
  return (
    <div className="mt-5">
      <div className="mb-3 flex items-center justify-between gap-4">
        <h4 className="text-sm font-semibold text-[var(--ink)]">
          Period-by-period comparison
        </h4>
        <span className="text-xs text-[var(--muted)]">Operating profit</span>
      </div>
      <div className="overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="w-full min-w-[650px] border-collapse bg-white text-left">
          <thead>
            <tr className="border-b border-[var(--border)] bg-[var(--surface-muted)]">
              <th className="px-4 py-3 text-xs font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                Period
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                Baseline
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                Scenario
              </th>
              <th className="px-4 py-3 text-right text-xs font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                Difference
              </th>
            </tr>
          </thead>
          <tbody>
            {result.periods.map((period) => (
              <tr
                key={period.period}
                className="border-b border-[var(--border-soft)] last:border-b-0"
              >
                <td className="px-4 py-4 text-sm font-semibold text-[var(--ink)]">
                  {formatPeriod(period.period)}
                </td>
                <td className="px-4 py-4 text-right font-mono text-sm text-[var(--muted-strong)] tabular-nums">
                  {formatFinancial(period.baseline.operating_profit)}
                </td>
                <td className="px-4 py-4 text-right font-mono text-sm font-semibold text-[var(--ink)] tabular-nums">
                  {formatFinancial(period.scenario.operating_profit)}
                </td>
                <td
                  className={`px-4 py-4 text-right font-mono text-sm font-semibold tabular-nums ${differenceTone(period.difference.operating_profit_difference)}`}
                >
                  {formatSignedFinancial(period.difference.operating_profit_difference)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function ScenarioAssumptions({ result }: { result: WhatIfSimulationResponse }) {
  return (
    <div className="mt-5 grid gap-4 lg:grid-cols-2">
      <div className="rounded-xl border border-[var(--border)] bg-white p-5">
        <h4 className="text-sm font-semibold text-[var(--ink)]">Scenario assumptions</h4>
        <ul className="mt-3 space-y-2 text-sm leading-6 text-[var(--muted-strong)]">
          {result.assumptions.map((assumption) => (
            <li key={assumption} className="flex gap-2">
              <span
                aria-hidden="true"
                className="mt-[0.65rem] h-1 w-1 shrink-0 rounded-full bg-[var(--accent-strong)]"
              />
              <span>{assumption}</span>
            </li>
          ))}
        </ul>
      </div>
      <aside className="rounded-xl border border-[var(--border-strong)] bg-[var(--surface-muted)] p-5">
        <h4 className="text-sm font-semibold text-[var(--ink)]">
          Interpretation limits
        </h4>
        <ul className="mt-3 space-y-2 text-sm leading-6 text-[var(--muted-strong)]">
          {result.limitations.map((limitation) => (
            <li key={limitation} className="flex gap-2">
              <span aria-hidden="true" className="text-[var(--muted)]">
                —
              </span>
              <span>
                {limitation.replace(
                  "backtest_mae_range",
                  "Historical forecast-error range",
                )}
              </span>
            </li>
          ))}
        </ul>
      </aside>
    </div>
  );
}

function validateScenario(
  inputs: ScenarioInputs,
): { scenario: ScenarioAdjustments } | { error: ScenarioFormError } {
  const scenario: ScenarioAdjustments = {
    revenue_pct: 0,
    cogs_pct: 0,
    operating_expenses_pct: 0,
  };

  for (const field of adjustmentFields) {
    const rawValue = inputs[field.name].trim();
    if (!rawValue) {
      return {
        error: {
          field: field.name,
          message: `Enter a percentage adjustment for ${field.label}.`,
        },
      };
    }

    const value = Number(rawValue);
    if (!Number.isFinite(value)) {
      return {
        error: {
          field: field.name,
          message: `Enter a valid numeric adjustment for ${field.label}.`,
        },
      };
    }

    if (value < -100 || value > 500) {
      return {
        error: {
          field: field.name,
          message: `${field.label} must be between -100% and +500%.`,
        },
      };
    }

    scenario[field.name] = value;
  }

  return { scenario };
}

function formatFinancial(value: number): string {
  return numberFormatter.format(value);
}

function formatSignedFinancial(value: number): string {
  if (value > 0) return `+${numberFormatter.format(value)}`;
  if (value < 0) return `\u2212${numberFormatter.format(Math.abs(value))}`;
  return "0";
}

function formatPercent(value: number | null): string {
  return value === null ? "Not defined" : `${numberFormatter.format(value)}%`;
}

function formatSignedPercentagePoints(value: number | null): string {
  if (value === null) return "Not defined";
  return `${formatSignedFinancial(value)} pp`;
}

function formatAdjustment(value: number): string {
  return `${formatSignedFinancial(value)}%`;
}

function formatPeriod(period: string): string {
  const [year, month] = period.split("-").map(Number);
  if (!year || !month) return period;
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(Date.UTC(year, month - 1, 1)));
}

function differenceTone(value: number | null): string {
  if (value === null || value === 0) return "text-[var(--muted-strong)]";
  return value > 0 ? "text-[var(--positive)]" : "text-[var(--negative)]";
}

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
