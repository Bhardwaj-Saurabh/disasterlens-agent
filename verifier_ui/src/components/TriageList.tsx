import { useEffect, useState } from "react";
import { fetchTriage, type TriageCase } from "../lib/api";

const POLL_INTERVAL_MS = 4000;

export function TriageList() {
  const [cases, setCases] = useState<TriageCase[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [minHours, setMinHours] = useState<number>(0);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      try {
        const next = await fetchTriage(minHours);
        if (!cancelled) {
          setCases(next);
          setError(null);
        }
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
  }, [minHours]);

  return (
    <div className="triage">
      <div className="triage-filters">
        <label>
          <span className="muted-faint">Wait time:</span>
          <select
            value={minHours}
            onChange={(e) => setMinHours(Number(e.target.value))}
          >
            <option value={0}>all</option>
            <option value={1}>≥ 1 hour</option>
            <option value={6}>≥ 6 hours</option>
            <option value={24}>≥ 24 hours</option>
          </select>
        </label>
      </div>

      {error && <p className="error">{error}</p>}

      {cases.length === 0 ? (
        <p className="muted">No open cases match this filter.</p>
      ) : (
        <ol className="triage-rows">
          {cases.map((c) => (
            <li key={c.case_id} className="triage-row">
              <header className="triage-row-header">
                <span className="triage-name" dir="auto">
                  {c.subject_name_as_given || c.case_id}
                </span>
                {c.is_minor_subject && (
                  <span className="badge badge-small badge-minor">MINOR</span>
                )}
                {c.standing_query_active && (
                  <span className="badge badge-small triage-standing">STANDING</span>
                )}
              </header>
              <div className="triage-meta">
                <span className="badge badge-small">
                  {c.seeker_language.toUpperCase()}
                </span>
                <span className="muted-faint">
                  {c.subject_age_estimate != null ? `age ${c.subject_age_estimate} · ` : ""}
                  {c.n_candidates} candidate{c.n_candidates === 1 ? "" : "s"} ·{" "}
                  {c.hours_waiting != null ? `${c.hours_waiting}h waiting` : "age unknown"}
                </span>
              </div>
              <div className="triage-score">
                <span className="muted-faint">priority</span>
                <span className="triage-score-num">{c.vulnerability_score}</span>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
