"use client";

import { useEffect, useRef, useState } from "react";

import { AnalysisDashboard } from "@/components/analysis-dashboard";
import {
  checkApiHealth,
  DecisionLensApiError,
  friendlyApiError,
  requestAnalysis,
  requestDecisionBrief,
  type AnalysisSummaryResponse,
  type DecisionBriefResponse,
} from "@/lib/api";

type ApiStatus = "checking" | "online" | "offline";

export function DecisionWorkspace() {
  const [file, setFile] = useState<File | null>(null);
  const [analysis, setAnalysis] = useState<AnalysisSummaryResponse | null>(null);
  const [brief, setBrief] = useState<DecisionBriefResponse | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);
  const [briefError, setBriefError] = useState<string | null>(null);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [briefLoading, setBriefLoading] = useState(false);
  const [dragActive, setDragActive] = useState(false);
  const [apiStatus, setApiStatus] = useState<ApiStatus>("checking");
  const fileInputRef = useRef<HTMLInputElement>(null);
  const requestControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    const timeoutId = window.setTimeout(() => {
      controller.abort();
      if (active) setApiStatus("offline");
    }, 4000);

    checkApiHealth(controller.signal).then((online) => {
      window.clearTimeout(timeoutId);
      if (active) setApiStatus(online ? "online" : "offline");
    });

    return () => {
      active = false;
      window.clearTimeout(timeoutId);
      controller.abort();
    };
  }, []);

  const busy = analysisLoading || briefLoading;
  const isInitialState = !file && !analysis && !analysisLoading;

  function clearResults() {
    setAnalysis(null);
    setBrief(null);
    setAnalysisError(null);
    setBriefError(null);
  }

  function selectFile(nextFile: File | undefined) {
    if (!nextFile) return;

    if (!nextFile.name.toLowerCase().endsWith(".csv")) {
      setAnalysisError("Choose a CSV file and try again.");
      return;
    }

    clearResults();
    setFile(nextFile);
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    selectFile(event.currentTarget.files?.[0]);
    event.currentTarget.value = "";
  }

  function handleDrop(event: React.DragEvent<HTMLLabelElement>) {
    event.preventDefault();
    setDragActive(false);
    if (!busy) selectFile(event.dataTransfer.files?.[0]);
  }

  function resetWorkspace() {
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;
    setFile(null);
    clearResults();
    setAnalysisLoading(false);
    setBriefLoading(false);
    setDragActive(false);
  }

  async function analyzeFile() {
    if (!file) {
      setAnalysisError("Choose a CSV file before starting the analysis.");
      return;
    }

    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    setAnalysisError(null);
    setBriefError(null);
    setAnalysis(null);
    setBrief(null);
    setAnalysisLoading(true);
    setBriefLoading(false);

    try {
      const analysisResponse = await requestAnalysis(file, controller.signal);
      setAnalysis(analysisResponse);
      setApiStatus("online");
      setAnalysisLoading(false);
      setBriefLoading(true);

      try {
        const briefResponse = await requestDecisionBrief(file, controller.signal);
        setBrief(briefResponse);
      } catch (error) {
        if (!isAbortError(error)) {
          setBriefError(
            "The Decision Brief request did not complete. The verified dashboard is still available.",
          );
        }
      } finally {
        setBriefLoading(false);
      }
    } catch (error) {
      if (!isAbortError(error)) {
        setAnalysisError(friendlyApiError(error));
        if (error instanceof DecisionLensApiError && error.status === null) {
          setApiStatus("offline");
        }
      }
    } finally {
      setAnalysisLoading(false);
      requestControllerRef.current = null;
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-[var(--canvas)] text-[var(--ink)]">
      <Header apiStatus={apiStatus} />

      <main
        className={`mx-auto w-full max-w-[1240px] flex-1 px-4 sm:px-6 lg:px-8 ${
          isInitialState
            ? "flex flex-col justify-center py-10 sm:py-12 lg:py-16"
            : "py-7 sm:py-10 lg:py-12"
        }`}
      >
        <div className="mb-7 grid gap-3 sm:mb-9 lg:grid-cols-[minmax(0,1.7fr)_minmax(260px,0.8fr)] lg:items-end lg:gap-12">
          <div>
            <p className="section-eyebrow">Financial analysis workspace</p>
            <h1 className="mt-2 text-3xl font-semibold tracking-[-0.04em] text-[var(--ink)] sm:text-4xl">
              Turn monthly financials into a focused decision view.
            </h1>
          </div>
          <p className="max-w-xl text-sm leading-6 text-[var(--muted)] lg:text-right">
            Metrics are calculated deterministically. The Decision Brief interprets only
            verified evidence.
          </p>
        </div>

        <UploadPanel
          file={file}
          analysis={analysis}
          analysisError={analysisError}
          analysisLoading={analysisLoading}
          briefLoading={briefLoading}
          busy={busy}
          dragActive={dragActive}
          fileInputRef={fileInputRef}
          onAnalyze={analyzeFile}
          onFileChange={handleFileChange}
          onDrop={handleDrop}
          onDragActiveChange={setDragActive}
          onReplace={() => fileInputRef.current?.click()}
          onReset={resetWorkspace}
        />

        {analysis && (
          <div className="mt-5 sm:mt-6">
            <DatasetBar
              analysis={analysis}
              fileName={file?.name || "Uploaded CSV"}
              onReplace={() => fileInputRef.current?.click()}
              onReset={resetWorkspace}
              disabled={busy}
            />
          </div>
        )}

        {analysisLoading && <AnalysisLoadingState />}

        {analysis && (
          <div className="mt-5 sm:mt-6">
            <AnalysisDashboard
              analysis={analysis}
              brief={brief}
              briefError={briefError}
              briefLoading={briefLoading}
            />
          </div>
        )}
      </main>

      <footer className="border-t border-[var(--border)] bg-white">
        <div className="mx-auto flex w-full max-w-[1240px] flex-col gap-2 px-4 py-5 text-xs text-[var(--muted)] sm:flex-row sm:items-center sm:justify-between sm:px-6 lg:px-8">
          <p>DecisionLens AI · Evidence-backed financial decision intelligence</p>
          <p>Decision support only — not professional financial advice.</p>
        </div>
      </footer>
    </div>
  );
}

function Header({ apiStatus }: { apiStatus: ApiStatus }) {
  const status = {
    checking: { label: "Checking analysis API", dot: "bg-[#c99a3b]" },
    online: { label: "Analysis API online", dot: "bg-[var(--positive)]" },
    offline: { label: "Analysis API unavailable", dot: "bg-[var(--negative)]" },
  }[apiStatus];

  return (
    <header className="border-b border-[var(--border)] bg-white">
      <div className="mx-auto flex min-h-[72px] w-full max-w-[1240px] items-center justify-between gap-5 px-4 py-3 sm:px-6 lg:px-8">
        <div className="flex min-w-0 items-center gap-3">
          <div className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--deep-green)] text-white shadow-sm">
            <LensMark />
          </div>
          <div className="min-w-0">
            <p className="truncate text-[15px] font-semibold tracking-[-0.02em] text-[var(--ink)]">
              DecisionLens AI
            </p>
            <p className="hidden truncate text-xs text-[var(--muted)] sm:block">
              Evidence-backed financial decision intelligence
            </p>
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2 rounded-full border border-[var(--border)] bg-[var(--surface-muted)] px-3 py-1.5 text-xs font-medium text-[var(--muted-strong)]">
          <span className={`h-2 w-2 rounded-full ${status.dot}`} aria-hidden="true" />
          <span className="hidden sm:inline">{status.label}</span>
          <span className="sm:hidden">API</span>
        </div>
      </div>
    </header>
  );
}

interface UploadPanelProps {
  file: File | null;
  analysis: AnalysisSummaryResponse | null;
  analysisError: string | null;
  analysisLoading: boolean;
  briefLoading: boolean;
  busy: boolean;
  dragActive: boolean;
  fileInputRef: React.RefObject<HTMLInputElement | null>;
  onAnalyze: () => void;
  onFileChange: (event: React.ChangeEvent<HTMLInputElement>) => void;
  onDrop: (event: React.DragEvent<HTMLLabelElement>) => void;
  onDragActiveChange: (active: boolean) => void;
  onReplace: () => void;
  onReset: () => void;
}

function UploadPanel({
  file,
  analysis,
  analysisError,
  analysisLoading,
  briefLoading,
  busy,
  dragActive,
  fileInputRef,
  onAnalyze,
  onFileChange,
  onDrop,
  onDragActiveChange,
  onReplace,
  onReset,
}: UploadPanelProps) {
  return (
    <section aria-labelledby="upload-title" className="rounded-xl border border-[var(--border)] bg-white shadow-[var(--shadow-subtle)]">
      <div className="grid lg:grid-cols-[0.9fr_1.1fr]">
        <div className="border-b border-[var(--border-soft)] p-5 sm:p-6 lg:border-b-0 lg:border-r lg:p-7">
          <p className="section-eyebrow">Dataset</p>
          <h2 id="upload-title" className="mt-2 text-xl font-semibold tracking-[-0.025em]">
            Upload monthly financials
          </h2>
          <p className="mt-3 text-sm leading-6 text-[var(--muted)]">
            Use a CSV with at least 12 consecutive monthly periods. DecisionLens validates
            the data before calculating any result.
          </p>
          <div className="mt-5">
            <p className="text-xs font-semibold uppercase tracking-[0.1em] text-[var(--muted)]">
              Required columns
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              {["date", "revenue", "cogs", "operating_expenses"].map((column) => (
                <code
                  key={column}
                  className="rounded-md border border-[var(--border)] bg-[var(--surface-muted)] px-2.5 py-1.5 text-xs text-[var(--muted-strong)]"
                >
                  {column}
                </code>
              ))}
            </div>
          </div>
        </div>

        <div className="p-5 sm:p-6 lg:p-7">
          <input
            ref={fileInputRef}
            id="financial-csv"
            className="sr-only"
            type="file"
            accept=".csv,text/csv"
            onChange={onFileChange}
            disabled={busy}
          />

          {!file ? (
            <label
              htmlFor="financial-csv"
              onDragEnter={(event) => {
                event.preventDefault();
                if (!busy) onDragActiveChange(true);
              }}
              onDragOver={(event) => event.preventDefault()}
              onDragLeave={(event) => {
                event.preventDefault();
                onDragActiveChange(false);
              }}
              onDrop={onDrop}
              className={`group flex min-h-44 cursor-pointer flex-col items-center justify-center rounded-lg border border-dashed px-5 py-7 text-center outline-none transition-colors focus-within:border-[var(--focus)] ${
                dragActive
                  ? "border-[var(--accent-strong)] bg-[var(--accent-soft)]"
                  : "border-[var(--border-strong)] bg-[var(--surface-muted)] hover:border-[var(--accent-strong)] hover:bg-[var(--accent-soft)]"
              }`}
            >
              <span className="grid h-10 w-10 place-items-center rounded-lg border border-[var(--border)] bg-white text-[var(--deep-green)] shadow-sm">
                <UploadIcon />
              </span>
              <span className="mt-4 text-sm font-semibold text-[var(--ink)]">
                Choose a CSV or drop it here
              </span>
              <span className="mt-1 text-xs text-[var(--muted)]">
                Monthly data · maximum file size 5 MB
              </span>
            </label>
          ) : (
            <div className="rounded-lg border border-[var(--border)] bg-[var(--surface-muted)] p-4 sm:p-5">
              <div className="flex items-start gap-3">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-lg bg-white text-xs font-bold text-[var(--deep-green)] shadow-sm">
                  CSV
                </span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-semibold text-[var(--ink)]">{file.name}</p>
                  <p className="mt-1 text-xs text-[var(--muted)]">
                    {formatFileSize(file.size)} · ready to validate
                  </p>
                </div>
              </div>

              <div className="mt-5 flex flex-wrap gap-2">
                <button
                  type="button"
                  className="primary-button"
                  onClick={onAnalyze}
                  disabled={busy}
                >
                  {analysisLoading
                    ? "Analyzing financials…"
                    : briefLoading
                      ? "Preparing Decision Brief…"
                      : analysis
                        ? "Run analysis again"
                        : "Analyze financials"}
                </button>
                <button
                  type="button"
                  className="secondary-button"
                  onClick={onReplace}
                  disabled={busy}
                >
                  Replace file
                </button>
                <button
                  type="button"
                  className="text-button"
                  onClick={onReset}
                  disabled={busy}
                >
                  Clear
                </button>
              </div>

              {busy && (
                <div className="mt-4 flex items-center gap-2 text-xs text-[var(--muted-strong)]" role="status">
                  <span className="loading-spinner" aria-hidden="true" />
                  <span>
                    {analysisLoading
                      ? "Validating and calculating verified analytics"
                      : "Matching the decision brief to calculated evidence"}
                  </span>
                </div>
              )}
            </div>
          )}

          {!file && (
            <button
              type="button"
              onClick={onAnalyze}
              className="mt-3 text-sm font-semibold text-[var(--accent-strong)] underline decoration-transparent underline-offset-4 transition hover:decoration-current focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--focus)]"
            >
              Analyze selected file
            </button>
          )}

          {analysisError && (
            <div
              className="mt-4 rounded-lg border border-[#e5b9b5] bg-[#fff4f3] px-4 py-3 text-sm leading-6 text-[#8d3029]"
              role="alert"
            >
              {analysisError}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}

function DatasetBar({
  analysis,
  fileName,
  onReplace,
  onReset,
  disabled,
}: {
  analysis: AnalysisSummaryResponse;
  fileName: string;
  onReplace: () => void;
  onReset: () => void;
  disabled: boolean;
}) {
  return (
    <section
      aria-label="Current dataset"
      className="flex flex-col gap-4 rounded-xl border border-[var(--border)] bg-white px-4 py-4 sm:flex-row sm:items-center sm:justify-between sm:px-5"
    >
      <div className="flex min-w-0 items-center gap-3">
        <span className="grid h-9 w-9 shrink-0 place-items-center rounded-lg bg-[var(--accent-soft)] text-[11px] font-bold text-[var(--deep-green)]">
          CSV
        </span>
        <div className="min-w-0">
          <p className="truncate text-sm font-semibold text-[var(--ink)]">{fileName}</p>
          <p className="mt-1 text-xs text-[var(--muted)]">
            {analysis.series.length} monthly periods · {formatPeriodRange(analysis.period_start, analysis.period_end)}
          </p>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <button type="button" className="secondary-button" onClick={onReplace} disabled={disabled}>
          Replace
        </button>
        <button type="button" className="text-button" onClick={onReset} disabled={disabled}>
          Reset workspace
        </button>
      </div>
    </section>
  );
}

function AnalysisLoadingState() {
  return (
    <section
      className="mt-5 rounded-xl border border-[var(--border)] bg-white p-6 shadow-[var(--shadow-subtle)] sm:mt-6 sm:p-8"
      aria-live="polite"
    >
      <div className="flex items-center gap-3">
        <span className="loading-spinner h-5 w-5" aria-hidden="true" />
        <div>
          <h2 className="text-base font-semibold text-[var(--ink)]">
            Building your verified decision view
          </h2>
          <p className="mt-1 text-sm text-[var(--muted)]">
            Validating the dataset, calculating business metrics, and evaluating the forecast.
          </p>
        </div>
      </div>
      <div className="mt-7 grid gap-3 sm:grid-cols-3">
        {["health", "drivers", "outlook"].map((item) => (
          <div key={item} className="h-24 animate-pulse rounded-lg bg-[var(--surface-muted)]" />
        ))}
      </div>
    </section>
  );
}

function LensMark() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none">
      <circle cx="10" cy="10" r="5.5" stroke="currentColor" strokeWidth="1.8" />
      <path d="M14.2 14.2 19 19" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path d="M7.5 10.2 9.2 12l3.5-4" stroke="#8fd1b9" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function UploadIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5 fill-none">
      <path d="M12 15V4m0 0L8.5 7.5M12 4l3.5 3.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M5 13.5v4A2.5 2.5 0 0 0 7.5 20h9a2.5 2.5 0 0 0 2.5-2.5v-4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} bytes`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatPeriodRange(start: string, end: string): string {
  return `${formatPeriod(start)} to ${formatPeriod(end)}`;
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

function isAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
}
