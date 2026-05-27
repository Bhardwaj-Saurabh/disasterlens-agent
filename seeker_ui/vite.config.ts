import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The seeker UI runs on :5174 during dev so the verifier UI (5173) and this
// can run side-by-side for the demo recording. Both proxy /api to the same
// FastAPI process at :8787.
//
// In production both UIs are served from ONE Cloud Run service: the verifier
// at /, the seeker at /seeker/. base="/seeker/" makes the built HTML emit
// `/seeker/assets/...` so the browser fetches the right bundle (otherwise it
// would hit the verifier UI's `/assets/...` mount and 404 on a hash miss).
export default defineConfig({
  base: "/seeker/",
  server: {
    port: 5174,
    proxy: {
      "/api": "http://localhost:8787",
    },
  },
  plugins: [react()],
});
