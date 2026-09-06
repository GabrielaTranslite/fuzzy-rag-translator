# Fuzzy-Repair MT Assistant

A retrieval-augmented translation assistant for video game localization. It takes a
new or slightly changed English game string, finds the closest **human-approved**
translation in a translation memory, and asks an LLM to **repair only the part that
changed**, keeping the approved wording everywhere else. In short: edit, do not
rewrite.

This project was built for the LLM Zoomcamp capstone. It is written so that a
reviewer who did not take the course, and who does not read Polish, can understand
the problem, the data, and the system. Every Polish example below comes with a
literal English gloss.

> Status at a glance: retrieval + LLM evaluation done, a working Streamlit app,
> an automated ingestion pipeline (Prefect), live monitoring (Grafana), and a full
> Docker Compose stack. See the [Evaluation criteria map](#evaluation-criteria-map).

---

## Why this project exists (for readers outside games and translation)

**Why translation memory and RAG.** Game localization is not generic translation.
The same English word must be rendered differently depending on the world of the
game: a medieval setting, a far-future sci-fi setting, a high-fantasy world, or an
antiquity setting each have their own register and terminology. Human translators
keep a **translation memory** (TM): a database of source sentences they already
translated and that were reviewed and approved. Reusing it keeps terminology and
tone consistent across a huge project. That memory is exactly the "knowledge base"
that a RAG system should retrieve from, so that the model answers in the voice of
the game, not in a generic voice.

**Why the fuzzy layer.** When a new string is almost identical to one already in
the memory (a **fuzzy match**), retranslating it from scratch is wasteful and risky:
a from-scratch model tends to rewrite wording a human already approved, drift on
game-specific terminology, and break consistency. If we have a great, human-approved
match, we want to **keep it** and change only what the new source actually changed.

**Why "repair" and not "translate".** That "change only what changed" step is the
core idea, known in the field as fuzzy-match repair, Neural Fuzzy Repair, or
automatic post-editing. The system retrieves the approved pair and instructs the
LLM to edit the minimum. This preserves human work, saves cost, and keeps the
output consistent.

**Who it helps.** Localization teams and translation project managers who work with
large, evolving game texts and want machine assistance that respects their approved
translations instead of overwriting them.

---

## The data

- Source: **The Battle for Wesnoth**, an open-source fantasy strategy game, and its
  human English to Polish translations (gettext `.po` files: `msgid` is English,
  `msgstr` is the approved Polish).
- Five text domains (help, campaign, manual, tutorial, units), **2852** approved
  segments after filtering.
- Quality gate: only entries that are translated and **not** flagged `fuzzy` by the
  translators are used, so the memory contains only reviewed, approved translations.
- A Wesnoth-specific quirk handled here: some sources carry an inline gettext
  context prefix before a caret, for example `female^Drake Arbiter` or
  `race+female^Horse`. These are disambiguation hints, not text to translate. They
  are stripped into a separate `context` field at ingest and reused as a grammatical
  hint (see [normalization](#the-flow)).
- **License: GPL v2+**. The `.po` files are redistributed here under that license
  with `data/COPYING` retained and attribution to the Wesnoth translation teams.
  `scripts/fetch_data.py` can also re-download them from a pinned upstream tag.

---

## What it does (the flow)

```
English source
   |
   v
strip context prefix        (normalization.py: "female^Drake Arbiter" -> context "female", text "Drake Arbiter")
   |
   v
fuzzy retrieval             (rapidfuzz edit distance over the approved sources, top match + score 0..100)
   |
   +--- score >= 55 ------>  REPAIR: give the LLM the approved English+Polish pair and the
   |                          context hint, ask it to edit only what changed  (edit, not rewrite)
   |
   +--- score <  55 ------>  FALLBACK: no trustworthy match, translate from scratch with the hint
   |
   v
output + metrics (retrieval score, preservation) + user feedback
   |
   v
Postgres  ->  Grafana dashboard (live monitoring)
```

The **55** threshold is not a guess. It is derived from the evaluation results:
below it, repairing an unrelated match hurts quality; above it, repair helps and
the gain grows with the match score. See
`eval/02_llm_eval.ipynb`, section "Choosing a retrieval-quality threshold".

A semantic retriever (Qdrant + sentence embeddings) is also implemented and
evaluated (see `eval/01_retrieval_eval.ipynb`), but the live product uses fuzzy
(edit-distance) retrieval, because for fuzzy-match repair the textually closest
approved segment is the right signal and it gives a clean, interpretable threshold.

---

## Example (no Polish needed to follow it)

A grammatical-gender case (`f09`). Polish marks gender on nouns and adjectives
through word endings, so the correct form cannot be guessed from the English name
alone; the approved game term has to be known.

| step | value | gloss |
|------|-------|-------|
| New English source | `Drake Arbiter` (needs the feminine form) | a unit name |
| From scratch | `Drake Arbiter` | left untranslated, the model did not know the term |
| Repair retrieves | approved `Smoczy strażnik` | the masculine form already in the memory |
| Repaired output | `Smocza strażniczka` | correct feminine form |

Only the endings change: Smocz**y** strażni**k** (masculine) becomes
Smocz**a** strażni**czka** (feminine). The approved term is reused; the gender is
fixed. That is the whole idea on one line.

When no close match exists, the app says so and translates from scratch instead of
trusting a bad match. Both behaviors are visible in the app.

---

## Screenshots and demo

<!-- Add images to docs/img/ and a short screen recording. -->
<!-- In Streamlit you can record a video from the top-right menu (see the LLM Zoomcamp docs), then drag-drop it into the GitHub README editor. -->

- Live repair UI: `![alt text](image.png)`
- Evaluation explorer: `docs/img/eval_explorer.png`
- Monitoring dashboard: `docs/img/monitoring.png`

_(Screenshots to be added.)_

---

## Results (highlights)

Evaluation over a hand-built gold set of 75 cases (fuzzy_real, edited, invented),
scored with **chrF** (character-level similarity to a human reference, 0 to 100)
and a **preservation** metric (how much of the approved wording was kept, 0 means
kept verbatim). Full detail and plain-language commentary in `eval/02_llm_eval.ipynb`.

Three-condition ladder (each rung adds one ingredient), overall chrF:

| condition | what it has | chrF |
|-----------|-------------|------|
| scratch | translate blind | 54.7 |
| scratch_context | + grammatical hint | 58.5 |
| repair | + retrieved approved pair | **76.7** |

The clearest win is grammatical gender: chrF goes 18 -> 39 -> 92 across the ladder.
Preservation on well-matched cases is about 0.2 (the approved wording is kept while
the new source is still translated correctly), which is the quantitative statement
of "edit, not rewrite".

---

## Quick start

Full instructions, environment variables, and troubleshooting are in
**[SETUP.md](SETUP.md)**. The short version:

```bash
cp .env.example .env          # then fill in OPENAI_API_KEY
docker compose up -d          # qdrant, postgres, app, grafana
python scripts/seed_monitoring.py   # optional: seed the dashboard with eval data
```

- App: http://localhost:8501
- Monitoring (Grafana): http://localhost:3000 (login from `GRAFANA_ADMIN_PASSWORD`)

You need Docker, and an OpenAI API key in `.env`. To run the app without Docker,
see SETUP.md.

---

## Evaluation criteria map

Where each LLM Zoomcamp criterion is addressed, so reviewers can find things fast.

| Criterion | Where |
|-----------|-------|
| Problem description | This README (Why this project exists, The data, The flow) |
| Retrieval flow | `src/retrieve.py` (fuzzy + semantic), `app.py` (live repair uses retrieval + LLM) |
| Retrieval evaluation | `eval/01_retrieval_eval.ipynb` (fuzzy vs semantic, hit-rate and MRR by edit type) |
| LLM evaluation | `eval/02_llm_eval.ipynb` (three-condition ladder, chrF + preservation, threshold derivation) |
| Interface | `app.py` (Streamlit: Live repair + Evaluation explorer) |
| Ingestion pipeline | `scripts/build_tm_flow.py` (Prefect flow: ingest + index), `src/ingest.py`, `scripts/fetch_data.py` |
| Monitoring | `docker-compose.yaml` (Grafana + Postgres), `grafana/provisioning/` (9-panel dashboard), feedback captured in the app |
| Containerization | `docker-compose.yaml` (qdrant, db, app, grafana), `Dockerfile` |
| Reproducibility | pinned `requirements.txt`, committed data under GPL, `SETUP.md`, `db/init/01_schema.sql` |
| Best practices | query rewriting via context normalization (`src/normalization.py`); semantic retriever evaluated in `eval/01`; see the note below |

Best-practices note (honest scope): user-query rewriting is implemented, because
the caret context is normalized and reused as a grammatical hint. A semantic
retriever is implemented and evaluated, but the two retrievers are not fused into a
single hybrid ranker, so this is described as "fuzzy used, semantic evaluated"
rather than claimed as hybrid search.

---

## Project structure

```
app.py                     Streamlit app (Live repair + Evaluation explorer)
src/
  ingest.py                parse .po -> normalized TM (data/tm/translation_memory.jsonl)
  normalization.py         strip_context / context-hint helper (single source of truth)
  retrieve.py              fuzzy_retrieval (product) + semantic_retrieval (evaluated)
  repair.py                repair prompts + LLM call (edit the approved target)
  translate.py             from-scratch translation (baseline + fallback path)
  index_qdrant.py          build the semantic index (used in eval / pipeline)
  db.py                    Postgres logging (schema + log_inference / log_feedback, JSONL fallback)
eval/
  01_retrieval_eval.ipynb  fuzzy vs semantic retrieval evaluation
  02_llm_eval.ipynb        LLM evaluation ladder + metrics + threshold + reviewer notes
  gold_set.jsonl           hand-built gold set (75 cases)
  llm_runs.jsonl           cached model outputs (feeds the Evaluation explorer + seed)
scripts/
  fetch_data.py            download the .po from upstream (pinned tag)
  build_tm_flow.py         Prefect flow: ingest -> index
  seed_monitoring.py       load eval results into Postgres so the dashboard is not empty
db/init/01_schema.sql      canonical monitoring schema (repair_logs)
grafana/provisioning/      Grafana datasource + dashboard as code
data/                      the .po sources, COPYING, generated TM
docker-compose.yaml        qdrant + postgres + app + grafana
Dockerfile                 app image
```

---

## License

Code is under the MIT license. The bundled Wesnoth translation data in `data/` is
under **GPL v2+** (see `data/COPYING`), courtesy of the Wesnoth project and its
volunteer translators.
