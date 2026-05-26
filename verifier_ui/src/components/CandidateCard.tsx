import { useState } from "react";
import { postDecision, type PendingDecision, type Shelter } from "../lib/api";

interface Props {
  decision: PendingDecision;
  shelters: Shelter[];
  onDecided: () => void;
}

export function CandidateCard({ decision, shelters, onDecided }: Props) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const shelter = shelters.find((s) => s.shelter_id === decision.candidate_shelter);
  const confidencePct = (decision.confidence * 100).toFixed(0);
  const confidenceClass =
    decision.confidence >= 0.9 ? "conf-high" :
    decision.confidence >= 0.75 ? "conf-mid" : "conf-low";

  const submit = async (verdict: "approved" | "rejected") => {
    setBusy(true);
    setError(null);
    try {
      await postDecision(decision.decision_id, verdict, note);
      onDecided();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <article className="card">
      <header className="card-header">
        <span className="badge">{decision.seeker_language.toUpperCase()}</span>
        <span className={`confidence ${confidenceClass}`}>{confidencePct}% confidence</span>
      </header>

      <section className="card-body">
        <div className="card-col">
          <h3>Seeker query</h3>
          <p className="quote" dir={decision.seeker_language === "ar" ? "rtl" : "ltr"}>
            {decision.seeker_query}
          </p>
        </div>
        <div className="card-divider" aria-hidden />
        <div className="card-col">
          <h3>Candidate</h3>
          <p className="candidate-name" dir="auto">{decision.candidate_name}</p>
          <p className="muted">
            {shelter ? shelter.name : decision.candidate_shelter}{" "}
            <span className="muted-faint">· {decision.candidate_person_id}</span>
          </p>
          <h4>Evidence</h4>
          <p className="evidence">{decision.evidence}</p>
        </div>
      </section>

      <section className="card-actions">
        <input
          className="note"
          type="text"
          placeholder="Verifier note (optional)"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          disabled={busy}
        />
        <div className="action-row">
          <button
            className="btn btn-reject"
            onClick={() => submit("rejected")}
            disabled={busy}
          >
            Reject
          </button>
          <button
            className="btn btn-approve"
            onClick={() => submit("approved")}
            disabled={busy}
          >
            {busy ? "…" : "Approve match"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </section>
    </article>
  );
}
