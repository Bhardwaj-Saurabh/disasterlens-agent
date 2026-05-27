import { useEffect, useState } from "react";
import { postDecision, type PendingDecision, type Shelter } from "../lib/api";

interface Props {
  decision: PendingDecision;
  shelters: Shelter[];
  onDecided: () => void;
}

export function CandidateCard({ decision, shelters, onDecided }: Props) {
  const [note, setNote] = useState("");
  const [guardianVerified, setGuardianVerified] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Reset the guardian checkbox whenever the focused decision changes — the
  // verifier must consciously re-tick for each minor; never carry the prior
  // check across cases.
  useEffect(() => {
    setGuardianVerified(false);
    setError(null);
    setNote("");
  }, [decision.decision_id]);

  const shelter = shelters.find((s) => s.shelter_id === decision.candidate_shelter);
  const confidencePct = (decision.confidence * 100).toFixed(0);
  const confidenceClass =
    decision.confidence >= 0.9 ? "conf-high" :
    decision.confidence >= 0.75 ? "conf-mid" : "conf-low";

  const isMinor = decision.is_minor === true;
  const consentWithheld = decision.disclosure_consent === false;
  // Approval is blocked if either policy gate is unsatisfied. Rejection /
  // request-more-info are always allowed — the verifier can dismiss the case
  // regardless of the gates.
  const approvalBlocked = consentWithheld || (isMinor && !guardianVerified);

  const submit = async (verdict: "approved" | "rejected") => {
    setBusy(true);
    setError(null);
    try {
      // Only send guardian_verified on approve-of-minor — sending it on a
      // reject would pollute the decision doc with a confirmation that wasn't
      // actually used.
      const guardian = verdict === "approved" && isMinor ? guardianVerified : null;
      await postDecision(decision.decision_id, verdict, note, guardian);
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
        <div className="card-header-badges">
          <span className="badge">{decision.seeker_language.toUpperCase()}</span>
          {isMinor && (
            <span className="badge badge-minor" title="Candidate is under 18 — guardian verification required">
              MINOR{decision.candidate_age != null ? ` · age ${decision.candidate_age}` : ""}
            </span>
          )}
          {consentWithheld && (
            <span className="badge badge-no-consent" title="disclosure_consent=false on the roster record">
              CONSENT WITHHELD
            </span>
          )}
        </div>
        <span className={`confidence ${confidenceClass}`}>{confidencePct}% confidence</span>
      </header>

      <section className="card-body">
        <div className="card-col">
          <h3>Seeker query</h3>
          {decision.seeker_photo_url && (
            <img
              className="photo-thumb"
              src={decision.seeker_photo_url}
              alt="Photo provided by the seeker"
            />
          )}
          <p className="quote" dir={decision.seeker_language === "ar" ? "rtl" : "ltr"}>
            {decision.seeker_query}
          </p>
        </div>
        <div className="card-divider" aria-hidden />
        <div className="card-col">
          <h3>Candidate</h3>
          {decision.candidate_photo_url && (
            <img
              className="photo-thumb"
              src={decision.candidate_photo_url}
              alt="Candidate's shelter-intake photo"
            />
          )}
          <p className="candidate-name" dir="auto">{decision.candidate_name}</p>
          <p className="muted">
            {shelter ? shelter.name : decision.candidate_shelter}{" "}
            <span className="muted-faint">· {decision.candidate_person_id}</span>
          </p>
          <h4>Evidence</h4>
          <p className="evidence">{decision.evidence}</p>
          {decision.photo_match_summary && (
            <p className="evidence-photo">
              <span className="evidence-photo-label">Vision check:</span>{" "}
              {decision.photo_match_summary}
            </p>
          )}
        </div>
      </section>

      {(isMinor || consentWithheld) && (
        <section className="policy-panel">
          {consentWithheld && (
            <p className="policy-blocker">
              <strong>Disclosure consent withheld.</strong> This candidate did
              not agree to be findable through reunification queries. Approval
              is disabled; the agent will close the loop with the seeker and
              keep the standing query active in case consent changes.
            </p>
          )}
          {isMinor && !consentWithheld && (
            <label className="policy-check">
              <input
                type="checkbox"
                checked={guardianVerified}
                onChange={(e) => setGuardianVerified(e.target.checked)}
                disabled={busy}
              />
              <span>
                <strong>Guardian relationship confirmed</strong> for this minor
                (school record, photo ID, or cross-roster confirmation). Required
                before approval — see <em>FEMA/NCMEC Post-Disaster Reunification
                of Children, 2013</em>.
              </span>
            </label>
          )}
        </section>
      )}

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
            disabled={busy || approvalBlocked}
            title={
              consentWithheld
                ? "Approval blocked: candidate did not consent to disclosure"
                : (isMinor && !guardianVerified)
                  ? "Tick the guardian-confirmation checkbox first"
                  : undefined
            }
          >
            {busy ? "…" : "Approve match"}
          </button>
        </div>
        {error && <p className="error">{error}</p>}
      </section>
    </article>
  );
}
