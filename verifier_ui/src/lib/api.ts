// API client for the FastAPI proxy. The Vite dev server proxies /api → :8787.

export interface PendingDecision {
  _id: string;
  decision_id: string;
  status: string;
  candidate_name: string;
  candidate_shelter: string;
  candidate_person_id: string;
  candidate_age?: number | null;
  candidate_photo_url?: string | null;
  seeker_photo_url?: string | null;
  photo_match_summary?: string | null;
  confidence: number;
  evidence: string;
  seeker_query: string;
  seeker_language: string;
  seeker_location_text?: string;
  seeker_location?: { lat: number; lon: number } | null;
  // Policy gates surfaced from the roster doc by the agent.
  // `disclosure_consent === false` means dispatch is blocked at the server.
  // `is_minor === true` forces a guardian_verified checkbox before approval.
  disclosure_consent?: boolean | null;
  is_minor?: boolean | null;
  guardian_verified?: boolean | null;
  created_at: string;
  decision: string | null;
  verifier_id: string | null;
  verifier_note: string | null;
  decided_at: string | null;
}

export interface Shelter {
  shelter_id: string;
  name: string;
  lat: number;
  lon: number;
}

export type DecisionVerdict = "approved" | "rejected" | "request_more_info";

export async function fetchPending(): Promise<PendingDecision[]> {
  const r = await fetch("/api/pending");
  if (!r.ok) throw new Error(`pending: ${r.status}`);
  return r.json();
}

export async function fetchShelters(): Promise<Shelter[]> {
  const r = await fetch("/api/shelters");
  if (!r.ok) throw new Error(`shelters: ${r.status}`);
  return r.json();
}

export interface TriageCase {
  case_id: string;
  seeker_language: string;
  subject_name_as_given: string;
  subject_age_estimate: number | null;
  is_minor_subject: boolean;
  status: string;
  created_at: string | null;
  hours_waiting: number | null;
  n_candidates: number;
  standing_query_active: boolean;
  vulnerability_score: number;
}

export async function fetchTriage(minHours = 0): Promise<TriageCase[]> {
  const r = await fetch(`/api/triage?min_hours=${minHours}`);
  if (!r.ok) throw new Error(`triage: ${r.status}`);
  return r.json();
}

export async function postDecision(
  decisionId: string,
  decision: DecisionVerdict,
  verifierNote = "",
  guardianVerified: boolean | null = null,
): Promise<void> {
  const body: Record<string, unknown> = { decision, verifier_note: verifierNote };
  if (guardianVerified !== null) body.guardian_verified = guardianVerified;
  const r = await fetch(`/api/decisions/${decisionId}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(`decide: ${r.status} ${await r.text()}`);
}
