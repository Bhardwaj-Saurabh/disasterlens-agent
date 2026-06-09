import { useEffect, useState } from "react";
import { CandidateCard } from "./components/CandidateCard";
import { Queue } from "./components/Queue";
import { ReunificationMap } from "./components/ReunificationMap";
import { TriageList } from "./components/TriageList";
import { fetchPending, fetchShelters, type PendingDecision, type Shelter } from "./lib/api";

const POLL_INTERVAL_MS = 1500;

type Tab = "queue" | "triage";

export default function App() {
  const [tab, setTab] = useState<Tab>("queue");
  const [decisions, setDecisions] = useState<PendingDecision[]>([]);
  const [shelters, setShelters] = useState<Shelter[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Load shelters once.
  useEffect(() => {
    fetchShelters().then(setShelters).catch((e) => setError(String(e)));
  }, []);

  // Poll pending decisions.
  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await fetchPending();
        if (cancelled) return;
        setDecisions(next);
        setError(null);
        setSelectedId((current) => {
          if (current && next.some((d) => d.decision_id === current)) return current;
          return next[0]?.decision_id ?? null;
        });
      } catch (e) {
        if (!cancelled) setError(String(e));
      }
    };
    tick();
    const id = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const selected = decisions.find((d) => d.decision_id === selectedId) ?? null;

  return (
    <div className="app">
      <header className="app-header">
        <h1>DisasterLens · Verifier</h1>
        <span className="muted">
          {decisions.length} pending · polling every {POLL_INTERVAL_MS / 1000}s
        </span>
      </header>

      {error && <div className="banner-error">{error}</div>}

      <main className="app-main">
        <aside className="sidebar">
          <div className="tabs">
            <button
              className={tab === "queue" ? "tab tab-active" : "tab"}
              onClick={() => setTab("queue")}
            >
              Pending decisions
            </button>
            <button
              className={tab === "triage" ? "tab tab-active" : "tab"}
              onClick={() => setTab("triage")}
            >
              Open cases (triage)
            </button>
          </div>
          {tab === "queue" ? (
            <Queue decisions={decisions} selectedId={selectedId} onSelect={setSelectedId} />
          ) : (
            <TriageList />
          )}
        </aside>

        <section className="center">
          {tab === "queue" && selected ? (
            <CandidateCard
              decision={selected}
              shelters={shelters}
              onDecided={() => setSelectedId(null)}
            />
          ) : tab === "queue" ? (
            <div className="empty-state">
              <h2>No active decision selected</h2>
              <p className="muted">
                When the agent finds a candidate above the confidence threshold,
                a decision appears here for human approval.
              </p>
            </div>
          ) : (
            <div className="empty-state">
              <h2>Coordinator triage</h2>
              <p className="muted">
                Open reunification cases sorted by vulnerability — minor subjects first,
                then by hours waited and absence of any surfaced candidates. The
                standing-query watcher re-fires open cases as new roster docs arrive.
              </p>
            </div>
          )}
        </section>

        <section className="map-pane">
          <ReunificationMap shelters={shelters} focused={selected} />
        </section>
      </main>
    </div>
  );
}
