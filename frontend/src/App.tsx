import { useCallback, useState } from "react";
import { StatusResponse } from "./api/client";
import { GeneratingStep } from "./components/GeneratingStep";
import { JobDescriptionStep } from "./components/JobDescriptionStep";
import { ProfileStep } from "./components/ProfileStep";
import { ResultsStep } from "./components/ResultsStep";

type Step = "profile" | "job" | "generating" | "results";

interface AppState {
  step: Step;
  sessionId?: string;
  runId?: string;
  finalStatus?: StatusResponse;
  errorMsg?: string;
}

const STEP_NUMBERS: Record<Step, number> = {
  profile: 1,
  job: 2,
  generating: 3,
  results: 4,
};

export default function App() {
  const [state, setState] = useState<AppState>({ step: "profile" });

  const goToJob = useCallback((sessionId: string) => {
    setState({ step: "job", sessionId });
  }, []);

  const goToGenerating = useCallback((runId: string) => {
    setState((s) => ({ ...s, step: "generating", runId }));
  }, []);

  const goToResults = useCallback((status: StatusResponse) => {
    setState((s) => ({ ...s, step: "results", finalStatus: status }));
  }, []);

  const handleFailed = useCallback((msg: string) => {
    setState((s) => ({ ...s, step: "results", errorMsg: msg }));
  }, []);

  const restart = useCallback(() => {
    setState({ step: "profile" });
  }, []);

  return (
    <div style={styles.page}>
      <header style={styles.header}>
        <h1 style={styles.logo}>Resume Tailor</h1>
        <span style={styles.stepIndicator}>Step {STEP_NUMBERS[state.step]} of 4</span>
      </header>

      <main style={styles.main}>
        {state.step === "profile" && (
          <ProfileStep onNext={goToJob} />
        )}
        {state.step === "job" && state.sessionId && (
          <JobDescriptionStep
            sessionId={state.sessionId}
            onBack={() => setState({ step: "profile" })}
            onNext={goToGenerating}
          />
        )}
        {state.step === "generating" && state.runId && (
          <GeneratingStep
            runId={state.runId}
            onDone={goToResults}
            onFailed={handleFailed}
          />
        )}
        {state.step === "results" && state.runId && (
          <>
            {state.errorMsg ? (
              <div style={styles.errorCard}>
                <h2>Generation Failed</h2>
                <p>{state.errorMsg}</p>
                <button onClick={restart} style={styles.restartBtn}>Try again</button>
              </div>
            ) : state.finalStatus ? (
              <ResultsStep
                runId={state.runId}
                status={state.finalStatus}
                onRestart={restart}
              />
            ) : null}
          </>
        )}
      </main>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    background: "#f4f4f5",
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
  },
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    padding: "16px 32px",
    background: "#fff",
    borderBottom: "1px solid #e5e5e5",
    marginBottom: 32,
  },
  logo: { fontSize: 20, fontWeight: 700, margin: 0 },
  stepIndicator: { fontSize: 13, color: "#888" },
  main: { padding: "0 16px 60px" },
  errorCard: {
    maxWidth: 500,
    margin: "0 auto",
    padding: "32px",
    background: "#fff",
    borderRadius: 8,
    boxShadow: "0 2px 12px rgba(0,0,0,0.08)",
    textAlign: "center",
  },
  restartBtn: {
    marginTop: 16,
    padding: "10px 24px",
    background: "#1a1a1a",
    color: "#fff",
    border: "none",
    borderRadius: 6,
    cursor: "pointer",
    fontSize: 15,
  },
};
