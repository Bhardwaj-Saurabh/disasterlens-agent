// API client for the FastAPI proxy. The Vite dev server proxies /api → :8787.

export interface PendingDecision {
  _id: string;
  decision_id: string;
  status: string;
  candidate_name: string;
  candidate_shelter: string;
  candidate_person_id: string;
  confidence: number;
  evidence: string;
  seeker_query: string;
  seeker_language: string;
  seeker_location_text?: string;
  seeker_location?: { lat: number; lon: number } | null;
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

export async function postDecision(
  decisionId: string,
  decision: DecisionVerdict,
  verifierNote = ""
): Promise<void> {
  const r = await fetch(`/api/decisions/${decisionId}/decide`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, verifier_note: verifierNote }),
  });
  if (!r.ok) throw new Error(`decide: ${r.status} ${await r.text()}`);
}
