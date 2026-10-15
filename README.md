# AUTOSAR HLD Analysis Assistant (Pilot)

Secure, locally hosted assistant for extracting, organising, searching and validating
architectural knowledge from large **AUTOSAR High-Level Design (HLD)** PDFs.

The pilot implements the case-study workflow end to end: ingestion → section-aware
chunking → embeddings → local vector store → cited Q&A → consistency checks →
revision comparison → structured export, with human review retained on every result.

- **UI:** Streamlit (`ui/`) — pilot interface, 6 working pages
- **API:** FastAPI (`api/`) — modular HTTP endpoints, interactive docs at `/docs`
- **LLM:** any OpenAI-compatible endpoint — Groq, OpenAI, Ollama or a private
  service; works with **no LLM at all** (grounded retrieval mode)
- **Storage:** SQLite (audit data) + ChromaDB (vectors), both local under `data/`

---

## 1. Contents

1. [Capabilities](#2-capabilities)
2. [Prerequisites](#3-prerequisites)
3. [Install](#4-install)
4. [Run the project](#5-run-the-project)
5. [Demo walkthrough (sample documents)](#6-demo-walkthrough-sample-documents)
6. [LLM configuration (Groq / OpenAI / Ollama / none)](#7-llm-configuration)
7. [UI page guide](#8-ui-page-guide)
8. [HTTP API reference](#9-http-api-reference)
9. [Consistency checks](#10-consistency-checks)
10. [Exports](#11-exports)
11. [Configuration reference](#12-configuration-reference)
12. [How it works (pipeline)](#13-how-it-works-pipeline)
13. [Data and storage](#14-data-and-storage)
14. [Tests, lint, type checks](#15-tests-lint-type-checks)
15. [Project layout](#16-project-layout)
16. [Troubleshooting](#17-troubleshooting)
17. [Scope and governance](#18-scope-and-governance)

---

## 2. Capabilities

| Capability | Where |
| --- | --- |
| PDF upload, section/table/metadata extraction, scanned-page detection | `ui/pages/1_Ingest.py`, `src/hld_assistant/ingest/` |
| Section-aware chunking with page + section breadcrumbs | `ingest/chunker.py` |
| Local embeddings (BGE/fastembed, sentence-transformers, hashing) + persistent ChromaDB vector store | `index/` |
| Natural language search and cited Q&A (page + section citations) | `ui/pages/2_Ask.py`, `rag/` |
| Component / interface / port / signal / runnable / BSW inventory | `ui/pages/3_Inventory.py`, `analysis/entities.py` |
| Mismatch, completeness and terminology checks (7 rules) | `ui/pages/4_Checks.py`, `analysis/checks.py` |
| Revision comparison (entities, sections, section text) | `ui/pages/5_Compare.py`, `analysis/compare.py` |
| CSV / JSON / Markdown export | `ui/pages/6_Export.py`, `export/exporter.py` |
| Engineer review records, audit storage (SQLite) | `db.py` |
| Modular HTTP API | `api/main.py` (FastAPI) |

---

## 3. Prerequisites

- **Python 3.11+** (tested on 3.14, Windows)
- ~1 GB free disk (ChromaDB/onnxruntime + embedding model download on first run)
- Optional: a **Groq API key** (<https://console.groq.com/keys>) for generated answers
- Optional: a local **Ollama**/vLLM/LM Studio endpoint
- A PDF to analyse — or use the included synthetic samples

Run all commands from the project root (`Tata-Tech/`).

## 4. Install

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional, for the quality gates only:

```powershell
pip install ruff mypy          # or:  pip install -e ".[dev]"
```

## 5. Run the project

**Start the UI (main application):**

```powershell
streamlit run ui/app.py
```
→ opens at <http://localhost:8501>

**Start the HTTP API (optional, can run alongside the UI):**

```powershell
uvicorn api.main:app --port 8000
```
→ interactive Swagger docs at <http://localhost:8000/docs>

**Generate the sample documents (optional):**

```powershell
python sample_data\generate_sample.py
# writes sample_data\hld_revision_a.pdf and hld_revision_b.pdf
```

**Enable a hosted LLM (recommended — otherwise answers stay in retrieval mode):**

```powershell
copy .env.example .env        # then paste your Groq key into .env
streamlit run ui\app.py
```

Stop with `Ctrl+C`; leave the virtual environment with `exit`.

## 6. Demo walkthrough (sample documents)

The repository ships two synthetic revisions with deliberate design defects, so the
whole workflow can be demonstrated without real (confidential) HLDs:

```powershell
python sample_data\generate_sample.py
streamlit run ui\app.py
```

| Step | Page | What to do | What you should see |
| --- | --- | --- | --- |
| 1 | **Home** | - | Document count, indexed chunks, embedder, LLM status |
| 2 | **Ingest** | Upload `hld_revision_a.pdf`, version `A`, status `approved` → *Ingest document* (repeat for revision B, status `draft`) | pages → chunks → entities counts; heading/table counts |
| 3 | **Ask** | *"Which components and interfaces are involved in the vehicle speed flow?"* | With a Groq key: an answer with `[1] [2] …` citations. Without one: grounded evidence excerpts (page + section + score) and no generated claims |
| 4 | **Inventory** | Pick revision A, browse kinds (`Component`, `Port`, `Interface`, `Signal`, `Runnable`, `BswModule`, …) | table of entities with page + section, CSV download |
| 5 | **Checks** | Pick revision B → *Run checks* | 5 findings: `port_direction_conflict`, `entity_kind_conflict`, `terminology_variance`, `undefined_reference`, `empty_section`, each with evidence |
| 6 | **Compare** | Revision A vs B → *Compare* | added: `TractionControlAssist`, `TractionRequest`, `SteeringAnglePreprocessor`, …; removed: `SteeringAngleReader`; added sections `2.2`, `4.3`; removed `9 Open questions`; changed text in `7 Diagnostics and configuration` |
| 7 | **Export** | Pick a document → *Generate export package* | CSV/JSON/Markdown files, downloadable from the page |

Sample defects intentionally embedded: a port described as both provided and
required, the same name used as two architecture kinds, `ChassisSignalService` vs
`Chassis_SignalService` spelling drift, a dependency on a component that is never
defined, and near-empty sections.

> The `data/` directory starts empty — generate and ingest both revisions
> (steps 1–2) before using Ask, Checks, or Compare.

## 7. LLM configuration

Q&A always retrieves first; the LLM only synthesises the answer from retrieved
evidence with citations. **No LLM → no hallucination:** the app answers with
grounded evidence excerpts and says so.

### Groq (recommended hosted option)

```powershell
copy .env.example .env
notepad .env
#   HLD_LLM_PROVIDER=groq
#   GROQ_API_KEY=gsk_...
streamlit run ui\app.py
```

or entirely from the shell:

```powershell
$env:HLD_LLM_PROVIDER = "groq"
$env:GROQ_API_KEY     = "gsk_..."       # https://console.groq.com/keys
streamlit run ui\app.py
```

Preset: endpoint `https://api.groq.com/openai/v1`, model
`openai/gpt-oss-120b`. The Home page shows
`LLM ready: openai/gpt-oss-120b via groq` — or a precise reason
(`No API key: set GROQ_API_KEY …`, `401 Invalid API Key`, connection refused).

### OpenAI

```powershell
$env:HLD_LLM_PROVIDER = "openai"
$env:OPENAI_API_KEY   = "sk-..."
streamlit run ui\app.py
```

### Ollama or any private OpenAI-compatible endpoint

```powershell
$env:HLD_LLM_BASE_URL = "http://localhost:11434/v1"
$env:HLD_LLM_MODEL    = "llama3.2"
streamlit run ui\app.py
```

### Force retrieval-only mode

```powershell
$env:HLD_LLM_ENABLED = "0"     # or HLD_LLM_ENABLED=0 in .env
```

**Rules:** shell environment beats `.env`; `HLD_LLM_*` overrides beat provider
presets; `.env` is git-ignored (never commit keys). `.env` is read from the
working directory (override with `HLD_ENV_FILE`).

## 8. UI page guide

| Page | Purpose | Key actions |
| --- | --- | --- |
| **Home** (`ui/app.py`) | System status and document list | LLM/embedder status, index health warning, governance note |
| **1 Ingest** | Controlled document ingestion | upload PDF, version label, `draft/approved/deprecated`, duplicate detection, reindex, delete |
| **2 Ask** | Natural language search & cited Q&A | filter by document(s), retrieval depth slider, evidence panel, review verdict (`accepted/corrected/rejected/needs discussion`), query history |
| **3 Inventory** | Extracted architecture entities | filter by entity kind, occurrence counts, per-kind and full CSV download |
| **4 Checks** | Mismatch & completeness analysis | run checks, severity filter (error/warning/info), evidence with page + section, findings CSV, per-finding review |
| **5 Compare** | Revision comparison | pick baseline/candidate, entity & section diffs, unified text diff, comparison export |
| **6 Export** | Structured export package | generate CSV/JSON/Markdown bundle, download files |

## 9. HTTP API reference

Base URL example: `http://localhost:8000` — Swagger UI at `/docs`.

| Method & path | Purpose | Body / notes |
| --- | --- | --- |
| `GET /` | Service banner | - |
| `GET /health` | Status: documents, index, embedder, LLM | - |
| `GET /documents` | List ingested documents | - |
| `POST /documents` | Upload + ingest a document | `multipart/form-data`: `file`, `version_label`, `status` |
| `DELETE /documents/{id}` | Remove document, chunks, vectors | - |
| `POST /search` | Retrieval only | `{"question": "...", "doc_ids": null, "k": 6}` |
| `POST /ask` | Cited answer | same body; returns `mode`, `answer`, `citations`, `passages` |
| `GET /documents/{id}/inventory` | Entities grouped by kind | - |
| `POST /documents/{id}/checks` | Run consistency checks | returns findings |
| `POST /compare` | Compare two revisions | `{"doc_id_a": "...", "doc_id_b": "..."}` |
| `POST /documents/{id}/export` | Write export package | returns file paths |
| `GET /exports/{name}` | Read a written export file | plain text |
| `GET /queries` | Q&A history | `?limit=50` |
| `POST /reviews` | Record engineer review | `{"target": "answer", "target_id": "...", "verdict": "accepted", "comment": "...", "reviewer": "..."}` |
| `GET /reviews` | Review history | `?limit=100` |

Example:

```powershell
curl -X POST "http://localhost:8000/ask" -H "Content-Type: application/json" `
     -d '{"question":"Which component publishes VehicleSpeed?","k":5}'
```

## 10. Consistency checks

| Rule | Severity | Detects |
| --- | --- | --- |
| `port_direction_conflict` | error | a port claimed as provided/output in one place and required/input in another |
| `entity_kind_conflict` | error | the same name used as two different architecture kinds |
| `terminology_variance` | warning | the same identifier spelled differently (`ChassisSignalService` vs `Chassis_SignalService`) |
| `undefined_reference` | warning | a name referenced with a dependency verb but never defined in tables/sections |
| `signal_without_interface` | info | a signal never associated with an interface |
| `duplicate_definition` | info | an entity defined on several pages |
| `empty_section` | info | headings with little or no content |

Every finding carries evidence (page, section, quote), a suggestion and an
`open` status that reviews can act on. Results are persisted in SQLite.

## 11. Exports

`POST /documents/{id}/export` (or the Export page) writes into `data/exports/`:

| File | Content |
| --- | --- |
| `<name>_report.md` | Human-readable report: inventory, findings, Q&A history, governance footer |
| `<name>_report.json` | Same content, machine-readable |
| `<name>_inventory.csv` | All entities with kind, page, section, occurrences |
| `<name>_entities.csv` | Raw entity extraction incl. context and confidence |
| `<name>_findings.csv` | Flattened findings with evidence |
| `<revA>_vs_<revB>_comparison.md` / `.json` | Revision diff (Compare page) |

## 12. Configuration reference

All settings are environment variables (or `.env` entries). Defaults shown.

| Variable | Default | Purpose |
| --- | --- | --- |
| `HLD_ENV_FILE` | `./.env` | Alternate `.env` path |
| `HLD_DATA_DIR` | `./data` | Root for uploads, DB, vectors, exports |
| `HLD_DB_PATH` | `<data>/hld.sqlite3` | SQLite location |
| `HLD_VECTOR_DIR` | `<data>/vectors` | ChromaDB location |
| `HLD_EXPORT_DIR` | `<data>/exports` | Export output |
| `HLD_LLM_PROVIDER` | `custom` | `groq` \| `openai` \| `ollama` \| `custom` — fills endpoint/model/key |
| `GROQ_API_KEY` / `OPENAI_API_KEY` | - | Provider key (or `HLD_LLM_API_KEY`) |
| `HLD_LLM_BASE_URL` | provider preset | Endpoint override (default `http://localhost:11434/v1`) |
| `HLD_LLM_MODEL` | provider preset | Model override (default `llama3.2`) |
| `HLD_LLM_TIMEOUT` | `90` | Seconds per generation |
| `HLD_LLM_ENABLED` | `1` | `0` forces retrieval mode |
| `HLD_EMBEDDER` | `auto` | `auto` → sentence-transformers → fastembed → hashing |
| `HLD_EMBEDDING_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | sentence-transformers model |
| `HLD_FASTEMBED_MODEL` | `BAAI/bge-small-en-v1.5` | ONNX model (no torch needed) |
| `HLD_HASHING_DIM` | `512` | Dimension of the offline fallback embedder |
| `HLD_TOP_K` | `6` | Passages retrieved per query |
| `HLD_CHUNK_CHARS` | `1200` | Maximum chunk size |
| `HLD_CHUNK_OVERLAP` | `200` | Overlap between adjacent chunks |
| `HLD_APP_TITLE` | `AUTOSAR HLD Analysis Assistant` | UI header |
| `HLD_PROJECT` | `default` | Project label shown in the UI |

Changing `HLD_EMBEDDER`/model creates a different vector collection: use
**Reindex** on the Ingest page (Home warns while the index is out of date).

## 13. How it works (pipeline)

1. **Upload** an approved HLD PDF (`services.ingest`).
2. **Extract** text, ruled tables (parsed then redacted from the text flow),
   numbered heading tree, PDF metadata; scanned pages are detected and flagged.
3. **Chunk** by section: every chunk carries `section_path`, `page_start/page_end`,
   `kind` (text/table) and a stable id.
4. **Embed** with the configured embedder and **upsert** into ChromaDB
   (explicit embeddings only — no hidden model downloads inside Chroma).
5. **Retrieve** per query: vector similarity (70%) + lexical overlap (30%),
   optionally filtered to selected documents.
6. **Generate** with a controlled system prompt: answer only from context, cite
   `[n]`, refuse when evidence is insufficient; citations are validated against
   the retrieved set. If the LLM is unreachable → grounded excerpts only.
7. **Analyse**: entity recognition over prose and table columns → 7 rule-based
   checks; revision comparison diffs entities, sections and section text.
8. **Review & export**: engineer verdicts and findings stored in SQLite; export
   CSV/JSON/Markdown packages for downstream tooling.

## 14. Data and storage

```
data/
├── hld.sqlite3        # documents, chunks, entities, queries, reviews, findings
├── vectors/            # ChromaDB persistent store (one collection per embedder)
├── uploads/            # PDFs uploaded through the UI (created on first upload)
└── exports/            # generated export packages
```

`data/`, `.env` and virtualenvs are git-ignored. To reset the demo state, stop
the app and delete `data/`. Back up `data/` to preserve the audit trail.

## 15. Tests, lint, type checks

```powershell
pytest                                  # 31 tests (unit + end-to-end + UI smoke)
ruff check src api ui tests sample_data # lint
mypy src api                            # type check
```

Test coverage: PDF extraction and chunking, entity recognition, all consistency
rules, revision comparison, exporters, embedder behaviour, LLM/provider
configuration (incl. Groq), the full service workflow, and Streamlit page smoke
tests via `streamlit.testing.v1.AppTest`.

## 16. Project layout

```
api/main.py             FastAPI endpoints over the shared service layer
ui/
  app.py                Home page (entry point)
  common.py             shared Streamlit helpers
  pages/                1_Ingest, 2_Ask, 3_Inventory, 4_Checks, 5_Compare, 6_Export
src/hld_assistant/
  config.py             settings + provider presets + .env loader
  db.py                 SQLite persistence (audit data)
  services.py           orchestration used by both UI and API
  ingest/               PDF extraction and section-aware chunking
  index/                embedders and ChromaDB vector store
  rag/                  prompts, LLM client, hybrid retriever
  analysis/             entity recognition, checks, revision diff
  export/               CSV / JSON / Markdown exporters
sample_data/            synthetic two-revision HLD generator + generated PDFs
tests/                  31 tests
.env.example            configuration template (copy to .env)
requirements.txt        runtime dependencies
pyproject.toml          package metadata, ruff/mypy/pytest configuration
```

## 17. Troubleshooting

| Symptom | Cause / fix |
| --- | --- |
| Home shows *LLM offline - retrieval mode* | Key missing or endpoint down — check the reason shown; for Groq set `GROQ_API_KEY`; for Ollama start the server |
| `No API key: set GROQ_API_KEY …` | `.env` not loaded (wrong working directory) or key not pasted yet |
| `401 Invalid API Key` | Wrong/revoked key; regenerate at console.groq.com/keys |
| Home warns *vector index is out of date* | Embedder/model changed → **Reindex** on the Ingest page |
| Ingestion fails on a PDF | File corrupted/password-protected; try another export of the HLD |
| Search misses content from scanned pages | OCR is out of pilot scope — pages without a text layer are flagged on Ingest |
| `Address already in use` | Port taken: `streamlit run ui\app.py --server.port 8502` or `uvicorn api.main:app --port 8001` |
| First run is slow | Embedding model download + index build; subsequent starts are fast |
| No sentence-transformers / torch | Not needed — `auto` falls back to fastembed (ONNX) and then hashing |
| Tests can't import the package | Run `pytest` from the project root (or `pip install -e .`) |
| Reset everything | Stop the app, delete `data/`, re-ingest |

## 18. Scope and governance

**Out of scope in this pilot** (per case study): automatic approval of
architecture decisions, modification of source HLD documents, OCR for scanned
pages (detected and flagged instead), and replacement of formal architecture
governance.

**Governance:** AI-generated content is traceable to approved source material
(page and section citations) and must be reviewed by authorised engineering
specialists before use for compliance, design approval, software release or
vehicle validation.
