# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This is **DisasterLens** — a submission for the [Google Cloud Rapid Agent Hackathon](https://googlecloudrapidagenthackathon.devpost.com/), **Elastic track**, deadline **2026-06-11**. The track choice is committed.

When work begins, read the docs **in this order**:

1. [README.md](README.md) — product positioning, judging-criteria mapping, hero capability
2. [docs/PRD.md](docs/PRD.md) — product spec, indices, demo golden path, eval scoreboard, 3-week sprint plan
3. [docs/design.md](docs/design.md) — system design: runtime topology, agent composition, HITL via ADK long-running tool + Firestore, hackathon-phase service mapping, deployment, repo layout. Operational source of truth; supersedes PRD where they differ on *how it runs*.

`docs/use_case.md` is the original strategic brief — historical context only. `docs/devpost-submission.md` (and any `docs/outreach.md`) are gitignored personal working files.

**Prior architecture documents (`AI_FRAMEWORK.md`, `architecture.md`, `hackathon-architecture.md`) were removed.** They specified an enterprise multi-agent framework that was over-engineered for a solo 26-day build. Do not reintroduce framework concepts (A2A bus, AI Gateway, semantic plane service, dual audit trail, sidecar tool containers, capability registry, OAuth issuer, per-agent identities) unless they appear in `docs/design.md`.

## Tooling

- Python `>=3.12` (see `.python-version`), managed via `uv` (`pyproject.toml` is the only manifest). Use `uv add <pkg>` and `uv run <cmd>` — do not hand-edit `pyproject.toml`.
- Verifier UI is TypeScript / React 18 / Vite 5 / **MapLibre GL JS** (renders Mapbox raster tiles via the Styles API when `VITE_MAPBOX_TOKEN` is set, falls back to OSM otherwise).
- Project name in `pyproject.toml` is `google-hackathon`; the wheel package is `agent/`.
- No test suite, linter, or formatter is configured. Don't invent commands for those — add the config first if needed.

## Environment

- Runtime config is loaded from **`.env.local`** (gitignored), not `.env`. See [agent/config.py](agent/config.py) and [.env.example](.env.example). `scripts/sprint1_day1.sh` also sources `.env.local`.
- **Two Elastic endpoints are needed**: `ELASTIC_ENDPOINT` (the `.es.` data API) and `KIBANA_ENDPOINT` (the `.kb.` Agent Builder MCP host). If `KIBANA_ENDPOINT` is unset, `agent/config.py` derives it by string-replacing `.es.` → `.kb.`. This `.es.`/`.kb.` split is a load-bearing gotcha — see the memory `project_elastic_mcp_endpoint`.
- Vertex routing requires `GOOGLE_GENAI_USE_VERTEXAI=true`, `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, and ADC (`gcloud auth application-default login`). Default model is `gemini-2.5-flash` — **do not** use `gemini-2.0-flash-exp` (Gemini-API-only, 404s on Vertex; memory: `project_vertex_model_ids`).
- Verifier UI build-time env lives separately in `verifier_ui/.env.local` (Vite inlines `VITE_*` at build time). Currently only `VITE_MAPBOX_TOKEN`.
- In Google Cloud, secrets live in Secret Manager (`elastic-api-key`, `elastic-endpoint`, etc.) — `.env.local` is local-dev only.

## Common Commands

```bash
# ── Bootstrap (one time) ───────────────────────────────────────────────
./scripts/sprint1_day1.sh all          # preflight + APIs + Firestore + secrets + helloworld
uv sync                                 # install/refresh deps

# ── Data pipeline (rebuild Elastic from scratch) ───────────────────────
uv run python -m scripts.setup_inference        # create disasterlens_e5 inference endpoint
uv run python -m scripts.create_indices         # register synonyms set + 4 indices (--recreate to wipe)
uv run python -m data.generate_synthetic        # write NDJSON + evals/family_pairs.jsonl
uv run python -m data.ingest_to_elastic --reset # bulk-load all 4 indices

# ── Agent (two terminals — agent + verifier) ───────────────────────────
uv run python -m agent.main --demo              # canned María→Carlos golden-path query
uv run python -m agent.main "free-text seeker query"
uv run adk dev --module agent.agent             # ADK dev UI; root_agent is in agent/agent.py

# In a SECOND terminal, satisfy the await_verifier HITL gate:
uv run python -m agent.verifier_cli                 # interactive
uv run python -m agent.verifier_cli --auto-approve  # demo mode
uv run python -m agent.verifier_cli --watch        # keep polling for new pending decisions

# ── Verifier UI (React + FastAPI proxy) ────────────────────────────────
uv run uvicorn verifier_ui.server:app --reload --port 8787   # API + serves dist/ if built
cd verifier_ui && npm install && npm run dev                 # Vite at :5173 (proxies to :8787)
cd verifier_ui && npm run build                              # static build into verifier_ui/dist/

# ── Eval scoreboard (PRD §16 gate: fused precision ≥ 0.90) ─────────────
uv run python -m evals.score                    # recall@5 + fused precision/recall/F1
uv run python -m evals.score --csv              # also write evals/score_results.csv
uv run python -m evals.score --show-failures    # list every FP/FN by case_id
```

## Code Architecture

The code now implements the full agent composition (per `docs/design.md` §4) plus the eval harness and a working React verifier UI.

**Agent — `agent/`**
- [agent/agent.py](agent/agent.py) — exports `root_agent` (built by `coordinator.build_coordinator_agent()`). This is what `adk dev` and `adk deploy` discover.
- [agent/coordinator.py](agent/coordinator.py) — root `LlmAgent`. Sub-agents (Intake, Notifier) are wrapped as **`AgentTool`** so the Coordinator gets the result back and keeps reasoning. **Do not** put them in `sub_agents=[...]` — that's a one-way transfer and the Coordinator can't resume (memory: `project_adk_subagents_vs_agenttool`).
- [agent/intake.py](agent/intake.py), [agent/notifier.py](agent/notifier.py) — sub-agents. Intake is pure-LLM extraction, no tools. Notifier owns `dispatch_notification` and refuses without a valid `decision_id`.
- [agent/prompts.py](agent/prompts.py) — load-bearing system prompts for all three agents. Rule numbering is preserved across edits; changes should be re-evaluated against `evals/family_pairs.jsonl`.
- [agent/config.py](agent/config.py) — env, index names, `LOW_CONFIDENCE_FLOOR=0.75`, Gemini `SAFETY_SETTINGS` (intentionally tighter than defaults — false-positive matches are dangerous in this domain).
- [agent/main.py](agent/main.py) — CLI runner; pretty-prints the ADK event trace.
- [agent/verifier_cli.py](agent/verifier_cli.py) — terminal stand-in for the React UI; same Firestore contract.

**Tools — `agent/tools/`**
The Coordinator's four tool clusters:
- [agent/tools/elastic.py](agent/tools/elastic.py) — `MCPToolset` over **Streamable HTTP** (not SSE) to `${KIBANA_ENDPOINT}/api/agent_builder/mcp`. Discovers ~21 platform tools at runtime; prompts steer the agent toward `platform_core_search` and `platform_core_execute_esql`.
- [agent/tools/name_variants.py](agent/tools/name_variants.py) — deterministic FunctionTool wrapping `data.variants.expand` (ICU translit + double-metaphone + nickname graph). Called BEFORE searching any non-Roman-script or diacritic-bearing name.
- [agent/tools/geocode.py](agent/tools/geocode.py) — lookup-table geocoder for the 10 Houston shelters + landmarks. **Intentionally not Google Maps Geocoding** — the demo must reproduce frame-for-frame.
- [agent/tools/verifier.py](agent/tools/verifier.py) — `await_verifier` **long-running** FunctionTool. Writes `pending_decisions/{decision_id}` to Firestore, polls until `decision` is set, returns it. Every match destined for an externally-visible action flows through here. Do not reimplement as a polling loop in the prompt — the long-running-tool pattern is the canonical HITL gate.
- [agent/tools/notify.py](agent/tools/notify.py) — `dispatch_notification`, owned by Notifier. Revalidates the `decision_id` against Firestore before sending.

**Data layer — `data/`**
- [data/personas.py](data/personas.py) — hand-curated `STRESS_PERSONAS` (every PRD §7 stress-case row) + `FILLER_PERSONAS` + 10 real Houston-area `SHELTERS` with lat/lon.
- [data/variants.py](data/variants.py) — deterministic name-variant generator (the engine behind `name_variants`). Rules: `nickname`, `arabic_romanise`, `fold_diacritics`, `name_order_swap`, `vietnamese_fold`, `initial_form` — the **hero rules** the eval scoreboard reports on.
- [data/embed.py](data/embed.py) — client-side E5-multilingual embedding via `POST _inference/text_embedding/disasterlens_e5`. **Don't try to use an ingest pipeline** — the `inference` processor silently drops embeddings on Elastic Cloud Serverless 9.5 (memory: `project_inference_pipeline_silent_drop`).
- [data/generate_synthetic.py](data/generate_synthetic.py) — emits NDJSON for all 4 indices + `evals/family_pairs.jsonl`. Distribution rule: STRESS personas appear in 2–3 shelters as *different variants* each time (the cross-roster collisions); FILLER personas appear in exactly 1 shelter. Seeded; reproducible.
- [data/ingest_to_elastic.py](data/ingest_to_elastic.py) — plain `_bulk`, no pipeline (embeddings are pre-baked).
- [data/mappings/](data/mappings/) — JSON index mappings. `name_standard`/`name_phonetic` (double-metaphone)/`name_translit` (ICU + nickname `synonym_graph`) are **load-bearing**; don't simplify to "just fuzzy match."

**Scripts — `scripts/`**
- [scripts/sprint1_day1.sh](scripts/sprint1_day1.sh) — idempotent bootstrap. Sub-commands: `preflight | setup | verify | helloworld | all`.
- [scripts/create_indices.py](scripts/create_indices.py) — registers the synonyms set then the 4 indices. **Synonyms are search-time only and live in a Serverless `synonyms_set`** (the PRD's inline example is wrong; memory: `project_synonym_graph_search_time`).
- [scripts/setup_inference.py](scripts/setup_inference.py) — creates `disasterlens_e5` (`.multilingual-e5-small`, 384-d). Idempotent.

**Eval — `evals/`**
- [evals/score.py](evals/score.py) — the headline number. Runs the same multi-strategy `dis_max` query the agent uses, computes recall@K, MRR, per-rule recall (with `HERO_RULES` highlighted), hard-negative precision, AND the fused-confidence layer (`top1_score × token-overlap × age`) that produces **PRD §16's "precision ≥ 0.90 at confidence ≥ 0.80"** headline. Threshold lives at `FUSED_CONFIDENCE_THRESHOLD = 0.75` — matches `agent.config.LOW_CONFIDENCE_FLOOR`. Keep them in sync.
- [evals/family_pairs.jsonl](evals/family_pairs.jsonl) — 50-case gold set, generated by `data/generate_synthetic.py`. **The number that must appear on screen in the demo video** comes from running `evals.score` against this file.

**Verifier UI — `verifier_ui/`**
- [verifier_ui/server.py](verifier_ui/server.py) — FastAPI proxy. Exposes Firestore `pending_decisions` as REST (`/api/pending`, `/api/decisions/{id}/decide`, `/api/shelters`) and serves the built React app from `dist/`. **Polls, doesn't `onSnapshot`** — deliberate, so no Firebase Web App provisioning is needed (the API uses the agent's ADC).
- `verifier_ui/src/` — React. Hero component is [ReunificationMap.tsx](verifier_ui/src/components/ReunificationMap.tsx) (MapLibre, animated arc from seeker pin to candidate shelter).

**Three deployables total** (per `docs/design.md` §11): `disasterlens-agent` (Agent Runtime), `verifier-ui` (Cloud Run service), `standing-query-watcher` (Cloud Run Job). No more.

## Track-Specific Technical Constraints (Elastic / DisasterLens)

- **ELSER v2 is English-only — do not use it for the multilingual layer.** Use **E5-multilingual** (or Jina v3) via Elastic inference endpoints. ELSER may be applied to English-only fields where it outperforms E5.
- Prefer the newer **Agent Builder MCP** (ES 9.2+ / Serverless) over the legacy `@elastic/mcp-server-elasticsearch`. Four custom Agent Builder skills are the agent's vocabulary: `match_person_across_rosters`, `search_social_mentions`, `create_reunification_case`, `register_standing_query` ([docs/PRD.md](docs/PRD.md) §5).
- HITL is the **ADK long-running tool pattern** (`await_verifier`). Do not reimplement as a prompt-level polling loop.
- Index analyzers (`name_standard`, `name_phonetic` via double-metaphone, `name_translit` via ICU + nickname `synonym_graph`) are load-bearing — every reunification decision compounds across them.

## Demo-Driven Design Bias

The submission is judged on a 3-minute video. When making implementation choices, bias toward what's **visually compelling**:

- Visible **5–8 Elastic MCP tool calls** per reasoning chain (the trace must scroll)
- Visible **approval modal** as the focal point of the HITL beat
- Visible **non-Roman-script** handling (مُحَمَّد → Mohammed / Muhammad / Mohamed / Mohd) — the hero unscripted moment
- A tangible end-artifact (dispatched notification with multilingual body)
- The **reunification map** is the YouTube thumbnail

## Submission Requirements (Hard Gates)

From [docs/PRD.md](docs/PRD.md) §16:

- MIT `LICENSE` at repo root (GitHub auto-detected) — does not exist yet
- Public GitHub repo, hosted Cloud Run URL working in a fresh unauthenticated browser, cold-start <15s
- 3-minute demo video + pre-recorded backup
- 50-case held-out eval (`evals/family_pairs.jsonl`) with **fused precision ≥ 0.90 at confidence ≥ 0.80** — numbers must appear on screen in the video
- Native-Spanish-speaker review on ES strings before recording
- API keys and secrets via Google Secret Manager — never in code or `.env`
