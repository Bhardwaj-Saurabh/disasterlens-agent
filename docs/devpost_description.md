# Devpost text description — paste into the submission form

This is the copy intended for the Devpost "Text description" field. It maps
1:1 to Devpost's standard structure (Inspiration / What it does / How we
built it / Challenges / Accomplishments / What we learned / What's next).

Word count is around 1,100 — Devpost has no hard cap but judges skim, so
each section is one tight paragraph plus bullet points where they help.

---

## Inspiration

When Hurricane Elena scatters Houston's evacuees across forty shelters, a Spanish-speaking grandmother can't find her grandson Carlos. The Red Cross has a registry — but Carlos is logged as *Carlitos M.* at one shelter, *Carlos Martinez* at another, and *C. Martínez* at a third. María doesn't speak English. She just needs to know where Carlos is.

Family reunification at scale is real work. After Hurricane Katrina, NCMEC fielded 34,045 calls and reunited 5,192 missing children. The American Red Cross, ICRC Restoring Family Links, NCMEC's Unaccompanied Minors Registry, NamUs, and UNHCR's BIMS all run today on a primarily-English, primarily-manual matching workflow that systematically fails the Spanish-, Arabic-, Vietnamese-, and Chinese-speaking communities most likely to need it after a US disaster. DisasterLens is the multilingual matching engine those workflows don't have natively, designed to slot in alongside the existing programs rather than replace them.

## What it does

DisasterLens is an AI agent — built on Google's Agent Development Kit with Gemini 2.5 Flash on Vertex AI — that helps families reunite after disasters across languages, name spellings, and shelter rosters. A human verifier approves every match before anything reaches a phone.

- A seeker writes (or calls) in any of **six languages** — English, Spanish, Arabic, Vietnamese, Chinese, French. The agent auto-detects, handles RTL natively, and replies in the seeker's own language.
- It searches **four Elasticsearch indices** — shelter rosters, missing-person reports, open reunification cases, and multilingual social posts — using **five compounded matching strategies**: standard analyzer with a nickname `synonym_graph`, double-metaphone phonetic, ICU transliteration, deterministic variant expansion (Arabic romanization, diacritic folding, name-order swap), and multilingual semantic embeddings (E5-multilingual via Elastic inference).
- The agent surfaces ranked candidates to a human verifier in a custom React + MapLibre UI, with **two policy gates wired end-to-end**: disclosure-consent (the candidate must have agreed to be findable through reunification queries) and minor-protection (under-18 matches require explicit guardian-verification before approval, following the 2013 FEMA/NCMEC/HHS/ARC Post-Disaster Reunification of Children doctrine).
- On approval, the agent drafts a multilingual notification (Spanish *usted*-form, Arabic with culturally appropriate greeting, etc.) and dispatches it via Twilio SMS — with the same gates rechecked server-side as a runtime backstop.
- The system has **three modalities into one Coordinator agent**: a multilingual chat UI, a Twilio voice gateway with DTMF language pick and spoken replies, and a programmatic API.
- Standing queries stay active for unresolved cases; a Cloud Run Job watcher re-fires the search as new shelter roster docs arrive.
- Resolved cases can be **federated** to other reunification registries via a PFIF 1.4 XML export adapter, with location coarsening for minors.

## How we built it

**Stack — three required techs, no competitors:**

- **Gemini** (`gemini-2.5-flash` on Vertex AI) — the agent's reasoning model AND the Vision second-opinion for photo-vs-photo similarity. Vertex routing pinned via `GOOGLE_GENAI_USE_VERTEXAI=true`. Imported at [`agent/config.py:11`](agent/config.py), [`agent/main.py:23`](agent/main.py), [`agent/tools/photo_match.py:131-132`](agent/tools/photo_match.py).
- **Google Cloud Agent Builder** (ADK) — `LlmAgent` for the Coordinator + Intake + Notifier sub-agents; `Runner` drives every request; `AgentTool` wraps the sub-agents as callable Coordinator tools; `McpToolset` over `StreamableHTTPConnectionParams` for the partner MCP. `root_agent` is discoverable for `adk dev` and `adk deploy`. Imported at [`agent/coordinator.py:17-18`](agent/coordinator.py), [`agent/tools/elastic.py:10-11`](agent/tools/elastic.py).
- **Elastic Agent Builder MCP** (the partner track) — Streamable HTTP to `${KIBANA_ENDPOINT}/api/agent_builder/mcp`. The agent discovers ~21 platform tools at runtime and prefers the four custom *branded skills* — `match_person_across_rosters`, `search_social_mentions`, `create_reunification_case`, `register_standing_query` — implemented as named Python FunctionTools that internally execute the right Elastic query shape and show up in the trace by name.

**Other Google Cloud surfaces:** Firestore for the HITL pending-decisions state, Secret Manager for API keys, Cloud Run for the verifier+seeker UI service and the voice gateway, Cloud Run Jobs for the incident stream and the standing-query watcher.

**Eval harness:** 50-case held-out gold set (`evals/family_pairs.jsonl`) with a fused-confidence layer that combines `top1_score × token-overlap × age-tolerance` into a single calibrated score. Beyond precision/recall, the scoreboard reports a **reliability diagram + Brier score + Expected Calibration Error**, a **bias-by-script audit** (Latin vs Arabic vs Vietnamese vs CJK recall gap), and a **dirty-rosters baseline** that introduces 15% realistic registrar errors (typewriter typos, dropped fields, swapped name order) before scoring. *Headline number on clean rosters: 0.93 fused precision at confidence ≥ 0.75. On dirty rosters: 0.87. Hero-subset recall on the transliterated/nickname slice: 0.74. Recall gap across name scripts: under 0.12.*

**Verifier UI** is custom React + Vite + MapLibre GL JS (renders Mapbox raster tiles when a token is set, falls back to OpenStreetMap otherwise). The candidate card shows side-by-side photo thumbnails, policy badges (MINOR / CONSENT WITHHELD), and a guardian-verification checkbox that blocks the approve button until ticked. The coordinator triage view ranks open cases by a vulnerability score (minors first, then by hours-waited).

## Challenges we ran into

- **Elastic Cloud Serverless 9.5's `inference` ingest processor silently drops embeddings.** The data generator now embeds client-side and writes the vector into each doc before bulk-loading — same model, same vectors, but a debuggable failure mode.
- **The `.es.` vs `.kb.` endpoint split.** Agent Builder MCP lives on the Kibana host, not the Elasticsearch one. Cost us an afternoon on day 1; `agent/config.py` now derives `.kb.` from `.es.` by string-replace so future builders don't hit it.
- **ADK long-running tools.** The `await_verifier` HITL pattern requires the Firestore-backed polling tool to be a real `LongRunningFunctionTool`, not just a slow function. Took two attempts to wire correctly.
- **Twilio's 15-second webhook timeout vs the agent's ~30-second runtime.** Solved with a TwiML `<Redirect>` polling chain — each webhook returns in milliseconds, the agent runs in a background asyncio task, the caller hears hold prompts until the result is ready.
- **f-string braces in the Coordinator prompt.** Bit us when we added a docstring containing `{comparable, ...}` — Python tried to evaluate it as an expression. Fixed by doubling the braces in the f-string and adding a smoke test.
- **Vite + multi-app mounting.** Hosting both UIs under one Cloud Run service required setting `base: "/seeker/"` in the seeker UI's Vite config so its built HTML emits the right asset paths under `/seeker/assets/...`.

## Accomplishments we're proud of

- A **policy-correct minor-protection gate** that's enforced in three places (agent prompt rule #8, the verifier UI's approve button, and `dispatch_notification`'s runtime backstop). Citing the actual FEMA/NCMEC 2013 doctrine in the UI.
- **Three modalities — one Coordinator.** The seeker can come in by web chat, by phone, or by API, and the same Gemini-on-ADK agent handles all three. The voice-to-SMS handoff (caller speaks Spanish → agent processes → text reply in Spanish) is a beat almost no other submission will have.
- **Honest eval numbers.** The dirty-rosters baseline is more credible than precision on clean fixtures, and the bias audit pre-empts the fairness question that judges should be asking but submissions rarely answer.
- **Reproducibility.** The synthetic data generator is deterministic via a fixed RNG seed, the eval harness is `uv run python -m evals.score`, and the demo's hero numbers come from the eval not from a slide.

## What we learned

- **Elastic Agent Builder MCP is far more capable than the legacy `@elastic/mcp-server-elasticsearch`.** The ~21 platform tools and the ability to register custom skills make the difference between "the agent calls one ES query" and "the agent shows 5-8 tool calls per chain that judges can scroll through."
- **The ADK `AgentTool` vs `sub_agents=[...]` distinction is load-bearing.** Wrapping sub-agents in `AgentTool` keeps the Coordinator in control; using `sub_agents=` is a one-way transfer and the Coordinator can't resume.
- **Verifier-gate-as-product, not as-feature.** Once we treated the HITL gate as the showcase capability (with consent + minor badges, server-side backstops, and a triage view), the rest of the UX fell into place. Trust matters more than algorithmic precision in this domain.
- **Multilingual matching is not "translate then search."** The compound analyzer stack (standard + phonetic + translit + nickname graph + semantic kNN) does work no single-strategy approach can do — and the Elastic `explain` output makes it visible enough to demo.

## What's next

- **Practitioner validation.** We have an outreach kit ([docs/outreach_kit.md](docs/outreach_kit.md)) for getting a 30-minute conversation with a Red Cross or NCMEC field worker; the goal is one quotable line that turns this from an AI demo into a field-aware system.
- **Federation handshake.** PFIF export exists; the next step is a PFIF *import* adapter so DisasterLens can ingest from NCMEC UMR / ICRC RFL feeds rather than just emit to them.
- **A biometric fallback boundary.** For mass-casualty incidents the right primitive is dental/DNA/fingerprint, which is where UNHCR BIMS and NamUs live. DisasterLens should declare the hand-off and integrate the relevant export.
- **Real shelter pilot.** The Texas Voluntary Organizations Active in Disaster (TX VOAD) network is the natural first deployment partner; their next tabletop exercise is in autumn 2026.

---

## Built with (Devpost "Built with" field — paste these tags)

```
gemini · vertex-ai · google-cloud-agent-builder · google-adk · elastic ·
elastic-agent-builder-mcp · cloud-run · firestore · secret-manager ·
fastapi · react · typescript · vite · maplibre-gl · twilio · python · uv
```

## Links to include in the Devpost submission

- **GitHub repo:** https://github.com/Bhardwaj-Saurabh/disasterlens-agent
- **Hosted URL (verifier UI):** *(your Cloud Run URL once deployed — `verifier-ui-...run.app`)*
- **Demo video (YouTube, ≤3 min, set to Public):** *(your unlisted-or-public YouTube link)*
- **License:** MIT (see [LICENSE](LICENSE))
