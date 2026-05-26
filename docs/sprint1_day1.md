# Sprint 1 — Day 1 Setup

Goal of Day 1: prove the two biggest unknowns work, so the rest of Sprint 1 can proceed without surprises:

1. **ADK ↔ Elastic Agent Builder MCP round-trip** — can our agent discover and call Elastic MCP tools?
2. **Custom Agent Builder skill registration on Serverless trial tier** — can we register the four custom skills the PRD requires?

By end of day, `./scripts/sprint1_day1.sh all` should exit cleanly and the agent should print a Gemini response naming at least one Elastic index. Anything beyond that is Day 2+.

---

## Manual prerequisites (do these first — script can't automate)

1. **Elastic Cloud Serverless trial**
   - Sign up: <https://cloud.elastic.co/registration>
   - Create a **Search** project (Serverless tier, not Hosted)
   - Wait for green status
   - From Kibana → **Stack Management → API keys**, create a new key (un-restricted for Day 1; tighten in Sprint 3)
   - Copy the **endpoint URL** and **base64 API key** — these go in `.env.local`
   - Confirm **Agent Builder** is available in your project's Kibana left nav. If it's not visible, your trial may not include it — open a chat with Elastic support before continuing

2. **Google Cloud project**
   - Either use an existing project, or:
     - Free trial: <https://cloud.google.com/free>
     - Hackathon $100 credits (1–5 business day approval): <https://forms.gle/xfv9vQzfRfNCCVbG7>
   - Enable billing on the project
   - Note the **project id** (not the display name) — goes in `.env.local`

3. **Local tools** (macOS)
   ```bash
   brew install --cask google-cloud-sdk
   brew install jq
   # uv: https://docs.astral.sh/uv/getting-started/installation/
   curl -LsSf https://astral.sh/uv/install.sh | sh
   gcloud auth login
   gcloud auth application-default login
   ```

4. **Local config**
   ```bash
   cp .env.example .env.local
   # edit .env.local — fill in GCP_PROJECT_ID, ELASTIC_ENDPOINT, ELASTIC_API_KEY
   ```
   `.env.local` is already gitignored via the `.env*` pattern — double-check before committing.

---

## Run the script

```bash
chmod +x scripts/sprint1_day1.sh
./scripts/sprint1_day1.sh all
```

Subcommands if you want to run in pieces:
- `preflight` — checks local tools, gcloud auth, project access
- `setup` — enables 9 GCP APIs, creates Firestore, stashes secrets, runs `uv sync`
- `verify` — checks each setup step landed and pings the Elastic cluster
- `helloworld` — runs `agent/main.py` (the actual de-risk)

Re-running is safe — every step is idempotent.

---

## What "success" looks like

`helloworld` output should be roughly:

```
[hello-world] discovered N MCP tools:
  • core_index_explorer
  • core_execute_esql
  • core_generate_esql
  • core_get_document_by_id
  • …

[hello-world] running agent…
[hello-world] agent: I found 0 indices in the cluster; the cluster is empty.
```

(0 indices is correct on Day 1 — we haven't ingested anything yet.)

If you see that, **Day 1 is done.** Commit `.env.example`, `pyproject.toml`, `uv.lock`, `agent/`, `scripts/` and move to Day 2.

---

## Failure-mode triage

| Symptom | Most likely cause | Fix |
|---|---|---|
| `gcloud services enable` fails with permission denied | Account isn't Owner/Editor on the project | Add `roles/owner` or `roles/editor` to your account |
| Firestore create fails with "already exists in a different mode" | A previous Datastore-mode database exists | Use a fresh project, or migrate per <https://cloud.google.com/datastore/docs/upgrade-to-firestore> |
| Elastic `curl` returns 401 | API key wrong or expired | Regenerate the key in Kibana; re-run `setup` to push new version to Secret Manager |
| Elastic `curl` returns 404 | `ELASTIC_ENDPOINT` is the Kibana URL, not the Elasticsearch URL | Use the URL ending in `.es.region.gcp.elastic-cloud.com` (no `/api/...` path) |
| MCP tool discovery returns 0 tools | Wrong MCP path, or Agent Builder not enabled | Confirm path against <https://www.elastic.co/docs/solutions/search/agent-builder/mcp-server>; check Agent Builder appears in Kibana left nav |
| MCP tool discovery returns 401/403 | API key lacks Agent Builder scope | Regenerate key with broader permissions for Day 1; tighten in Sprint 3 |
| Gemini call fails with permission denied | Your account lacks `roles/aiplatform.user` | `gcloud projects add-iam-policy-binding $GCP_PROJECT_ID --member=user:YOU --role=roles/aiplatform.user` |
| Import error on `google.adk.tools.mcp_tool` | ADK API moved between versions | Check current import path at <https://google.github.io/adk-docs/tools/mcp-tools/> and adjust `agent/main.py` |

---

## Day 2 starts here

Once Day 1 is green:

1. Register the four custom Agent Builder skills (`match_person_across_rosters`, `search_social_mentions`, `create_reunification_case`, `register_standing_query`) in Kibana — this validates unknown #2 from above
2. Write the index mappings (`data/mappings/*.json`) per PRD §4.3
3. Write `data/generate_synthetic.py` — start with the name-variant gold set since it's the eval bedrock
4. Bulk-ingest into Elastic

That's the rest of Sprint 1 Week 1.
