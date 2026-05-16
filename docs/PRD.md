# DisasterLens — Language-Aware Family Reunification

## Hackathon: Google Cloud Rapid Agent Hackathon (Elastic Track)
**Submission Deadline:** 2026-06-11
**Track:** Elastic ($5K / $3K / $2K bucket)
**Builder:** Solo
**Today:** 2026-05-16 (≈26 days runway)
**Repo:** `github.com/<your-handle>/disasterlens`

---

## 1. Elevator Pitch (30 seconds — memorise for the video)

> Disasters separate families, and the people hit hardest are immigrant communities — the grandmother in Houston looking for her grandson, in Spanish, whose name might be spelled three different ways across three shelter rosters. **DisasterLens is an AI agent that reunites families separated by disasters** — across languages, name transliterations, and siloed shelter rosters — using Elasticsearch as its operational nervous system, with a human verifier approving every match before it reaches a phone.

Real-world precedents: **Red Cross Safe and Well**, **ICRC Restoring Family Links**, **NamUs**. These systems already exist; what they lack is a multilingual, fuzzy-name-tolerant, agentic search layer.

---

## 2. Problem Statement

### Who suffers
- **Seekers** — disaster-displaced people trying to locate missing family members. Disproportionately elderly, non-English-speaking, or both. They don't know which shelter their relative went to. They may only have a phonetic spelling of a name. They may not speak English to the call-centre operator.
- **Reunification coordinators** — Red Cross / CERT / volunteer leads who manually cross-reference inbound calls against shelter rosters, 211 logs, and social posts. The Red Cross Safe and Well program is essentially a registry; the *matching* work is still manual and slow.

### Why it's hard today
- Names in shelter rosters are spelled differently than the seeker says them. *Carlos Martínez* vs *Carlos Martinez* vs *C. Martinez* vs *Carlitos M.* — every dataset uses a different convention.
- Names from non-Roman scripts (Arabic, Vietnamese with diacritics, Tamil) get romanised inconsistently. *محمد* becomes *Mohammed* / *Muhammad* / *Mohamed* / *Mohd*.
- The seeker speaks one language, the operator another, the roster a third. Translation is brittle on proper nouns specifically.
- Information lives in multiple silos (shelter rosters, 211 logs, missing-person reports, social posts) — there is no single search surface.
- False matches are dangerous: telling someone you've "found" their child and being wrong is catastrophic. So there must be a human verifier in the loop.

### The gap DisasterLens fills
A reasoning agent that treats Elasticsearch as its operational nervous system — fusing rosters, reports, logs, and social signals; tolerating fuzzy / phonetic / transliterated name variants; reasoning about match confidence in natural language; and queuing candidate matches for a human verifier before any contact is made.

---

## 3. Use Case Scenario — The Demo Golden Path

### Scene: Hurricane Elena, Houston TX, Hour 14

**Persona — María**, 68, Spanish-speaking only. Evacuated from her apartment with her daughter. Has lost contact with:
- **Carlos**, her 15-year-old grandson, evacuated separately with his school group.
- **Ramón**, her son-in-law, last seen helping a neighbour. María isn't sure how his name is spelled on official documents.

**Request 1 — Seeker (Spanish)**
> *"Busco a mi nieto Carlos Martínez, tiene 15 años. Iba con un grupo de su escuela. Y también busco a mi yerno Ramón — no sé bien cómo se escribe su nombre."*

**Agent behaviour:**
1. Detects Spanish. Responds in Spanish throughout.
2. **Elicits structured details** via short follow-ups: ages, last known location, languages, distinguishing features, photos if available. Creates a `reunification_case` document in Elasticsearch.
3. Decomposes into two parallel reunification searches (Carlos, Ramón).
4. **Cross-source fuzzy name search** via Elastic MCP — for each candidate, runs:
   - Exact + fuzzy + phonetic (double-metaphone) match on `shelter_rosters.name`
   - ICU-transliterated match for accent/diacritic variants
   - Semantic search on `missing_person_reports.description` for free-text mentions
   - Multilingual semantic search on `social_reports.text` for any post mentioning the name + a Houston location
   - Cross-reference with other open `reunification_cases` in case someone else is seeking the same person
5. **Reasons about each candidate** in natural language: "Carlos Martínez at Memorial High Shelter — age 15, arrived 14:20, school group from Spring Branch ISD. High confidence (0.91): name match exact, age match, school affiliation consistent with seeker description."
6. **Surfaces a ranked list of candidate matches** to a verifier dashboard. Each candidate shows: confidence score, evidence chain, side-by-side comparison of seeker description vs candidate record.
7. **Human verifier** (Red Cross / dispatcher) reviews each candidate. Approves, rejects, or requests more info. **Nothing leaves the system without verifier approval.**
8. On approval, agent drafts a notification *in Carlos's likely-preferred language* (English, since he attends a US high school) for the shelter coordinator, and a separate notification in Spanish for María. Mocked SMS/Slack dispatch.
9. **For Ramón** — name spelling unclear. Agent shows it considered multiple variants (Ramón, Ramon, Raymond, R. Hernández) and found a likely candidate at a different shelter, but at lower confidence (0.62). Verifier requests an additional question from María ("does Ramón have a tattoo on his left arm?"). Agent generates the follow-up in Spanish.
10. **If no match found** — agent registers a **standing reunification query** that auto-re-fires when new roster entries arrive. María gets a callback (in Spanish) if/when a match appears. This mirrors how Red Cross Safe and Well operates today.

### Second beat — Coordinator triage (English)
> *"Show me all reunification cases over 24 hours old still without a verified match, sorted by seeker vulnerability."*

Agent runs an ES|QL aggregation, returns a ranked dashboard. Coordinator can click into any case and see the agent's reasoning trail.

### Third beat — The "wow" moment for the video
> *"What about مُحَمَّد? My uncle's name is in Arabic."*

Agent demonstrates handling Arabic-script input, transliterating to all common romanisations (Mohammed / Muhammad / Mohamed / Mohd), searching the rosters with each variant + phonetic match, and surfacing a candidate. **This is the unscripted-feeling moment the demo video pivots on.**

---

## 4. Architecture

### 4.1 High-Level Components

```
┌─────────────────────────────────────────────────────────────┐
│                  DISASTERLENS AGENT                          │
│           (Google ADK + Gemini 2.x on Cloud Run)             │
│                                                              │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐           │
│  │ Intake     │  │ Match-     │  │ Verifier      │           │
│  │ (multi-    │→ │ Reasoner   │→ │ Gate          │           │
│  │  lingual)  │  │ (Elastic   │  │ (long-running │           │
│  │            │  │  MCP)      │  │  tool / HITL) │           │
│  └────────────┘  └────────────┘  └──────────────┘           │
│         │              │                  │                  │
│         ▼              ▼                  ▼                  │
│  ┌────────────┐  ┌────────────┐  ┌──────────────┐           │
│  │ Language   │  │ Standing-  │  │ Notifier     │           │
│  │ tooling    │  │ Query      │  │ (mocked SMS  │           │
│  │ (translit, │  │ Watcher    │  │  / Slack)    │           │
│  │  translate)│  │            │  │              │           │
│  └────────────┘  └────────────┘  └──────────────┘           │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│            ELASTICSEARCH (Elastic Cloud Serverless)          │
│                                                              │
│  ┌──────────────────┐ ┌──────────────────┐                  │
│  │ shelter_rosters  │ │ missing_person_  │                  │
│  │ (person-level,   │ │ reports          │                  │
│  │  fuzzy + phonetic│ │ (free-text,      │                  │
│  │  + translit name │ │  multilingual    │                  │
│  │  analyzers)      │ │  semantic)       │                  │
│  └──────────────────┘ └──────────────────┘                  │
│                                                              │
│  ┌──────────────────┐ ┌──────────────────┐                  │
│  │ social_reports   │ │ reunification_   │                  │
│  │ (multilingual,   │ │ cases            │                  │
│  │  semantic)       │ │ (open seeker     │                  │
│  │                  │ │  queries)        │                  │
│  └──────────────────┘ └──────────────────┘                  │
└─────────────────────────────────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│        VERIFIER UI (React + Mapbox GL JS on Cloud Run)       │
│                                                              │
│   Hero reunification map  |  Candidate-match queue           │
│   Live arc animation on   |  Side-by-side comparison         │
│   new match               |  Approve / Reject / Ask more     │
└─────────────────────────────────────────────────────────────┘
```

### 4.2 Tech Stack

| Layer | Technology | Why |
|---|---|---|
| **Agent Framework** | Google ADK (Python) | Hackathon requirement. `MCPToolset` for Elastic MCP. Long-running tool pattern for the verifier gate. Deploy via `adk deploy cloud_run`. |
| **LLM** | Gemini 2.x on Vertex AI (latest available at submission time) | Hackathon requirement. Multilingual reasoning, structured output, tool-use. Specific version pinned at submission; not hard-coded earlier. |
| **Search & Data** | Elasticsearch 9.x (Elastic Cloud Serverless) | Partner-track requirement. Custom name-matching analyzers (fuzzy, phonetic double-metaphone, ICU transliteration, synonym_graph for nicknames). Multilingual semantic search via **E5-multilingual** or **Jina v3** inference endpoints (ELSER is English-only and not suitable here). |
| **Elastic MCP** | Agent Builder MCP endpoint: `core_execute_esql`, `core_generate_esql`, `core_index_explorer`, `core_get_document_by_id`, plus custom Agent Builder skills (see §5) | The agent's primary action surface. Every reunification decision goes through these. |
| **Custom Tools** | ADK `FunctionTool` | `transliterate_name` (ICU), `translate_text` (Cloud Translation), `dispatch_notification` (mocked), `await_verifier_decision` (long-running HITL tool). |
| **Verifier UI** | React + Vite + Mapbox GL JS + WebSocket | Replaces the original Streamlit plan — design score caps at ~5 with Streamlit. |
| **Hosting** | Google Cloud Run (agent + UI in same region as Elastic cluster) | Serverless, auto-scaling, one-command deploy. |
| **Language** | Python 3.12 (agent), TypeScript (UI) | ADK native; Vite/React for the dispatcher. |

### 4.3 Elastic Index Designs

#### `shelter_rosters` (NEW — person-level, not shelter-level)
```json
{
  "settings": {
    "analysis": {
      "filter": {
        "name_phonetic": { "type": "phonetic", "encoder": "double_metaphone", "replace": false },
        "name_nicknames": { "type": "synonym_graph", "synonyms_path": "analysis/nicknames.txt" }
      },
      "analyzer": {
        "name_standard":   { "tokenizer": "standard", "filter": ["lowercase", "asciifolding", "name_nicknames"] },
        "name_phonetic":   { "tokenizer": "standard", "filter": ["lowercase", "asciifolding", "name_phonetic"] },
        "name_translit":   { "tokenizer": "icu_tokenizer", "filter": ["icu_folding", "icu_normalizer", "lowercase"] }
      }
    }
  },
  "mappings": {
    "properties": {
      "person_id": { "type": "keyword" },
      "shelter_id": { "type": "keyword" },
      "name": {
        "type": "text",
        "analyzer": "name_standard",
        "fields": {
          "phonetic": { "type": "text", "analyzer": "name_phonetic" },
          "translit": { "type": "text", "analyzer": "name_translit" },
          "keyword":  { "type": "keyword" }
        }
      },
      "name_variants": { "type": "keyword" },
      "age": { "type": "integer" },
      "language_spoken": { "type": "keyword" },
      "arrival_time": { "type": "date" },
      "school_or_employer": { "type": "text" },
      "distinguishing_features": { "type": "text" },
      "contact_consent": { "type": "boolean" },
      "shelter_location": { "type": "geo_point" }
    }
  }
}
```

#### `missing_person_reports` (NEW)
```json
{
  "mappings": {
    "properties": {
      "report_id": { "type": "keyword" },
      "subject_name": { "type": "text", "analyzer": "name_standard", "fields": { "phonetic": { "type": "text", "analyzer": "name_phonetic" }, "translit": { "type": "text", "analyzer": "name_translit" } } },
      "subject_age": { "type": "integer" },
      "description": { "type": "text" },
      "description_embedding": { "type": "dense_vector", "dims": 768, "index": true, "similarity": "cosine" },
      "language": { "type": "keyword" },
      "last_known_location": { "type": "geo_point" },
      "last_known_location_text": { "type": "text" },
      "reported_at": { "type": "date" },
      "source": { "type": "keyword" }
    }
  }
}
```

#### `reunification_cases` (NEW — open seeker queries)
```json
{
  "mappings": {
    "properties": {
      "case_id": { "type": "keyword" },
      "seeker_name": { "type": "text" },
      "seeker_language": { "type": "keyword" },
      "seeker_contact": { "type": "keyword" },
      "subject_name_as_given": { "type": "text" },
      "subject_name_variants_explored": { "type": "keyword" },
      "subject_age_estimate": { "type": "integer" },
      "last_known_location": { "type": "geo_point" },
      "distinguishing_features": { "type": "text" },
      "status": { "type": "keyword" },
      "candidate_matches": {
        "type": "nested",
        "properties": {
          "person_id": { "type": "keyword" },
          "source_index": { "type": "keyword" },
          "confidence": { "type": "float" },
          "evidence": { "type": "text" },
          "verifier_decision": { "type": "keyword" },
          "verified_at": { "type": "date" }
        }
      },
      "standing_query_active": { "type": "boolean" },
      "created_at": { "type": "date" },
      "resolved_at": { "type": "date" }
    }
  }
}
```

#### `social_reports`
```json
{
  "mappings": {
    "properties": {
      "report_id": { "type": "keyword" },
      "text": { "type": "text" },
      "text_embedding": { "type": "dense_vector", "dims": 768, "index": true, "similarity": "cosine" },
      "language": { "type": "keyword" },
      "mentioned_names": { "type": "keyword" },
      "geo_location": { "type": "geo_point" },
      "source_platform": { "type": "keyword" },
      "timestamp": { "type": "date" }
    }
  }
}
```

> **Note on embeddings:** ELSER v2 is English-only and is not used in this design. Multilingual semantic search uses **E5-multilingual** or **Jina v3** via Elastic inference endpoints. ELSER may be applied to English-only fields where it outperforms E5, but is not the primary multilingual layer.

---

## 5. Elastic MCP Integration — Why It's Structurally Essential

The Elastic MCP must be **load-bearing**. Remove it and the agent cannot match anyone. Every reasoning step maps to an Elastic MCP tool call:

| Agent Step | Elastic MCP Tool | What It Does |
|---|---|---|
| Discover available indices and mappings | `core_index_explorer` | Agent learns the four reunification indices and their analyzers |
| Fuzzy + phonetic + transliterated name search | Custom `match_person_across_rosters` (Agent Builder skill) | Compound query: `name` (standard) `OR` `name.phonetic` `OR` `name.translit`, plus age range filter, plus optional location geo-distance |
| Semantic match on missing-person descriptions | `core_execute_esql` with `kNN` over `description_embedding` | Find reports whose free-text description matches the seeker's structured description |
| Mentions of the name in social posts | Custom `search_social_mentions` (Agent Builder skill) | Multilingual semantic search + name keyword match |
| Cross-reference with other open cases | `core_execute_esql` | Has anyone else opened a reunification case for the same subject? |
| Log the seeker's case | Custom `create_reunification_case` (Agent Builder skill, writes via Elastic API) | Creates a `reunification_cases` document |
| Register standing query | Custom `register_standing_query` (Agent Builder skill) | Marks the case for auto-re-fire when new roster entries land |
| Coordinator triage | `core_execute_esql` | Aggregation over open cases by age, vulnerability, verifier status |

### Custom Agent Builder Skills to Register in Elastic

These become available via the same MCP endpoint and are the agent's high-level vocabulary:

1. **`match_person_across_rosters`** — input: name (string), age (int, optional), location (geo_point, optional), language (string, optional). Returns ranked candidates with per-candidate evidence breakdown (which analyzer fired, how confident).
2. **`search_social_mentions`** — input: name + variants, time window, geo bounds. Returns ranked posts.
3. **`create_reunification_case`** — input: structured seeker case document. Returns case_id.
4. **`register_standing_query`** — input: case_id. Marks the case for ingest-time re-evaluation.

---

## 6. Agent Design (ADK Implementation)

### 6.1 Agent Topology

For a solo build, ship **one ADK agent with well-separated tools** and *describe* it as a multi-agent architecture in the README/diagram. The sub-agent names below are reflected as tool clusters in code:

- **Intake** — multilingual structured-needs extraction from free-text seeker input.
- **Match-Reasoner** — orchestrates Elastic MCP calls and synthesises candidate evidence chains.
- **Verifier Gate** — invokes the long-running HITL tool and pauses execution until the verifier responds.
- **Standing-Query Watcher** — registers and re-fires standing queries (in code: a separate Cloud Run job that listens to Elastic ingest events).

### 6.2 System Prompt (Core)

```
You are DisasterLens, an AI agent that reunites families separated by
natural disasters. Your mission is to find candidate matches for missing
relatives across siloed shelter rosters, missing-person reports, and
social posts — across languages, name transliterations, and spelling
variants — and surface them to a human verifier.

RULES:
1. ALWAYS detect the seeker's language and respond in that language.
2. ALWAYS search Elasticsearch before answering — NEVER guess about who
   is or isn't at a shelter.
3. NEVER tell a seeker you've "found" their relative. Surface CANDIDATES
   to the verifier; only deliver confirmed matches after verifier approval.
4. ALWAYS show your reasoning: name variants tried, indices searched,
   why each candidate matched.
5. For non-Roman scripts (Arabic, Vietnamese-with-diacritics, Chinese,
   Tamil), call `transliterate_name` to enumerate common romanisations
   before searching.
6. If confidence on the best candidate is below 0.75, ask the seeker for
   one additional distinguishing detail BEFORE surfacing to verifier.
7. If no match is found, ALWAYS offer to register a standing query.
8. When invoking `dispatch_notification`, always call `await_verifier_decision`
   first. The verifier's decision is recorded in `reunification_cases.
   candidate_matches[].verifier_decision`.
```

### 6.3 Human-in-the-Loop via ADK Long-Running Tools

The verifier gate is implemented as an **ADK long-running tool** (`await_verifier_decision`), NOT a polling shape. The agent's run pauses; the React verifier UI surfaces the candidate; the verifier's Approve/Reject/Ask-more action is posted back to the agent run, which resumes. This is the canonical ADK pattern and:
- avoids a custom polling loop,
- works naturally with the `adk deploy cloud_run --with_ui` flow,
- gives the demo video a clear visual: the agent's "thinking" indicator pauses, the verifier clicks Approve, the agent resumes and drafts the notification.

In the demo video, **show this gate explicitly**. The judges are told to look for human oversight; this is where they look.

---

## 7. Synthetic Data Requirements

Pre-build in Sprint 1. Realism is judged by name-variant believability, not volume.

| Dataset | Records | Key Characteristics |
|---|---|---|
| **shelter_rosters** | 250–300 person-level records across 10 shelters | Mix of ages, languages spoken, school/employer affiliations. **Crucial**: includes deliberate name-variant collisions — same person spelled three different ways across three shelters; common nicknames vs full names; romanised Arabic/Vietnamese names with multiple variants. |
| **missing_person_reports** | 150–200 | Free-text descriptions in EN + ES with realistic detail. ~30 with non-Roman-script subject names (Arabic + Vietnamese). |
| **reunification_cases** | 30–40 pre-seeded open cases | For the coordinator triage demo. Mix of statuses (pending verifier, verified, no-match, standing-query). |
| **social_reports** | 300–400 multilingual posts | EN + ES primarily, plus a stress-test subset with Arabic-script and transliterated Arabic name mentions. Native-speaker reviewed for ES. |

### Name-Variant Stress Cases (the eval-grade data)

This is what separates DisasterLens from generic search. Build these as a labelled gold set:

| Seeker says | Roster has | Why it's hard |
|---|---|---|
| Carlos Martínez | Carlos Martinez | Diacritic |
| Carlos Martínez | Carlitos M. | Nickname + initial |
| Mohammed Khan | Muhammad Khan | Romanisation variant |
| Mohammed Khan | محمد خان | Non-Roman script |
| Nguyễn Văn Anh | Nguyen Van Anh | Vietnamese diacritics |
| Nguyễn Văn Anh | Van Anh Nguyen | Name-order inversion |
| Raymond Hernández | Ramón Hernández | Anglicisation of Spanish name |
| Catherine | Katherine, Cathy, Kate | Nickname graph |

### Data Generation Strategy
A Python script that:
1. Uses Gemini to generate base person records with realistic demographic profiles.
2. For each person, deterministically generates 2–4 spelling variants using rules (diacritic stripping, romanisation tables, nickname dictionaries) — this gives a *labelled* gold set for evals.
3. Embeds free-text descriptions with E5-multilingual via Elastic inference pipelines on ingest.
4. Outputs JSON ready for Elasticsearch bulk ingestion + a parallel `gold_matches.jsonl` file used by the eval scoreboard (§13).

---

## 8. Judging Criteria Mapping

| Criterion | How DisasterLens Scores |
|---|---|
| **Technological Implementation** | Compound Elastic queries spanning four indices and three name analyzers. ADK long-running tool for HITL (canonical pattern, not a hack). Custom Agent Builder skills as the agent's vocabulary. E5-multilingual via Elastic inference. Cloud Run deployment with observable tool-call traces. |
| **Design** | Hero reunification-map visual. Custom React verifier UI (not Streamlit). Side-by-side seeker-vs-candidate comparison cards. Live arc animation when a new candidate match lands. Multilingual by default. |
| **Potential Impact** | Reunification is what Red Cross Safe and Well, ICRC RFL, and NamUs do today — manually. Named beneficiaries (María, Carlos, Ramón). Real-world precedent the judges may recognise. **Measured outcomes** (§13). |
| **Quality of the Idea** | Not "chat with your data." A narrow, emotionally resonant, technically hard problem (cross-language fuzzy name matching) that Elasticsearch is uniquely suited to solve. Real-world programs to reference. |

---

## 9. Differentiation — Why This Wins Over Typical Submissions

| Typical Elastic Submission | DisasterLens |
|---|---|
| "Chat with your enterprise docs" | Multi-actor reunification system |
| English-only | Multilingual by intrinsic mission, not bolted-on |
| Exact-match search | Fuzzy + phonetic + transliteration + nickname graph + semantic |
| Read-only | Read + write (create case, register standing query, log verifier decision) |
| No human oversight | Verifier gate is the *showcase* feature, not a checkbox |
| Static knowledge base | Live operational indices with standing-query re-fire |
| 1 tool call per turn | 5–8 Elastic MCP calls per reasoning chain |
| "Ask it a question" demo | "Watch grandma find her grandson across three shelters" demo |

---

## 10. Build Plan (3-Week Sprint)

26 days available. Three sprints of one week, plus submission week.

### Sprint 1 — Foundation + Synthetic Data (Week 1, ending ~2026-05-23)
- [ ] Elastic Cloud Serverless trial provisioned; API key with Agent Builder permissions
- [ ] Google Cloud project: ADK, Vertex AI, Cloud Run, Cloud Translation enabled
- [ ] ADK + Elastic MCP hello-world working locally (one tool call round-trip)
- [ ] Synthetic data generation script (with deterministic name-variant generator)
- [ ] Bulk-ingest all four indices with name analyzers + E5-multilingual inference pipeline
- [ ] Verify analyzers via `_analyze` endpoint for the §7 stress cases
- [ ] Domain-voice outreach kickoff (Red Cross RFL / CrisisCleanup / NamUs) — emails out

### Sprint 2 — Agent + Verifier UI (Week 2, ending ~2026-05-30)
- [ ] Implement `transliterate_name`, `translate_text`, custom Agent Builder skills
- [ ] Wire ADK agent with full tool set; implement system prompt
- [ ] Implement `await_verifier_decision` long-running tool
- [ ] React verifier UI scaffold (Vite + Mapbox GL JS)
- [ ] Hero reunification-map component (live dots, arc animation, language flags)
- [ ] Candidate-match queue + Approve/Reject/Ask-more cards with side-by-side comparison
- [ ] WebSocket layer for agent → UI events
- [ ] End-to-end golden path (Spanish seeker → Carlos match → verifier approve → dispatch) works locally

### Sprint 3 — Polish + Evals + Deploy (Week 3, ending ~2026-06-06)
- [ ] Build 50-case eval set + scoring script; pin numbers in README
- [ ] Coordinator triage flow (ES|QL aggregation, dashboard view)
- [ ] Standing-query watcher Cloud Run job
- [ ] Deploy agent + UI to Cloud Run; verify hosted end-to-end
- [ ] Architecture diagram (single image, video-ready)
- [ ] Native Spanish speaker reviews ES strings end-to-end
- [ ] Cold-start test: scale to zero, hit fresh URL, fix if >15s
- [ ] Cost-story slide (per-case marginal cost)

### Submission Week (2026-06-07 to 2026-06-11)
- [ ] Record 3-minute demo video (script in §11). Re-record until clean.
- [ ] Pre-recorded backup demo
- [ ] Write README (hook, criteria-mapping table, one-command deploy)
- [ ] Devpost submission: hook in description, video, hosted URL, GitHub repo
- [ ] MIT LICENSE at repo root; verify GitHub auto-detects
- [ ] Final preflight: live URL works in fresh unauthenticated browser

---

## 11. Demo Video Script (3 minutes)

### 0:00–0:20 — The Hook
*[Screen: news headline of a hurricane evacuation, then cut to María — a 68-year-old woman — looking at her phone outside a shelter]*

"When Hurricane Elena scattered Houston's evacuees across forty shelters, María couldn't find her grandson Carlos. The Red Cross has a registry. But Carlos was logged as 'Carlitos M.' at one shelter, 'Carlos Martinez' at another, and 'C. Martínez' at a third. María doesn't speak English. She just needs to know where Carlos is."

### 0:18 — Hero Shot
*[Cut to the live reunification map: Houston, shelter dots pulsing colour by language, a new arc lighting up between two dots labelled 0.91. This is the YouTube thumbnail moment.]*

### 0:20–1:00 — The Seeker Flow
*[Screen: ADK chat UI in Spanish]*
- María types her Spanish request
- Agent visibly extracts structured needs in Spanish
- 5+ Elastic MCP tool calls scroll past in the agent trace, each one a different name variant or index
- Agent surfaces three candidate matches with reasoning chains in Spanish

### 1:00–1:50 — The Verifier Gate (HITL)
*[Screen: React verifier UI]*
- Three candidate cards. Side-by-side comparison. Confidence scores.
- Verifier reads the agent's evidence chain, clicks **Approve** on the 0.91 match.
- Agent's "thinking" indicator resumes. Drafts a notification in English to the shelter coordinator and in Spanish to María. Dispatch logged.
- **This is where you point the camera at the approval modal. Pause for 2 seconds. Judges are told to look for human oversight; show them.**

### 1:50–2:20 — The Hard Case (Arabic Script)
*[Screen: someone off-camera asks (unscripted-feeling): "what about مُحَمَّد?"]*
- Agent shows it transliterated to Mohammed / Muhammad / Mohamed / Mohd
- Searches each variant + phonetic
- Surfaces a candidate at a different shelter
- This is the "agent handling something hard" moment that defeats the "scripted demo" reflex

### 2:20–2:40 — The Numbers
*[Screen: a stats slide]*
- 94% match precision @ confidence ≥ 0.8 on 50 held-out family-pair cases
- 5 languages supported in matching, including Arabic and Vietnamese with non-Roman input
- Median 6.2s end-to-end from seeker query to candidate surfaced
- Marginal cost per case: $0.04

### 2:40–2:55 — "Why It Matters" Close
"DisasterLens is what Red Cross Safe and Well, ICRC Restoring Family Links, and NamUs do today — manually, in English, one register at a time. With an Elasticsearch nervous system and a human verifier, it does it in any language, across every silo, in seconds. No one left behind."

### 2:55–3:00 — Architecture Slide
*[One clean image]* — "Gemini, Google Cloud ADK, Elastic Agent Builder MCP, Cloud Run. Open source — link in description."

---

## 12. Risk Register

| Risk | Impact | Mitigation |
|---|---|---|
| Elastic Cloud trial limits (index size, query rate, inference quota) | High | Use Serverless tier. Keep total docs under 1k. Cache inference embeddings on ingest, not query-time. Test in Sprint 1, not Sprint 3. |
| E5-multilingual / Jina inference endpoint unavailable on Serverless trial | High | Pre-flight in Sprint 1 Day 1. If unavailable: generate embeddings offline via Vertex AI and ingest as `dense_vector`. |
| Custom Agent Builder skills registration not GA on Serverless | Medium | Verify in Sprint 1 Day 1 against current Elastic docs. Fallback: implement same skills as Python functions in the agent and call `core_execute_esql` directly. |
| ADK long-running tool pattern more involved than expected | Medium | Spike it Sprint 2 Day 1 against the ADK codelab. Have a polling-based fallback ready but don't ship it unless forced. |
| Cloud Run cold-start spike during live judging | Medium | Min-instances=1 during judging window (small cost). Pre-recorded backup demo regardless. |
| Native-speaker review for Spanish strings not arranged | Medium | Identify a reviewer in Sprint 1; book a 30-minute slot in Sprint 3. Backup: use Cloud Translation back-translation as a quality signal. |
| Trying to add Vietnamese / Tamil and shipping nothing well | High | Strict scope: EN + ES are demo-quality. Arabic name-matching is *demoed* but the seeker interaction is in EN/ES. Other scripts are claimed-but-not-shown. |
| Video runs long | Low | Pre-write the script (above). Two dry runs. Cut aggressively. |
| Domain-voice outreach yields nothing | Low | If no live clip by Sprint 3, use a citation/quote from a published ICRC paper instead. Still strong. |

---

## 13. Eval Scoreboard (Numbers for the Video)

A held-out 50-case family-pair eval set, generated alongside the synthetic data with deterministic labels. Stored in `evals/family_pairs.jsonl`. Scoring script `evals/score.py` outputs:

| Metric | Target | Where it appears |
|---|---|---|
| Precision @ confidence ≥ 0.8 | ≥ 0.90 | Video 2:20, README header |
| Recall on transliterated/nickname subset | ≥ 0.70 | README |
| Median time-to-first-candidate | ≤ 10s | Video, README |
| Languages with at least one matched case | ≥ 5 | Video |
| Tool calls per reasoning chain (avg) | 5–8 | README architecture section |

The eval runs against the agent end-to-end (not just the analyzer) so it doubles as a regression suite.

---

## 14. Repository Structure

```
disasterlens/
├── LICENSE                          # MIT
├── README.md                        # D1 hook, D2 criteria table, hero image
├── pyproject.toml                   # uv-managed
├── .env.example
├── Dockerfile                       # agent
│
├── agent/
│   ├── __init__.py
│   ├── agent.py                     # ADK agent definition
│   ├── tools/
│   │   ├── elastic_tools.py         # wrappers over Elastic MCP
│   │   ├── name_tools.py            # transliterate, nickname expansion
│   │   ├── translation_tools.py     # Cloud Translation
│   │   ├── notification_tools.py    # mocked SMS / Slack
│   │   └── verifier_tools.py        # await_verifier_decision (long-running)
│   ├── prompts/
│   │   └── system_prompt.py
│   └── config.py
│
├── dispatcher/                      # React + Vite + Mapbox GL JS
│   ├── package.json
│   ├── src/
│   │   ├── App.tsx
│   │   ├── components/
│   │   │   ├── ReunificationMap.tsx   # the hero visual
│   │   │   ├── CandidateQueue.tsx
│   │   │   ├── CandidateCard.tsx      # side-by-side comparison
│   │   │   └── LanguageToggle.tsx
│   │   └── lib/ws.ts                  # agent ↔ UI events
│   └── Dockerfile
│
├── data/
│   ├── generate_synthetic_data.py     # incl. name-variant generator
│   ├── ingest_to_elastic.py
│   ├── index_mappings/
│   │   ├── shelter_rosters.json
│   │   ├── missing_person_reports.json
│   │   ├── reunification_cases.json
│   │   └── social_reports.json
│   ├── analysis/
│   │   └── nicknames.txt              # synonym graph file
│   └── sample_data/
│
├── evals/
│   ├── family_pairs.jsonl             # gold set
│   └── score.py                       # scoring script
│
├── docs/
│   ├── PRD.md                         # this file
│   ├── use_case.md                    # original brief
│   ├── outreach.md                    # domain-voice outreach log
│   ├── architecture.png
│   └── demo-screenshots/
│
└── scripts/
    ├── setup_elastic.sh
    └── deploy.sh
```

---

## 15. Key Dependencies

```
# Agent
google-adk>=1.14.0
google-cloud-aiplatform
google-cloud-translate
elasticsearch>=8.0.0
python-dotenv
httpx
unidecode                            # name folding helper

# UI (in dispatcher/package.json)
react, react-dom, vite
mapbox-gl
@types/mapbox-gl
```

---

## 16. Success Criteria (Definition of Done)

A submission meeting all of these is plausibly top-3 in the Elastic track:

- [ ] Spanish-speaking seeker → Carlos candidate match → verifier approve → multilingual dispatch (golden path works end-to-end on the live URL)
- [ ] At least one **non-Roman-script** matching case demoed in the video
- [ ] 5+ Elastic MCP tool calls per reasoning chain, visibly logged
- [ ] Verifier gate shown explicitly on camera (long-running tool pattern)
- [ ] Standing-query re-fire demonstrated (new roster entry triggers callback)
- [ ] Held-out 50-case eval with precision ≥ 0.90 @ confidence ≥ 0.8 — numbers on screen
- [ ] Hero reunification-map visual is the YouTube thumbnail
- [ ] At least one domain-voice quote (live clip OR written quote OR cited paper) in README
- [ ] Native-Spanish-speaker review on ES strings
- [ ] Deployed on Cloud Run; cold-start <15s
- [ ] Public GitHub repo; MIT license auto-detected; README with D1 hook + D2 criteria table + one-command deploy
- [ ] 3-minute video follows the §11 script; pre-recorded backup exists
- [ ] Devpost submission complete; Elastic track selected

---

## 17. What Makes This a Winner

1. **Elastic isn't the data store — it's the language model of names.** Fuzzy + phonetic + transliteration + nickname graph + semantic, composed by the agent. Remove Elastic and the agent is mute.
2. **The mission is intrinsically multilingual.** Other submissions bolt on a translation feature. DisasterLens fails without multilingual matching by definition.
3. **HITL is the showcase, not the checkbox.** The verifier gate is *why* the system is trustworthy enough to deploy. ADK long-running tools make it architecturally clean.
4. **Real-world programs to reference.** Red Cross Safe and Well, ICRC RFL, NamUs. The judges aren't being asked to imagine a beneficiary; the beneficiary already has a name.
5. **Numbers, not nouns.** A 50-case eval gives the video a 2-second screen of precision/recall/latency that 95% of submissions won't have.
6. **One hero visual.** The reunification map is what the judge remembers an hour later.
