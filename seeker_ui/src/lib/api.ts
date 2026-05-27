// Seeker UI ↔ FastAPI backend. /api is proxied to :8787 via Vite during dev,
// and served same-origin in production.

export interface SeekerChatReply {
  reply: string;
  n_events: number;
  tool_calls: { name: string; args_preview: Record<string, string> }[];
}

export interface PhotoUploadReply {
  photo_id: string;
  photo_url: string;   // absolute URL the agent can fetch
  bytes: number;
  content_type: string;
}

export async function uploadPhoto(file: File): Promise<PhotoUploadReply> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/api/seeker-photos", { method: "POST", body: fd });
  if (!r.ok) throw new Error(`upload: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function sendSeekerMessage(
  message: string,
  seekerPhotoUrl: string | null,
  sessionId: string | null,
): Promise<SeekerChatReply> {
  const r = await fetch("/api/seeker-chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      seeker_photo_url: seekerPhotoUrl ?? "",
      session_id: sessionId,
    }),
  });
  if (!r.ok) throw new Error(`chat: ${r.status} ${await r.text()}`);
  return r.json();
}
