# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Status

This repository is a **greenfield project** for the **Google Cloud Rapid Agent Hackathon** ("Building Agents for Real-World Challenges", submission deadline 2026-06-11). No application code exists yet — only `pyproject.toml`, an empty `README.md`, and `docs/use_case.md` containing the strategic brief.

When work begins, read [docs/use_case.md](docs/use_case.md) first. It is the source of truth for:
- The five candidate use cases (DisasterLens on Elastic is fully specified; four other partner tracks — Arize, Fivetran, GitLab, MongoDB, Dynatrace — are outlined)
- Per-track partner MCP capabilities (load-bearing, not decorative — see "Partner MCP Capabilities At a Glance")
- Hackathon judging criteria, demo-video skeleton, and submission requirements (open-source license at repo root, hosted URL, 3-min video)

## Tooling

- Python `>=3.12` (see `.python-version`), managed via `uv` (`pyproject.toml` is the only manifest; no `requirements.txt`). Use `uv add <pkg>` to add deps and `uv run <cmd>` to execute.
- Project name is `google-hackathon` (see `pyproject.toml`).

## Expected Architecture (per the brief)

The hackathon rules require the submission to be "powered by Gemini and Google Cloud Agent Builder." The brief's recommended stack:

- **Google ADK (Agent Development Kit)** + `MCPToolset` for the chosen partner MCP server
- Custom function tools for non-partner integrations (e.g., Maps, SMS)
- **Cloud Run** for hosting; **Agent Builder** console for demo polish
- A **human-in-the-loop approval gate** before any externally-visible action — this is a judging requirement, not optional

When choosing implementation patterns, bias toward what makes a 3-minute demo video visually compelling: visible multi-step plans, visible MCP tool calls, a visible approval modal, and a tangible end-artifact (dispatched route, opened ticket, etc.).

## Track-Specific Constraints to Remember

- **Dynatrace Grail queries incur per-GB costs** — keep DQL time-bounded if that track is chosen.
- **Fivetran MCP is read-only by default**; writes require `FIVETRAN_ALLOW_WRITES` plus per-call confirmation.
- **MongoDB MCP and Fivetran MCP have built-in destructive-op confirmation** — don't reimplement what the MCP already gates.
- **Elastic has two MCP servers**; the newer Agent Builder MCP (ES 9.2+/Serverless) is preferred over the legacy `@elastic/mcp-server-elasticsearch`.
