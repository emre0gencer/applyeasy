import { useCallback, useState } from "react";
import { StatusResponse } from "./api/client";
import { GeneratingStep } from "./components/GeneratingStep";
import { JobDescriptionStep } from "./components/JobDescriptionStep";
import { LandingPage } from "./components/LandingPage";
import { NetworkBackground } from "./components/NetworkBackground";
import { ResultsStep } from "./components/ResultsStep";

type Step = "landing" | "job" | "generating" | "results";

interface AppState {
  step: Step;
  sessionId?: string;
  runId?: string;
  finalStatus?: StatusResponse;
  errorMsg?: string;
  rawText?: string;
  jobDescription?: string;
  includeCoverLetter?: boolean;
}

const WIZARD_STEPS: Partial<Record<Step, number>> = {
  job: 1,
  generating: 2,
  results: 3,
};

export default function App() {
  const [state, setState] = useState<AppState>({ step: "landing" });

  const goToJob = useCallback((sessionId: string, rawText: string) => {
    setState({ step: "job", sessionId, rawText });
  }, []);

  const goToGenerating = useCallback((runId: string, jobDescription: string, includeCoverLetter: boolean) => {
    setState((s) => ({ ...s, step: "generating", runId, jobDescription, includeCoverLetter }));
  }, [])

  const goToResults = useCallback((status: StatusResponse) => {
    setState((s) => ({ ...s, step: "results", finalStatus: status }));
  }, []);

  const handleFailed = useCallback((msg: string) => {
    setState((s) => ({ ...s, step: "results", errorMsg: msg }));
  }, []);

  // Full restart: go back to landing, pre-fill the background textarea
  const restart = useCallback(() => {
    setState((s) => ({ step: "landing", rawText: s.rawText }));
  }, []);

  // Retry after failed generation: session is still valid, go back to job step with JD pre-filled
  const retryFromFailed = useCallback(() => {
    setState((s) => ({ step: "job", sessionId: s.sessionId, rawText: s.rawText, jobDescription: s.jobDescription }));
  }, []);

  const stepNum = WIZARD_STEPS[state.step];

  return (
    <div style={styles.page}>
      <NetworkBackground />
      <div style={styles.content}>
        {state.step !== "landing" && (
          <header style={styles.header}>
            <h1 style={styles.logo} onClick={restart} title="Go to home">
              <span style={styles.logoApply}>Apply</span><span style={styles.logoEasy}>Easy</span>
            </h1>
            {stepNum !== undefined && (
              <span style={styles.stepIndicator}>Step {stepNum} of 3</span>
            )}
          </header>
        )}

        <main style={state.step === "landing" ? undefined : styles.main}>
          {state.step === "landing" && (
            <LandingPage onSubmit={goToJob} initialText={state.rawText} />
          )}
          {state.step === "job" && state.sessionId && (
            <JobDescriptionStep
              sessionId={state.sessionId}
              onBack={restart}
              onNext={goToGenerating}
              initialJd={state.jobDescription}
            />
          )}
          {state.step === "generating" && state.runId && (
            <GeneratingStep
              runId={state.runId}
              onDone={goToResults}
              onFailed={handleFailed}
              includeCoverLetter={state.includeCoverLetter ?? false}
            />
          )}
          {state.step === "results" && state.runId && (
            <>
              {state.errorMsg ? (
                <div style={styles.errorCard}>
                  <h2 style={{ color: "#f1f5f9" }}>Generation Failed</h2>
                  <p style={{ color: "#94a3b8" }}>{state.errorMsg}</p>
                  <div style={styles.errorBtnRow}>
                    <button onClick={retryFromFailed} style={styles.restartBtn}>Try again</button>
                    <button onClick={restart} style={styles.secondaryBtn}>Start over</button>
                  </div>
                </div>
              ) : state.finalStatus ? (
                <ResultsStep
                  runId={state.runId}
                  status={state.finalStatus}
                  onRestart={restart}
                  includeCoverLetter={state.includeCoverLetter ?? false}
                />
              ) : null}
            </>
          )}
        </main>
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background: "transparent",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  content: {
    position: "relative",
    zIndex: 1,
    minHeight: "100vh",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    height: 60,
    padding: "0 40px",
    background: "rgba(2,12,27,0.75)",
    backdropFilter: "blur(12px)",
    borderBottom: "1px solid rgba(255,255,255,0.08)",
    marginBottom: 24,
  },
  logo: {
    fontSize: 20,
    margin: 0,
    letterSpacing: "-0.03em",
    cursor: "pointer",
    userSelect: "none",
    display: "flex",
    alignItems: "baseline",
    gap: 0,
  },
  logoApply: { color: "#f1f5f9", fontWeight: 700 },
  logoEasy: { color: "#60a5fa", fontWeight: 800 },
  stepIndicator: {
    fontSize: 12,
    fontWeight: 600,
    color: "#94a3b8",
    background: "rgba(255,255,255,0.06)",
    border: "1px solid rgba(255,255,255,0.1)",
    padding: "3px 10px",
    borderRadius: 100,
  },
  main: { padding: "0 16px 60px" },
  errorCard: {
    maxWidth: 500,
    margin: "0 auto",
    padding: "32px",
    background: "rgba(2,15,36,0.8)",
    backdropFilter: "blur(16px)",
    borderRadius: 12,
    border: "1px solid rgba(255,255,255,0.1)",
    boxShadow: "0 8px 32px rgba(0,0,0,0.4)",
    textAlign: "center",
  },
  errorBtnRow: {
    display: "flex",
    gap: 12,
    justifyContent: "center",
    marginTop: 20,
  },
  restartBtn: {
    padding: "10px 24px",
    background: "#6366f1",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: 15,
  },
  secondaryBtn: {
    padding: "10px 24px",
    background: "transparent",
    color: "#94a3b8",
    border: "1px solid rgba(255,255,255,0.15)",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: 15,
  },
};
