# DisasterLens

> **DisasterLens is an AI agent that reunites families separated by disasters — across languages, name spellings, and shelter rosters — with a human verifier approving every match before it reaches a phone.**

Built for the [Google Cloud Rapid Agent Hackathon](https://googlecloudrapidagenthackathon.devpost.com/) — Elastic track.

![DisasterLens hero — live reunification map of Houston with candidate-match arcs lighting up between shelters](docs/architecture.png)

---

## The Problem

When Hurricane Elena scatters Houston's evacuees across forty shelters, **María** — 68, Spanish-speaking — can't find her grandson Carlos. The Red Cross has a registry. But Carlos was logged as *Carlitos M.* at one shelter, *Carlos Martinez* at another, and *C. Martínez* at a third. María doesn't speak English. She just needs to know where Carlos is.

Family reunification at scale is real work. After Katrina, [NCMEC fielded 34,045 calls and resolved 5,192 missing-children cases](https://www.ncmec.org/ourwork/disasters); the [American Red Cross](https://www.redcross.org/get-help/disaster-relief-and-recovery-services/contact-and-locate-loved-ones.html) operates a registry-and-phone-bank model, the [ICRC Restoring Family Links](https://familylinks.icrc.org/) program operates [Trace the Face](https://tracetheface.familylinks.icrc.org/how-does-it-works/) for cross-border cases, and [NamUs](https://namus.nij.ojp.gov/) covers long-tail missing/unidentified persons in the US. All three rely heavily on manual matching by case workers — typically in English. **DisasterLens is the multilingual matching engine those workflows don't have natively**, intended to slot in alongside them as the analytic layer, not replace them.

### Where DisasterLens fits — and where it hands off

| Scenario | Right tool | DisasterLens role |
|---|---|---|
| Adults across shelter rosters, multiple scripts/languages | **DisasterLens** | Primary |
| Unaccompanied minors (under 18), US disaster | [NCMEC UMR](https://www.ncmec.org/ourwork/disasters) (FEMA-activated) | Surface candidates, hand off — flag minors explicitly in the verifier UI |
| Cross-border / refugee reunification | [ICRC RFL](https://familylinks.icrc.org/) | Out of scope — different consent/legal regime (Geneva Conventions) |
| Unidentified remains / long-tail missing persons | [NamUs](https://namus.nij.ojp.gov/) | Out of scope — needs dental/DNA/biometrics |
| Mass-casualty biometric ID | [UNHCR BIMS](https://www.unhcr.org/blogs/keeping-unhcrs-biometrics-system-up-to-date/) / law-enforcement systems | Out of scope |

## What It Does

1. A Spanish-speaking grandmother describes her missing grandson in her own words.
2. The agent — multilingual by intrinsic design — extracts structured details and searches across four Elasticsearch indices: shelter rosters, missing-person reports, open reunification cases, and social posts.
3. Each name is matched with five compounded strategies: **fuzzy** + **phonetic (double-metaphone)** + **ICU transliteration** + **nickname synonym graph** + **multilingual semantic embedding**.
4. The agent surfaces ranked candidates to a human verifier, each with a confidence score and an evidence chain ("name match exact, age match, school affiliation consistent"), plus two policy gates: **disclosure consent** on the roster record and **minor-protection** (under-18 matches require explicit guardian verification before approval).
5. **Nothing leaves the system without verifier approval.** False matches are dangerous; the verifier gate is the showcase feature, implemented via ADK's long-running tool pattern, with a runtime backstop in [`dispatch_notification`](agent/tools/notify.py) that refuses to send when consent is withheld or guardian verification is missing.
6. On approval, the agent drafts notifications in each party's preferred language and dispatches them.
7. If no match is found, a **standing query** auto-re-fires when new roster entries arrive. If another seeker has already opened a case for the same subject, the agent **deduplicates** rather than spawning a parallel investigation.

## Hero Capability: Non-Roman-Script Name Matching

When a seeker asks about **مُحَمَّد**, the agent transliterates to *Mohammed / Muhammad / Mohamed / Mohd*, searches each variant against phonetic and ICU-folded analyzers, and surfaces a candidate. This is the capability competing submissions will lack.

## Three modalities, one agent

The same Coordinator backs three front doors:

1. **Multilingual seeker chat UI** ([seeker_ui/](seeker_ui/)) — React, RTL-aware, file upload for a photo of the subject. Six languages with locale-detected auto-RTL: English, Spanish, Arabic, Vietnamese, Chinese, French.
2. **Twilio voice gateway** ([voice_gateway/](voice_gateway/)) — a Houston-area phone number that the seeker can call. DTMF language pick → Polly TTS greeting → speech-to-text → agent → spoken reply, with the same verifier gate. SMS dispatch via Twilio's Messaging API when the seeker provides a phone number.
3. **Programmatic API + CLI** ([agent.main](agent/main.py)) — the same `run_query_collect` library function that the chat UI calls.

The verifier UI ([verifier_ui/](verifier_ui/)) sits behind all three and is where every match is approved before any external action.

---

## How We Score on the Four Judging Criteria

| Criterion | How DisasterLens Earns the Mark |
|---|---|
| **Technological Implementation** | Compound Elastic queries spanning four indices and three name analyzers (standard, phonetic double-metaphone, ICU transliteration) plus a nickname `synonym_graph` and multilingual semantic embeddings (E5-multilingual / Jina v3 via Elastic inference). Agent reasoning maps **5–8 Elastic MCP tool calls per chain**. HITL via ADK's canonical long-running tool pattern. Custom Agent Builder skills as the agent's vocabulary. |
| **Design** | Custom React + MapLibre verifier UI with a live reunification map (hero visual), candidate-match queue, side-by-side seeker-vs-candidate comparison cards, an approval modal with explicit **consent / minor-protection gates** (guardian-verification required before approving any under-18 match), and multilingual rendering with RTL support. |
| **Potential Impact** | Reunification is a problem with **named real-world programs** ([ARC](https://www.redcross.org/get-help/disaster-relief-and-recovery-services/contact-and-locate-loved-ones.html), [ICRC RFL](https://familylinks.icrc.org/), [NCMEC UMR](https://www.ncmec.org/ourwork/disasters), [NamUs](https://namus.nij.ojp.gov/)) handling concrete volume (NCMEC: 34,045 calls, 5,192 children reunified after Katrina alone), and **named beneficiaries** (immigrant communities, elderly, mixed-language families, unaccompanied minors). Held-out eval reports **≥0.90 fused-confidence precision on clean rosters and ≥0.85 on dirty rosters** (15% typos / dropped fields), plus **≥0.70 recall on the hero transliteration / nickname subset** — measured impact, not anecdotal. |
| **Quality of the Idea** | Not "chat with your data." A narrow, emotionally resonant, technically hard problem (cross-language fuzzy name matching) that Elasticsearch is uniquely suited to solve. Multilingual by intrinsic mission, not bolted on as a feature. Verifier gate is architecturally meaningful, not a checkbox. |

---

## Architecture

See [docs/PRD.md](docs/PRD.md) for the full specification.

**Stack:**
- **Agent:** Google ADK (Python) + Gemini 2.x on Vertex AI
- **Search:** Elasticsearch 9.x Serverless via Agent Builder MCP
- **Embeddings:** E5-multilingual / Jina v3 via Elastic inference endpoints (not ELSER — ELSER v2 is English-only)
- **Verifier UI:** React + Vite + MapLibre GL JS (renders Mapbox raster tiles via the Styles API when a token is set; falls back to OpenStreetMap otherwise)
- **Hosting:** Google Cloud Run

**Indices:** `shelter_rosters`, `missing_person_reports`, `reunification_cases`, `social_reports` — each with three name analyzers (standard, phonetic, transliterated) plus semantic embeddings.

**Custom Agent Builder skills:** `match_person_across_rosters`, `search_social_mentions`, `create_reunification_case`, `register_standing_query`.

---

## Measured Performance

Held-out 50-case family-pair eval, scored end-to-end:

| Metric | Target |
|---|---|
| Fused-confidence precision @ ≥ 0.75 (clean rosters) | ≥ 0.90 |
| Fused-confidence precision @ ≥ 0.75 (dirty rosters, 15% typos / dropped fields) | ≥ 0.85 |
| Recall on transliterated / nickname subset (hero rules) | ≥ 0.70 |
| Median time-to-first-candidate | ≤ 10 s |
| Languages with at least one matched case | ≥ 5 |

The eval set lives at [`evals/family_pairs.jsonl`](evals/family_pairs.jsonl) and the scoreboard at [`evals/score.py`](evals/score.py). The "dirty rosters" number is the more honest one — real shelter intake produces typos, swapped name order, and missing fields; reporting both anchors the claim against the obvious "your synthetic data was too clean" objection. Reproduce with `uv run python -m data.generate_synthetic --dirty-pct 0.15 && uv run python -m data.ingest_to_elastic --reset && uv run python -m evals.score`.

---

## Demo Video

[3-minute demo](#) — *(link added at submission)*

Skeleton:
- **0:00–0:20** — María, Spanish-speaking, looking for Carlos
- **0:18** — Hero visual: live reunification map, arc lights up between two shelters
- **0:20–1:00** — Seeker flow with 5+ Elastic MCP tool calls visible
- **1:00–1:50** — Verifier gate (HITL) — the approval modal is the focal point
- **1:50–2:20** — Hard case: Arabic-script name (مُحَمَّد) handled live
- **2:20–2:40** — Eval numbers on screen
- **2:40–3:00** — Why it matters + architecture slide

A pre-recorded backup demo is available at `docs/demo-backup.mp4` in case the live URL is cold-started during judging.

---

## Quick Start

```bash
# 1. Provision Elastic Cloud Serverless and capture an API key (data + Agent Builder).
#    Copy .env.example → .env.local and fill in.
uv sync

# 2. Set up Elastic — synonyms set, indices, multilingual inference endpoint.
uv run python -m scripts.setup_inference
uv run python -m scripts.create_indices

# 3. Generate synthetic data + 50-case eval gold set, then bulk-ingest.
uv run python -m data.generate_synthetic                 # add --dirty-pct 0.15 for the dirty pass
uv run python -m data.ingest_to_elastic --reset

# 4. Run the agent (terminal 1) + verifier (terminal 2).
uv run python -m agent.main --demo                       # canned María→Carlos query
uv run python -m agent.verifier_cli --watch              # CLI verifier; or use the UI below

# 5. Verifier UI + Seeker UI + FastAPI proxy (all driven by ONE FastAPI process).
uv run uvicorn verifier_ui.server:app --reload --port 8787  # backend on :8787
cd verifier_ui && npm install && npm run dev              # Vite verifier UI on :5173
cd seeker_ui   && npm install && npm run dev              # Vite seeker chat UI on :5174

# 6. Voice gateway (Twilio webhook target — needs ngrok or Cloud Run public URL).
uv run uvicorn voice_gateway.server:app --reload --port 5001
ngrok http 5001   # then set <ngrok-url>/voice/incoming as the Twilio Voice webhook

# 7. Eval scoreboard — produces the headline numbers above, plus calibration
#    (Brier + ECE) and a bias-by-script audit.
uv run python -m evals.score --csv

# 8. Demo prep — show the analyzer stack firing on the hero match.
uv run python -m evals.explain_match --query "محمد خان"

# 9. Live incident-mode (for the third minute of the demo video).
uv run python -m scripts.incident_stream --period-sec 8 --max-docs 12

# 10. PFIF export — federate a verified case to NCMEC UMR / ICRC RFL.
uv run python -m agent.tools.pfif_export rc_0007 -o /tmp/case.pfif.xml
```

## One-command deploy (Cloud Run)

```bash
GCP_PROJECT_ID=<your-project> ./scripts/deploy.sh all
```

Builds and deploys three units in one go: `verifier-ui` and `voice-gateway` (Cloud Run services with `--min-instances=1` to dodge cold-start during judging), plus `incident-stream` (Cloud Run Job, run on demand for the live-data beat of the demo). The script ends with a five-curl cold-start probe against `/healthz` so you can see whether judging-week latency will be a problem.

---

## Domain References

- American Red Cross — Contact and Locate Loved Ones · https://www.redcross.org/get-help/disaster-relief-and-recovery-services/contact-and-locate-loved-ones.html
- ICRC Restoring Family Links · https://familylinks.icrc.org/ · Trace the Face · https://tracetheface.familylinks.icrc.org/
- NCMEC — Disaster Preparedness and Response · https://www.ncmec.org/ourwork/disasters
- NamUs · https://namus.nij.ojp.gov/
- FEMA / NCMEC / HHS / ARC — *Post-Disaster Reunification of Children: A Nationwide Approach* (2013) · https://www.ready.gov/sites/default/files/2019-06/post_disaster_reunification_of_children.pdf
- UNHCR — Modernizing Registration: PRIMES · https://www.unhcr.org/blogs/modernizing-registration-identity-management-unhcr/
- *(Domain-voice quote / clip / cited paper added during Sprint 3.)*

## License

MIT — see [LICENSE](LICENSE).
