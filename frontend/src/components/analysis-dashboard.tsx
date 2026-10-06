import type {
  AnalysisSummaryResponse,
  BusinessSignal,
  DecisionBriefResponse,
  EvidenceItem,
  ForecastModelDiagnostics,
  MetricChange,
  Severity,
  StatisticalAnomaly,
} from "@/lib/api";
import { ScenarioSimulator } from "@/components/scenario-simulator";

interface AnalysisDashboardProps {
  analysis: AnalysisSummaryResponse;
  file: File;
  brief: DecisionBriefResponse | null;
  briefError: string | null;
  briefLoading: boolean;
}

const numberFormatter = new Intl.NumberFormat("en-US", {
  maximumFractionDigits: 2,
  minimumFractionDigits: 0,
});

const signalTitles: Record<BusinessSignal["type"], string> = {
  MARGIN_COMPRESSION: "Margin compression",
  COST_GROWTH_OUTPACING_REVENUE: "Cost growth outpacing revenue",
  PROFIT_DETERIORATION: "Profit deterioration",
  PROFIT_RECOVERY: "Profit recovery",
  REVENUE_DECLINE: "Revenue decline",
};

const metricLabels: Record<string, string> = {
  revenue: "Revenue",
  cogs: "COGS",
  operating_expenses: "Operating expenses",
  operating_profit: "Operating profit",
  operating_margin_pct: "Operating margin",
  projected_revenue: "Projected revenue",
  projected_operating_profit: "Projected operating profit",
  projected_operating_margin_pct: "Projected operating margin",
  revenue_impact: "Revenue impact",
  cogs_impact: "COGS impact",
  operating_expenses_impact: "Operating-expense impact",
};

const modelLabels: Record<string, string> = {
  NAIVE_LAST_VALUE: "Last observed value",
  LINEAR_TREND: "Linear trend",
  SEASONAL_NAIVE: "Seasonal comparison",
};

export function AnalysisDashboard({
  analysis,
  file,
  brief,
  briefError,
  briefLoading,
}: AnalysisDashboardProps) {
  return (
    <div className="space-y-5 lg:space-y-6">
      <BusinessHealth analysis={analysis} />
      <DecisionFinding
        brief={brief}
        briefError={briefError}
        briefLoading={briefLoading}
      />
      <ProfitBridge analysis={analysis} />
      <SignalsAndAnomalies analysis={analysis} />
      <ForecastOutlook analysis={analysis} />
      <ScenarioSimulator file={file} />
      {(analysis.warnings.length > 0 || analysis.forecast.warnings.length > 0) && (
        <DataNotes
          notes={[...analysis.warnings, ...analysis.forecast.warnings]}
        />
      )}
    </div>
  );
}

function BusinessHealth({ analysis }: { analysis: AnalysisSummaryResponse }) {
  const snapshot = analysis.latest_snapshot;

  return (
    <section aria-labelledby="business-health-title" className="workspace-section">
      <SectionHeading
        eyebrow="Latest reported month"
        title="Business health"
        description={`Verified results for ${formatPeriod(analysis.latest_period)}, compared with ${formatPeriod(analysis.previous_period)}.`}
        id="business-health-title"
      />

      <div className="grid gap-px overflow-hidden rounded-xl border border-[var(--border)] bg-[var(--border)] md:grid-cols-3">
        <HealthMetric
          label="Revenue"
          value={formatFinancial(snapshot.revenue)}
          unit="financial units"
          change={formatPercentChange(analysis.changes.revenue)}
          tone={changeTone(analysis.changes.revenue.percent_change)}
        />
        <HealthMetric
          label="Operating profit"
          value={formatFinancial(snapshot.operating_profit)}
          unit="financial units"
          change={formatAbsoluteChange(analysis.changes.operating_profit)}
          tone={changeTone(analysis.changes.operating_profit.absolute_change)}
        />
        <HealthMetric
          label="Operating margin"
          value={formatPercent(snapshot.operating_margin_pct)}
          unit="of revenue"
          change={formatMarginChange(analysis.changes.operating_margin_pct)}
          tone={changeTone(analysis.changes.operating_margin_pct.absolute_change)}
        />
      </div>
    </section>
  );
}

function HealthMetric({
  label,
  value,
  unit,
  change,
  tone,
}: {
  label: string;
  value: string;
  unit: string;
  change: string;
  tone: "positive" | "negative" | "neutral";
}) {
  const toneClasses = {
    positive: "text-[var(--positive)]",
    negative: "text-[var(--negative)]",
    neutral: "text-[var(--muted)]",
  }[tone];

  return (
    <article className="bg-white p-5 sm:p-6">
      <p className="text-sm font-medium text-[var(--muted-strong)]">{label}</p>
      <p className="mt-4 font-mono text-[clamp(1.75rem,4vw,2.35rem)] font-semibold leading-none tracking-[-0.04em] text-[var(--ink)] tabular-nums">
        {value}
      </p>
      <p className="mt-2 text-xs text-[var(--muted)]">{unit}</p>
      <div className="mt-5 border-t border-[var(--border-soft)] pt-3">
        <p className={`text-sm font-medium ${toneClasses}`}>{change}</p>
        <p className="mt-1 text-xs text-[var(--muted)]">vs. previous month</p>
      </div>
    </article>
  );
}

function DecisionFinding({
  brief,
  briefError,
  briefLoading,
}: Pick<AnalysisDashboardProps, "brief" | "briefError" | "briefLoading">) {
  return (
    <section
      aria-labelledby="important-finding-title"
      className="overflow-hidden rounded-xl border border-[var(--border-dark)] bg-[var(--deep-green)] text-white shadow-[var(--shadow-subtle)]"
    >
      <div className="grid lg:grid-cols-[1.35fr_0.85fr]">
        <div className="p-6 sm:p-8 lg:p-9">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="section-eyebrow text-[#9fc3b5]">Most important finding</p>
            {brief && (
              <span className="rounded-full border border-white/15 bg-white/[0.08] px-3 py-1 text-xs font-medium text-[#dcece5]">
                {brief.generation.mode === "llm"
                  ? "AI-grounded"
                  : "Evidence-based fallback"}
              </span>
            )}
          </div>

          {briefLoading && <BriefLoadingState />}

          {!briefLoading && briefError && (
            <div className="mt-6 max-w-2xl" role="status">
              <h2
                id="important-finding-title"
                className="text-2xl font-semibold tracking-[-0.03em]"
              >
                Decision Brief is temporarily unavailable
              </h2>
              <p className="mt-3 text-sm leading-6 text-[#c4d8d0]">{briefError}</p>
              <p className="mt-2 text-sm leading-6 text-[#c4d8d0]">
                Your verified analytics remain available below.
              </p>
            </div>
          )}

          {!briefLoading && brief && (
            <>
              <h2
                id="important-finding-title"
                className="mt-6 max-w-3xl text-2xl font-semibold leading-tight tracking-[-0.035em] sm:text-3xl"
              >
                {brief.decision_brief.headline}
              </h2>
              <p className="mt-4 max-w-3xl text-[15px] leading-7 text-[#d4e3dd]">
                {brief.decision_brief.reasoning}
              </p>
              <div className="mt-7 border-l-2 border-[var(--accent)] pl-4">
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#9fc3b5]">
                  Safe next step
                </p>
                <p className="mt-2 max-w-2xl text-sm leading-6 text-white">
                  {brief.decision_brief.next_step_text}
                </p>
              </div>
            </>
          )}
        </div>

        <div className="border-t border-white/10 bg-black/10 p-6 sm:p-7 lg:border-l lg:border-t-0 lg:p-7">
          <p className="section-eyebrow text-[#9fc3b5]">Why this decision?</p>
          {briefLoading && (
            <p className="mt-5 text-sm leading-6 text-[#c4d8d0]">
              Matching the brief to verified evidence…
            </p>
          )}
          {!briefLoading && briefError && (
            <p className="mt-5 text-sm leading-6 text-[#c4d8d0]">
              Supporting evidence will appear here when the Decision Brief service is available.
            </p>
          )}
          {!briefLoading && brief && (
            <div className="mt-4 space-y-2.5">
              {brief.supporting_evidence.map((item) => (
                <EvidenceCard key={item.id} item={item} />
              ))}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function BriefLoadingState() {
  return (
    <div className="mt-7 max-w-2xl" role="status" aria-label="Preparing Decision Brief">
      <div className="h-7 w-3/4 animate-pulse rounded bg-white/12" />
      <div className="mt-5 h-3 w-full animate-pulse rounded bg-white/10" />
      <div className="mt-3 h-3 w-5/6 animate-pulse rounded bg-white/10" />
      <span className="sr-only">Preparing the evidence-backed Decision Brief.</span>
    </div>
  );
}

function EvidenceCard({ item }: { item: EvidenceItem }) {
  return (
    <article className="rounded-lg border border-white/12 bg-white/[0.06] p-3.5">
      <div className="flex items-start justify-between gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[#9fc3b5]">
          {metricLabels[item.metric] || humanize(item.metric)}
        </p>
        <span className="font-mono text-[11px] text-[#8da99e]">{item.id}</span>
      </div>
      <p className="mt-1.5 text-[13px] leading-5 text-[#eef5f2]">
        {formatNarrative(item.statement)}
      </p>
      <div className="mt-2.5 flex items-center gap-2 text-[11px] text-[#a9c2b8]">
        <span>{formatPeriod(item.period)}</span>
        {item.value !== null && (
          <>
            <span aria-hidden="true">·</span>
            <span className="font-mono tabular-nums">{formatEvidenceValue(item)}</span>
          </>
        )}
      </div>
    </article>
  );
}

function ProfitBridge({ analysis }: { analysis: AnalysisSummaryResponse }) {
  const decomposition = analysis.profit_change_decomposition;
  const contributor = decomposition.largest_measured_contributor;
  const impacts = [
    { label: "Revenue impact", value: decomposition.revenue_impact },
    { label: "COGS impact", value: decomposition.cogs_impact },
    {
      label: "Operating-expense impact",
      value: decomposition.operating_expenses_impact,
    },
    {
      label: "Total operating-profit change",
      value: decomposition.delta_operating_profit,
      total: true,
    },
  ];

  return (
    <section aria-labelledby="profit-change-title" className="workspace-section">
      <SectionHeading
        eyebrow="Arithmetic bridge"
        title="Why profit changed"
        description={`Measured contributions from ${formatPeriod(decomposition.comparison_period)} to ${formatPeriod(decomposition.period)}. These are arithmetic contributions, not causal claims.`}
        id="profit-change-title"
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {impacts.map((impact) => (
          <article
            key={impact.label}
            className={`rounded-xl border p-5 ${
              impact.total
                ? "border-[var(--border-dark)] bg-[var(--ink)] text-white"
                : "border-[var(--border)] bg-white"
            }`}
          >
            <p
              className={`text-sm font-medium ${
                impact.total ? "text-white/65" : "text-[var(--muted-strong)]"
              }`}
            >
              {impact.label}
            </p>
            <p
              className={`mt-5 font-mono text-2xl font-semibold tracking-[-0.03em] tabular-nums ${
                impact.total ? "text-white" : impactColor(impact.value)
              }`}
            >
              {formatSignedFinancial(impact.value)}
            </p>
            <p
              className={`mt-2 text-xs ${
                impact.total ? "text-white/55" : "text-[var(--muted)]"
              }`}
            >
              financial units
            </p>
          </article>
        ))}
      </div>

      <div className="mt-4 flex flex-col gap-2 rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
        <p className="text-xs font-semibold uppercase tracking-[0.12em] text-[var(--muted)]">
          Largest measured contributor
        </p>
        <p className="text-sm font-medium text-[var(--ink)]">
          {metricLabels[contributor.metric] || humanize(contributor.metric)} ·{" "}
          <span className={`font-mono tabular-nums ${impactColor(contributor.impact)}`}>
            {formatSignedFinancial(contributor.impact)}
          </span>{" "}
          financial units
        </p>
      </div>
    </section>
  );
}

function SignalsAndAnomalies({ analysis }: { analysis: AnalysisSummaryResponse }) {
  return (
    <section aria-labelledby="signals-title" className="workspace-section">
      <SectionHeading
        eyebrow="Verified monitoring"
        title="Signals and anomalies"
        description="Deterministic business rules and statistical checks are shown separately so their meaning stays clear."
        id="signals-title"
      />

      <div className="grid gap-6 lg:grid-cols-2 lg:gap-8">
        <div>
          <div className="mb-3 flex items-center justify-between gap-4">
            <h3 className="text-sm font-semibold text-[var(--ink)]">Business signals</h3>
            <span className="text-xs text-[var(--muted)]">
              {analysis.signals.length} detected
            </span>
          </div>
          {analysis.signals.length > 0 ? (
            <div className="space-y-3">
              {analysis.signals.map((signal) => (
                <SignalCard key={signal.id} signal={signal} />
              ))}
            </div>
          ) : (
            <EmptyState>
              No deterministic business signals crossed the configured thresholds. Continue
              monitoring as new data arrives.
            </EmptyState>
          )}
        </div>

        <div className="lg:border-l lg:border-[var(--border-soft)] lg:pl-8">
          <div className="mb-3 flex items-center justify-between gap-4">
            <h3 className="text-sm font-semibold text-[var(--ink)]">
              Statistical anomalies
            </h3>
            <span className="text-xs text-[var(--muted)]">
              {analysis.anomalies.length} detected
            </span>
          </div>
          {analysis.anomalies.length > 0 ? (
            <div className="space-y-3">
              {analysis.anomalies.map((anomaly) => (
                <article
                  key={anomaly.id}
                  className="rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-sm font-semibold text-[var(--ink)]">
                      {metricLabels[anomaly.metric] || humanize(anomaly.metric)} movement
                    </p>
                    <SeverityBadge severity={anomaly.severity} />
                  </div>
                  <p className="mt-2 text-sm leading-6 text-[var(--muted-strong)]">
                    {formatAnomalySummary(anomaly)}
                  </p>
                  <div className="mt-3 border-t border-[var(--border-soft)] pt-2.5 text-[11px] leading-5 text-[var(--muted)]">
                    <span className="font-semibold uppercase tracking-[0.08em]">
                      Statistical details
                    </span>
                    <span aria-hidden="true"> · </span>
                    Observed change{" "}
                    <span className="font-mono tabular-nums">
                      {formatAnomalyChange(
                        anomaly.observed_change,
                        anomaly.change_unit,
                      )}
                    </span>
                    <span aria-hidden="true"> · </span>
                    historical median{" "}
                    <span className="font-mono tabular-nums">
                      {formatAnomalyChange(
                        anomaly.historical_median_change,
                        anomaly.change_unit,
                      )}
                    </span>
                    <span aria-hidden="true"> · </span>
                    robust z-score{" "}
                    <span className="font-mono tabular-nums">
                      {formatSignedNumber(anomaly.robust_z)}
                    </span>
                  </div>
                </article>
              ))}
            </div>
          ) : (
            <EmptyState>
              No statistically unusual latest-month movements detected. This does not mean
              the business is risk-free.
            </EmptyState>
          )}
        </div>
      </div>
    </section>
  );
}

function SignalCard({ signal }: { signal: BusinessSignal }) {
  return (
    <article className="rounded-xl border border-[var(--border)] bg-white p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-semibold text-[var(--ink)]">
          {signalTitles[signal.type]}
        </p>
        <SeverityBadge severity={signal.severity} />
      </div>
      <p className="mt-2 text-sm leading-6 text-[var(--muted-strong)]">
        {formatNarrative(signal.statement)}
      </p>
      <p className="mt-3 text-xs text-[var(--muted)]">
        {formatPeriod(signal.comparison_period)} → {formatPeriod(signal.period)}
      </p>
    </article>
  );
}

function SeverityBadge({ severity }: { severity: Severity }) {
  const classes = {
    low: "border-[#d7dfda] bg-[#f3f6f4] text-[#52625c]",
    medium: "border-[#ead7a5] bg-[#fff8e6] text-[#8a6414]",
    high: "border-[#e5b9b5] bg-[#fff0ef] text-[#a33b32]",
  }[severity];

  return (
    <span
      className={`rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] ${classes}`}
    >
      {severity}
    </span>
  );
}

function ForecastOutlook({ analysis }: { analysis: AnalysisSummaryResponse }) {
  const { forecast } = analysis;

  return (
    <section aria-labelledby="forecast-title" className="workspace-section">
      <SectionHeading
        eyebrow="Historical-pattern forecast"
        title="Three-month outlook"
        description="Forecasts are based on historical patterns and are not guarantees."
        id="forecast-title"
      />

      <div className="overflow-x-auto rounded-xl border border-[var(--border)]">
        <table className="w-full min-w-[720px] border-collapse bg-white text-left">
          <thead>
            <tr className="border-b border-[var(--border)] bg-[var(--surface-muted)]">
              <th className="px-5 py-3 text-xs font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                Forecast period
              </th>
              <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                Revenue
              </th>
              <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                Operating profit
              </th>
              <th className="px-5 py-3 text-right text-xs font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
                Operating margin
              </th>
            </tr>
          </thead>
          <tbody>
            {forecast.periods.map((period) => (
              <tr
                key={period.period}
                className="border-b border-[var(--border-soft)] last:border-b-0"
              >
                <td className="px-5 py-5">
                  <p className="text-sm font-semibold text-[var(--ink)]">
                    {formatPeriod(period.period)}
                  </p>
                  <p className="mt-1 text-xs text-[var(--muted)]">Projected month</p>
                </td>
                <td className="px-5 py-5 text-right">
                  <p className="font-mono text-sm font-semibold text-[var(--ink)] tabular-nums">
                    {formatFinancial(period.revenue.value)}
                  </p>
                  <p className="mt-1 text-xs text-[var(--muted)]">financial units</p>
                </td>
                <td className="px-5 py-5 text-right">
                  <p
                    className={`font-mono text-sm font-semibold tabular-nums ${impactColor(period.operating_profit)}`}
                  >
                    {formatFinancial(period.operating_profit)}
                  </p>
                  <p className="mt-1 text-[11px] text-[var(--muted)]">
                    Historical-error range {formatFinancial(period.operating_profit_component_range.low)}–
                    {formatFinancial(period.operating_profit_component_range.high)}
                  </p>
                </td>
                <td className="px-5 py-5 text-right">
                  <p className="font-mono text-sm font-semibold text-[var(--ink)] tabular-nums">
                    {formatPercent(period.operating_margin_pct)}
                  </p>
                  <p className="mt-1 text-xs text-[var(--muted)]">projected margin</p>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <details className="group mt-4 rounded-lg border border-[var(--border)] bg-[var(--surface-muted)]">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-4 px-4 py-3 text-sm font-medium text-[var(--ink)] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus)]">
          Forecast model details
          <span
            aria-hidden="true"
            className="text-lg text-[var(--muted)] transition-transform group-open:rotate-45"
          >
            +
          </span>
        </summary>
        <div className="grid gap-3 border-t border-[var(--border)] p-4 md:grid-cols-3">
          <ModelDetail label="Revenue" diagnostic={forecast.models.revenue} />
          <ModelDetail label="COGS" diagnostic={forecast.models.cogs} />
          <ModelDetail
            label="Operating expenses"
            diagnostic={forecast.models.operating_expenses}
          />
        </div>
        <div className="border-t border-[var(--border)] px-4 py-3 text-xs leading-5 text-[var(--muted)]">
          Ranges reflect observed backtest error around the component forecasts. They are
          not confidence intervals.
        </div>
      </details>
    </section>
  );
}

function ModelDetail({
  label,
  diagnostic,
}: {
  label: string;
  diagnostic: ForecastModelDiagnostics;
}) {
  return (
    <div className="rounded-lg bg-white p-4">
      <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
        {label}
      </p>
      <p className="mt-2 text-sm font-semibold text-[var(--ink)]">
        {modelLabels[diagnostic.selected_model] || humanize(diagnostic.selected_model)}
      </p>
      <p className="mt-2 text-xs leading-5 text-[var(--muted-strong)]">
        Compared across {diagnostic.backtest_points} rolling historical checks.
      </p>
      <p className="mt-1 text-[11px] leading-5 text-[var(--muted)]">
        Technical details · MAE{" "}
        <span className="font-mono tabular-nums">
          {formatFinancial(diagnostic.mae)} units
        </span>
        {diagnostic.normalized_mae_pct !== null && (
          <>
            {" "}· normalized MAE{" "}
            <span className="font-mono tabular-nums">
              {numberFormatter.format(diagnostic.normalized_mae_pct)}%
            </span>
          </>
        )}
      </p>
    </div>
  );
}

function DataNotes({ notes }: { notes: string[] }) {
  const uniqueNotes = [...new Set(notes)];
  return (
    <aside className="rounded-xl border border-[var(--border)] bg-[var(--surface-muted)] p-5">
      <h2 className="text-sm font-semibold text-[var(--ink)]">Data and calculation notes</h2>
      <ul className="mt-3 space-y-2 text-sm leading-6 text-[var(--muted-strong)]">
        {uniqueNotes.map((note) => (
          <li key={note} className="flex gap-2">
            <span aria-hidden="true" className="mt-[0.65rem] h-1 w-1 shrink-0 rounded-full bg-[var(--muted)]" />
            <span>{formatNarrative(note)}</span>
          </li>
        ))}
      </ul>
    </aside>
  );
}

function EmptyState({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-dashed border-[var(--border-strong)] bg-[var(--surface-muted)] px-4 py-5 text-sm leading-6 text-[var(--muted-strong)]">
      {children}
    </div>
  );
}

function SectionHeading({
  eyebrow,
  title,
  description,
  id,
}: {
  eyebrow: string;
  title: string;
  description: string;
  id: string;
}) {
  return (
    <div className="mb-5 flex flex-col gap-2 sm:mb-6 sm:flex-row sm:items-end sm:justify-between sm:gap-8">
      <div>
        <p className="section-eyebrow">{eyebrow}</p>
        <h2
          id={id}
          className="mt-2 text-xl font-semibold tracking-[-0.025em] text-[var(--ink)] sm:text-2xl"
        >
          {title}
        </h2>
      </div>
      <p className="max-w-2xl text-sm leading-6 text-[var(--muted)] sm:text-right">
        {description}
      </p>
    </div>
  );
}

function formatFinancial(value: number): string {
  return numberFormatter.format(value);
}

function formatSignedFinancial(value: number): string {
  if (value > 0) return `+${numberFormatter.format(value)}`;
  if (value < 0) return `−${numberFormatter.format(Math.abs(value))}`;
  return "0";
}

function formatPercent(value: number | null): string {
  return value === null ? "Not defined" : `${numberFormatter.format(value)}%`;
}

function formatPercentChange(change: MetricChange): string {
  if (change.percent_change === null) return "Change not comparable";
  return `${formatSignedNumber(change.percent_change)}%`;
}

function formatAbsoluteChange(change: MetricChange): string {
  if (change.absolute_change === null) return "Change not available";
  return `${formatSignedFinancial(change.absolute_change)} units`;
}

function formatMarginChange(change: MetricChange): string {
  if (change.absolute_change === null) return "Change not defined";
  return `${formatSignedNumber(change.absolute_change)} pp`;
}

function formatSignedNumber(value: number): string {
  if (value > 0) return `+${numberFormatter.format(value)}`;
  if (value < 0) return `−${numberFormatter.format(Math.abs(value))}`;
  return "0";
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

function formatEvidenceValue(item: EvidenceItem): string {
  if (item.value === null) return "Not defined";
  if (item.unit === "financial_units") {
    return `${formatFinancial(item.value)} units`;
  }
  if (item.unit === "percentage_points") {
    return `${formatFinancial(item.value)} pp`;
  }
  return `${formatFinancial(item.value)}%`;
}

function formatAnomalySummary(anomaly: StatisticalAnomaly): string {
  const metric = metricLabels[anomaly.metric] || humanize(anomaly.metric);
  const relationship = anomaly.direction === "increase" ? "above" : "below";

  return `${metric} moved unusually far ${relationship} the recent historical pattern between ${formatPeriod(anomaly.comparison_period)} and ${formatPeriod(anomaly.period)}.`;
}

function formatAnomalyChange(
  value: number,
  unit: StatisticalAnomaly["change_unit"],
): string {
  if (unit === "percent") return `${formatSignedNumber(value)}%`;
  return `${formatSignedFinancial(value)} units`;
}

function formatNarrative(value: string): string {
  const periods: string[] = [];
  const protectedPeriods = value.replace(
    /\b\d{4}-(?:0[1-9]|1[0-2])\b/g,
    (period) => {
      periods.push(period);
      return `__PERIOD_${periods.length - 1}__`;
    },
  );

  const formattedNumbers = protectedPeriods.replace(
    /(?<![\w.])[+-]?\d+(?:\.\d+)?(?![\w.])/g,
    (rawNumber) => {
      const numericValue = Number(rawNumber);
      if (!Number.isFinite(numericValue)) return rawNumber;

      const sign = numericValue < 0 ? "−" : rawNumber.startsWith("+") ? "+" : "";
      return `${sign}${numberFormatter.format(Math.abs(numericValue))}`;
    },
  );

  return formattedNumbers.replace(
    /__PERIOD_(\d+)__/g,
    (_placeholder, index: string) => formatPeriod(periods[Number(index)]),
  );
}

function changeTone(value: number | null): "positive" | "negative" | "neutral" {
  if (value === null || value === 0) return "neutral";
  return value > 0 ? "positive" : "negative";
}

function impactColor(value: number): string {
  if (value > 0) return "text-[var(--positive)]";
  if (value < 0) return "text-[var(--negative)]";
  return "text-[var(--muted-strong)]";
}

function humanize(value: string): string {
  return value
    .toLowerCase()
    .replaceAll("_", " ")
    .replace(/^./, (character) => character.toUpperCase());
}
