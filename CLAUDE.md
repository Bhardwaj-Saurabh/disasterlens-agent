# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This is **DisasterLens** — a submission for the [Google Cloud Rapid Agent Hackathon](https://googlecloudrapidagenthackathon.devpost.com/), **Elastic track**, deadline **2026-06-11**. The track choice is committed.

When work begins, read the docs **in this order**:

1. [README.md](README.md) — product positioning, judging-criteria mapping, hero capability
2. [docs/PRD.md](docs/PRD.md) — product spec, indices, demo golden path, eval scoreboard, 3-week sprint plan
3. [docs/design.md](docs/design.md) — system design: runtime topology, agent composition (1 Coordinator + Intake + Notifier sub-agents), HITL via ADK long-running tool + Firestore, hackathon-phase service mapping, deployment, repo layout. Operational source of truth; supersedes PRD where they differ on *how it runs*.

`docs/use_case.md` is the original strategic brief — historical context only. `docs/outreach.md` and `docs/devpost-submission.md` are gitignored personal working files.

**Prior architecture documents (`AI_FRAMEWORK.md`, `architecture.md`, `hackathon-architecture.md`) have been removed.** They specified an enterprise multi-agent framework that was over-engineered for a solo 26-day build. Do not reintroduce framework concepts (A2A bus, AI Gateway, semantic plane service, dual audit trail, sidecar tool containers, capability registry, OAuth issuer, per-agent identities) unless they appear in `docs/design.md` once written.

## Tooling

- Python `>=3.12` (see `.python-version`), managed via `uv` (`pyproject.toml` is the only manifest). Use `uv add <pkg>` and `uv run <cmd>`.
- Verifier UI (when built) is TypeScript / React / Vite / Mapbox GL JS.
- Project name in `pyproject.toml` is `google-hackathon`.

## Environment

- Runtime config is loaded from **`.env.local`** (gitignored), not `.env`. See `agent/config.py` and `.env.example`. `scripts/sprint1_day1.sh` also sources `.env.local`.
- Required vars: `GCP_PROJECT_ID`, `ELASTIC_ENDPOINT`, `ELASTIC_API_KEY`. Optional: `GCP_REGION` (default `us-central1`), `GEMINI_MODEL` (default `gemini-2.0-flash-exp`).
- In Google Cloud, secrets live in Secret Manager (`elastic-api-key`, `elastic-endpoint`, etc.) — `.env.local` is local-dev only.

## Common Commands

```bash
# One-shot Sprint 1 setup: preflight → enable APIs → create Firestore → stash secrets → run hello-world
./scripts/sprint1_day1.sh all

# Sub-steps (each idempotent)
./scripts/sprint1_day1.sh preflight    # check gcloud/uv/jq/curl and gcloud auth
./scripts/sprint1_day1.sh setup        # enable APIs, Firestore, Secret Manager, uv sync
./scripts/sprint1_day1.sh verify       # confirm APIs enabled, Elastic reachable, Vertex IAM OK
./scripts/sprint1_day1.sh helloworld   # uv run python -m agent.main

# Direct invocations
uv sync                                # install/refresh deps from pyproject.toml
uv add <pkg>                           # add a dep (do NOT hand-edit pyproject.toml)
uv run python -m agent.main            # run the ADK ↔ Elastic MCP connectivity agent
```

There is no test suite, linter, or formatter configured yet. Do not invent commands for those — add the config first if needed.

## Code Architecture

Current code is the **Sprint 1 Day 1 connectivity probe only** (one ADK agent, one MCP tool round-trip). The full agent composition described in `docs/design.md` §4 is not yet implemented.

What exists today:
- [agent/main.py](agent/main.py) — single `LlmAgent` wired to Elastic Agent Builder MCP via `MCPToolset` + `SseConnectionParams`. Two `TODO(day1)` markers flag the endpoint path and connection-params class as the most likely things to drift against current ADK / Elastic docs.
- [agent/config.py](agent/config.py) — minimal env loader. Real safety settings / thresholds / prompts arrive in Sprint 2.
- [scripts/sprint1_day1.sh](scripts/sprint1_day1.sh) — idempotent setup; the canonical entry point for getting the project to "hello-world runs."

Target shape (per [docs/design.md](docs/design.md) §4, §11) — build toward this, not around it:
- One ADK app, three agents: `Coordinator` (root `LlmAgent`) + `Intake` sub-agent + `Notifier` sub-agent.
- Four tool clusters on the Coordinator: `elastic_mcp` (MCPToolset), `name_variants` (deterministic FunctionTool — ICU translit + double-metaphone + nickname graph), `cloud_translation` (Agent Builder Extension), `await_verifier` (**long-running** FunctionTool — Firestore-backed HITL gate, §6).
- Three deployables total: `disasterlens-agent` (Agent Runtime), `verifier-ui` (Cloud Run service), `standing-query-watcher` (Cloud Run Job). No more.

The MCP connection uses **SSE transport** to `${ELASTIC_ENDPOINT}/api/agent_builder/mcp` with `Authorization: ApiKey ...`. If ADK ships an HTTP `ConnectionParams` class, prefer it over SSE.

## Track-Specific Technical Constraints (Elastic / DisasterLens)

- **ELSER v2 is English-only — do not use it for the multilingual layer.** Use **E5-multilingual** or **Jina v3** via Elastic inference endpoints. ELSER may be applied to English-only fields where it outperforms E5.
- Prefer the newer **Agent Builder MCP** (ES 9.2+ / Serverless) over the legacy `@elastic/mcp-server-elasticsearch`. Four custom Agent Builder skills are the agent's vocabulary: `match_person_across_rosters`, `search_social_mentions`, `create_reunification_case`, `register_standing_query` ([docs/PRD.md](docs/PRD.md) §5).
- HITL is implemented as the **ADK long-running tool pattern** (`await_verifier_decision`). Do not implement as a polling loop.
- Index analyzers (`name_standard`, `name_phonetic` via double-metaphone, `name_translit` via ICU + nickname `synonym_graph`) are load-bearing — every reunification decision compounds across them. Don't simplify the analyzer stack to "just fuzzy match".

## Demo-Driven Design Bias

The submission is judged on a 3-minute video. When making implementation choices, bias toward what's **visually compelling** in that video:

- Visible **5–8 Elastic MCP tool calls** per reasoning chain (the agent trace must scroll)
- Visible **approval modal** as the focal point of the HITL beat
- Visible **non-Roman-script** handling (مُحَمَّد → Mohammed/Muhammad/Mohamed/Mohd) — this is the hero unscripted moment
- A tangible end-artifact (dispatched notification with multilingual body)
- The **reunification map** (React + Mapbox) is the YouTube thumbnail

## Submission Requirements (Hard Gates)

From [docs/PRD.md](docs/PRD.md) §16:

- MIT `LICENSE` at repo root (GitHub auto-detected) — does not exist yet
- Public GitHub repo, hosted Cloud Run URL working in a fresh unauthenticated browser, cold-start <15s
- 3-minute demo video + pre-recorded backup
- 50-case held-out eval (`evals/family_pairs.jsonl`) with precision ≥ 0.90 @ confidence ≥ 0.80 — numbers must appear on screen in the video
- Native-Spanish-speaker review on ES strings before recording
- API keys and secrets via Google Secret Manager — never in code or `.env`
