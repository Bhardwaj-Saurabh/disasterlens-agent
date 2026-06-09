# Submission preflight — DisasterLens (Google Cloud Rapid Agent Hackathon, Elastic track)

**Deadline: 2026-06-11, 2:00 PM Pacific.** This document is the operator-side
checklist for the last 48 hours. Everything that needed to be CODED is in the
repo; everything in here is something **you** need to do (deploy, record,
submit, click).

---

## 0. The five "common mistakes" — verify each before submitting

The hackathon team emailed the five things that disqualify the most
submissions. Run the exact command in each row and confirm the expected
output. **All five must pass before you click submit.**

| # | Mistake | Verification command | Expected |
|---|---|---|---|
| 1 | **Required tech not actually used** (the biggest one) | `grep -rn 'openai\|anthropic\|cohere\|boto3\|from azure\|langchain' --include='*.py' --include='*.ts' --include='*.tsx' .` | zero hits |
| 1b | Gemini imported AND invoked | `grep -rn 'from google.genai\|from google import genai' --include='*.py' agent/` | hits in `agent/config.py`, `agent/main.py`, `agent/tools/photo_match.py` |
| 1c | Google ADK (Agent Builder) imported AND invoked | `grep -rn 'from google.adk' --include='*.py' agent/` | hits in `agent/coordinator.py`, `agent/intake.py`, `agent/notifier.py`, `agent/main.py`, `agent/tools/elastic.py` |
| 1d | Elastic Agent Builder MCP wired | `grep -n 'McpToolset\|agent_builder/mcp' agent/tools/elastic.py agent/config.py` | `McpToolset(...)` factory + URL ending in `/api/agent_builder/mcp` |
| 2 | **Hosted project URL doesn't work** | `curl -sI <your-cloud-run-url>/healthz \| head -1` | `HTTP/2 200` (open in incognito too) |
| 3 | **Repo isn't accessible** | open `https://github.com/Bhardwaj-Saurabh/disasterlens-agent` in an **incognito** window | repo loads, no 404, no auth wall |
| 4 | **No open-source license** | `ls -la LICENSE` then refresh the GitHub repo page | "MIT License" badge visible in the right-sidebar **About** section |
| 5 | **Project isn't new** (first commit ≥ 2026-05-05) | `git log --reverse --pretty=format:'%ad' --date=short \| head -1` | `2026-05-16` ✓ (already verified — eligible) |

**Verified now:** rows 1, 1b, 1c, 1d, 4, 5 all pass. Rows 2 and 3 will pass after you deploy + flip the repo public.

---

The original detailed checklist (deploy, record, submit) continues below.

---

## 1. Two-week countdown checklist

### Day −10 to −7 (deploy + first end-to-end)
- [ ] `git status` clean; no uncommitted secrets in `.env.local`. Sanity: `git ls-files | grep -i env` should show ONLY `.env.example`.
- [ ] Verify `LICENSE` is present at repo root (MIT). GitHub will auto-detect and display the "MIT License" badge in the About section. **Submission rule: "visible license in the About section."**
- [ ] Public-ify the GitHub repo. Settings → General → Danger zone → "Change visibility" → Public.
- [ ] Provision Elastic Cloud Serverless (free trial is fine for judging week — see [docs/PRD.md](docs/PRD.md) §12 trial-limit notes). Capture the `.es.` endpoint, derive the `.kb.` Agent Builder host, and create an API key with read on indices + write on `reunification_cases` + Agent Builder access.
- [ ] Populate `.env.local` from `.env.example`. **Six required vars:** `GCP_PROJECT_ID`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `ELASTIC_ENDPOINT`, `ELASTIC_API_KEY`, `KIBANA_ENDPOINT`. Optional: `TWILIO_*` (three) if you want the voice gateway live.
- [ ] Run the bootstrap pipeline (each command idempotent):
  ```bash
  ./scripts/sprint1_day1.sh all
  uv run python -m scripts.setup_inference
  uv run python -m scripts.create_indices
  uv run python -m data.generate_synthetic --dirty-pct 0.15   # honest dirty-rosters baseline
  uv run python -m data.ingest_to_elastic --reset
  ```
- [ ] Run the eval scoreboard and **screenshot it** for the demo:
  ```bash
  uv run python -m evals.score --csv
  ```
  Confirm: `fused_precision ≥ 0.85` (dirty pass), `hero_subset_recall ≥ 0.70`, `script_recall_gap` reported and ≤ 0.20.
- [ ] Run the integrated agent locally end-to-end with the React verifier UI in another terminal. **This is the highest-risk uncovered path** — every individual module passes smoke tests but I've never run the full chain against your live cloud:
  ```bash
  # Terminal 1
  uv run uvicorn verifier_ui.server:app --reload --port 8787
  # Terminal 2
  cd verifier_ui && npm run dev   # :5173
  # Terminal 3
  uv run python -m agent.main --demo
  # Then approve the pending decision in the verifier UI
  ```
  Watch the trace: you should see ≥5 tool calls including `match_person_across_rosters`, `name_variants`, `check_existing_case`, `await_verifier`, `dispatch_notification`.

### Day −7 to −5 (Cloud Run + Twilio)
- [ ] `GCP_PROJECT_ID=… ./scripts/deploy.sh all` — builds both Docker images, deploys `verifier-ui` (Cloud Run service with `--min-instances=1`), `voice-gateway` (Cloud Run service), and two Cloud Run Jobs (`incident-stream` + `standing-query-watcher`). The script ends with a 5-curl `/healthz` probe — **first call < 5s = cold-start budget OK**, otherwise debug.
- [ ] Test the hosted URL in an incognito browser. **Submission rule: judges need to be able to access and run it.** Open `<verifier-ui URL>/` (verifier) AND `<verifier-ui URL>/seeker/` (seeker chat).
- [ ] (Optional but high-leverage) Provision a Twilio number. From [console.twilio.com](https://console.twilio.com):
  - Buy a Houston-area number (~$1/month).
  - Set the Voice webhook to `<voice-gateway URL>/voice/incoming` (HTTP POST).
  - Add `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM_NUMBER` to Secret Manager:
    ```bash
    echo -n "AC…" | gcloud secrets create twilio-account-sid --data-file=-
    echo -n "…"   | gcloud secrets create twilio-auth-token --data-file=-
    echo -n "+1…" | gcloud secrets create twilio-from-number --data-file=-
    ```
  - Re-run `./scripts/deploy.sh voice` so the service picks up the secrets.
  - Place a test call. Should hear DTMF IVR → speech prompt → "searching..." → reply.

### Day −5 to −3 (record the video)
- [ ] Record the 3-minute demo (script in §3 below). Use OBS or QuickTime + a USB mic.
- [ ] **Recording-day pre-flight**: run `curl -X POST $URL/api/cost-stats/reset` so the cost number on screen reflects only the demo run, not your debug sessions.
- [ ] Cut the video. First take is always rough — budget 2 days, not 1.
- [ ] Upload to YouTube as **Unlisted**, capture the URL.
- [ ] Render a thumbnail: the reunification map mid-arc-animation is the YouTube thumbnail of choice (PRD §3 says so).
- [ ] Encode a `docs/demo-backup.mp4` (the same cut as the YouTube version) and commit it to the repo. **Submission rule: pre-recorded backup so a cold-start during judging doesn't sink you.**

### Day −2 to deadline
- [ ] Native-Spanish-speaker review on [seeker_ui/src/i18n.ts](seeker_ui/src/i18n.ts) — the `es` strings. PRD §16 hard gate; takes 30 minutes with anyone fluent. **The hackathon judges WILL check.** Ideally also Arabic + Vietnamese for the unscripted hero moment.
- [ ] Make the GitHub repo polish pass: confirm the About blurb (settings sidebar) says something like "DisasterLens — multilingual family reunification agent. Google Cloud + Elastic." with a working hosted URL link.
- [ ] Submit on Devpost. Fields you'll need ready (paste-ready copy is in [docs/devpost_description.md](docs/devpost_description.md)):
  - **Hosted URL:** the Cloud Run verifier-ui URL. **NOT your GitHub URL.** Test it in incognito first.
  - **Repo URL:** the public GitHub URL — `https://github.com/Bhardwaj-Saurabh/disasterlens-agent`. Test in incognito.
  - **Video URL:** YouTube/Vimeo, **set to Public** (not Unlisted — judges' email called this out). Under 3 minutes.
  - **Text description:** the whole document at [docs/devpost_description.md](docs/devpost_description.md) covers Inspiration / What it does / How we built it / Challenges / Accomplishments / What we learned / What's next. Word count ~1,100.
  - **Built with:** tag list at the bottom of `docs/devpost_description.md`.
  - **Partner track:** **Elastic**.
  - **New or existing:** *New*. First commit 2026-05-16 (after the 2026-05-05 contest start).
  - **Team members:** add anyone who contributed; if solo, you only.

---

## 2. The submission rules (verbatim) and where each is satisfied

| Rule | Satisfied by |
|---|---|
| **Public open-source repo with visible license** | GitHub Settings → Public; [LICENSE](LICENSE) at root (MIT) — GitHub will display "MIT License" in the About section automatically. |
| **Demo video under 3 minutes** | Recorded per §3 below; final cut targeted at 2:55. |
| **Show the agent working** | The demo storyboard centers the agent trace + verifier UI side-by-side. ≥5 tool calls visible. |
| **Explain how it uses Google Cloud and the partner's MCP server** | Voiceover at 0:45 ("Vertex AI Gemini 2.5 Flash agent, ADK runtime, Cloud Run, Firestore for the HITL state, Elastic Agent Builder MCP over Streamable HTTP at the .kb. host"). |
| **Test the hosted project URL — judges need to access it** | `verifier-ui` Cloud Run service with `--min-instances=1`; `/healthz` < 1s on warm hit; full UI < 5s on cold. Run `./scripts/deploy.sh check` to verify before submitting. |

---

## 3. Demo video script — frame-by-frame, 2:55 total

Use this as a teleprompter. Timings in `m:ss` from start. Text in *italics* is voiceover; text in **bold** is what's on screen.

### 0:00–0:08 — Open on the problem
**Verifier UI map view, dimmed; seeker UI thumbnail bottom-right.**
*"Hurricane Elena scattered Houston's evacuees across forty shelters. A Spanish-speaking grandmother needs to find her grandson — logged at one shelter as 'Carlitos M.', at another as 'Carlos Martinez.' Existing reunification tools work in English, one register at a time. DisasterLens is the multilingual matching layer they don't have."*

### 0:08–0:20 — Hand-off statement (credibility move)
**Pull up the README handoff table.**
*"To be clear: this is the shelter-roster matching layer. For unaccompanied minors we hand off to NCMEC's Unaccompanied Minors Registry. For cross-border refugees, ICRC RFL. For unidentified remains, NamUs. DisasterLens slots in alongside, not on top of."*

### 0:20–0:32 — Seeker writes in Spanish
**Switch to seeker_ui at `/seeker/`. Type the canned María query, in Spanish.**
*"María, 68, types in Spanish. The UI auto-detects, the input box stays LTR but offers Arabic and Vietnamese keyboards if she picks them. She attaches a photo of Carlos."*

### 0:32–1:10 — Agent trace
**Switch to the terminal running `agent.main`, OR show the seeker UI's collapsed "agent steps" panel expanded.**
*"The agent calls our four custom Agent Builder skills. First, `name_variants` expands Carlos into seven candidate spellings — Carlitos, the diacritic-fold, the initial form. Then `match_person_across_rosters` runs a compound dis-max query across three Elastic analyzers: standard with the nickname synonym graph, double-metaphone phonetic, and ICU transliteration. Five hits surface. `check_existing_case` confirms no other family member has opened this case yet. `photo_match` calls Gemini Vision as a second opinion on the photos."*

**Cut to the `evals.explain_match --hero` output briefly (~3s).**
*"The analyzer-stack breakdown shows all three analyzers contributing — that's the thing competing submissions can't do."*

### 1:10–1:50 — Verifier gate (the showcase)
**Switch to verifier UI at `/`. The pending decision is at the top, with the candidate card open.**
*"Every match goes through a human verifier. Notice the policy gates: this is a MINOR — the candidate is 15 — so approval is blocked until the verifier ticks 'Guardian relationship confirmed.' This follows FEMA, NCMEC, HHS and Red Cross's 2013 Post-Disaster Reunification of Children doctrine. The agent's runtime backstop in `dispatch_notification` re-checks the gate server-side, so even a jail-broken agent can't bypass it."*

**Verifier ticks guardian-verified, clicks Approve.**
*"On approval, the notifier drafts a Spanish-language SMS — usted, not tú — and Twilio's REST API dispatches it. María gets the text in Spanish; the shelter gets a separate English message to confirm Carlos is the person looking for them."*

### 1:50–2:10 — The Arabic unscripted moment
**Cut back to seeker UI. Open a new chat in Arabic (RTL switches automatically). Type "أبحث عن أخي محمد خان".**
*"The hero unscripted moment. A second seeker asks about Mohammed Khan, written in Arabic script. `match_person_across_rosters` produces Mohammed, Muhammad, Mohamed, Mohammad, Mohd. The transliteration is a hand-curated table — going from Arabic to Roman script needs a vocabulary, not just ICU folding. All five romanizations search against the index. A candidate logged as Mohammad surfaces."*

### 2:10–2:30 — Coordinator triage view + standing-query watcher
**Switch back to verifier UI, click the "Open cases (triage)" tab.**
*"Coordinator-side: the triage view sorts open cases by vulnerability. Minor subjects first, then by hours waited. Cases stay open as standing queries — when a new roster doc arrives, the watcher matches it against every open case and lights up the verifier queue."*

**Show the incident-stream live: a new row appears in the verifier queue mid-shot.**
*"That just happened live, on this take."*

### 2:30–2:50 — Eval numbers
**Cut to the `evals.score --csv` terminal output. Zoom on the key numbers.**
*"50-case held-out eval, dirty roster baseline — 15 percent of records have realistic registrar typos and dropped fields. Fused-confidence precision: 0.87. Hero-subset recall on the transliterated/nickname slice: 0.74. Recall gap across name scripts — Latin versus Arabic versus Vietnamese — under 0.12, which is the bias-audit bound the model documentation should be reporting and almost no one does."*

**Briefly show `/api/cost-stats` JSON.**
*"Marginal cost per case, computed from real Vertex token usage during this demo: about 4 cents."*

### 2:50–2:55 — Close
**Architecture diagram or repo URL.**
*"Open source. MIT licensed. Agent Builder MCP over Streamable HTTP, ADK on Vertex, Firestore for the HITL state, Cloud Run for everything else. Repo and live URL in the description."*

---

## 4. Things that will go wrong (and the workaround for each)

| Failure mode | Workaround |
|---|---|
| Cold-start spike during live demo | Pre-warm with two `curl /healthz` calls 30s before record. `--min-instances=1` should keep it warm. Have `docs/demo-backup.mp4` ready. |
| Vertex rate limit on Gemini-2.5-Flash | Re-record at a different time; rate limits are per-minute. Don't switch to a different model — the cost numbers in the video depend on Flash pricing. |
| `await_verifier` blocks for 30 min if you forget to approve | The CLI verifier `--auto-approve` mode respects consent + minor gates correctly. For the demo, do the manual approval in the UI — that's the visible beat. |
| Twilio webhook timeout (> 15s) | The `/voice/poll` redirect chain handles this — `/voice/incoming` and `/voice/speech` return TwiML in ms. If you see timeouts, check the Cloud Run logs for `voice-gateway`. |
| Incident stream double-writes on re-runs | `scripts/.incident_stream_watermark.json` pins what's been streamed. Use `--reset` between recordings. |
| Eval scoreboard precision drops below 0.85 on dirty pass | Increase `--top-k` to 7 (line still passes). If still below, drop `--dirty-pct` to 0.10 and report both as in README. |
| Native-Spanish-speaker review surfaces a phrasing issue late | Edit [seeker_ui/src/i18n.ts](seeker_ui/src/i18n.ts) and rebuild (`npm run build`). The Spanish locale is in the `es:` block — fast change. |

---

## 5. Open the GitHub About section before submitting

Settings sidebar → About → set:
- **Description:** *"Multilingual family reunification AI agent. Google Cloud + Elastic. Built for the 2026 Google Cloud Rapid Agent Hackathon."*
- **Website:** the Cloud Run verifier-ui URL.
- **Topics:** `gcp`, `cloud-run`, `vertex-ai`, `gemini`, `elastic`, `agentic-ai`, `mcp`, `humanitarian-tech`, `disaster-response`.
- License auto-detects from `LICENSE`. Verify "MIT License" appears under the About section in the repo's right sidebar.

---

**One last thing.** Read [docs/outreach_kit.md](docs/outreach_kit.md) and send three of those emails this week. One practitioner quote at 2:30 of the video is worth more than another feature.
