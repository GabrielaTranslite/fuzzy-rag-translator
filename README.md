# Fuzzy Repair Translator

A project scaffold for a fuzzy TM RAG translator from English to Polish.

## Structure

- `data/`
  - `tm/`: translation memory store with approved EN→PL segments
  - `gold/`: gold evaluation pairs
  - `COPYING`: GPL Wesnoth license and attribution
- `src/`
  - `ingest.py`: parse `.po`, filter fuzzy entries, build TM store and embeddings
  - `retrieve.py`: fuzzy (edit distance), semantic, and rerank retrieval
  - `repair.py`: normalize source, build repair prompts, call LLM
  - `db.py`: log repair outputs to Postgres
- `eval/`: evaluation notebooks
- `app.py`: Streamlit interface
- `grafana/`: Grafana dashboard assets
- `Dockerfile`, `docker-compose.yaml`, `.env.example`

## Data

The knowledge base is a translation memory built from the Polish localization of The Battle for Wesnoth, an open-source strategy game. Its translations are made by human volunteer translators and released under the GPL (version 2 or later), which is what makes them safe to reuse here. See `data/COPYING` for the full license and attribution.

The source files are gettext `.po` files, where each entry pairs an English string (`msgid`) with its approved Polish translation (`msgstr`). I kept only entries that are actually translated and not marked `fuzzy`, so every pair in the memory has been confirmed by a human reviewer. Plural entries are skipped for now, because one English form maps to three Polish forms and does not fit a clean one-to-one segment model.

After filtering, the memory holds 1,624 segments. The English side has 195,374 characters across 33,119 words. The Polish side has 209,544 characters but only 29,427 words.

That gap is worth a second look. Polish ends up with about 7% more characters and 11% fewer words than English. It looks backwards at first, but it is what you would expect for this language pair: Polish has no articles and fewer short function words, so the word count drops, while its inflected forms run longer, so the character count rises. The numbers are a small sign that these are genuine human translations and not something mechanical.

Each record keeps the source and target text, the gettext context (`msgctxt`) where present, the extracted WML comment, the source references, any flags, and a stable `id` derived from the file, context, and source string.

### What a .po file is

If you have never worked with software translation, here is the short version. When a program needs to exist in more than one language, the text is not hardcoded. Developers mark each translatable string, and a tool collects those strings into a `.po` file. The format comes from GNU gettext, a localization system that has been around for decades. A translator then opens that file and writes the target language next to each original string.

One `.po` entry is one unit of translation. At its simplest it has two parts: `msgid`, the original English string, and `msgstr`, the translation. The file can also carry extra notes around each entry: where the string appears in the code, a short context label that tells apart two identical strings, and flags such as `fuzzy`, which marks a translation a tool guessed but no human has approved yet. Those notes are what let me keep only the reviewed, human-approved pairs.

### Fields in the translation memory

Loaded into a DataFrame, `translation_memory.jsonl` has one row per segment with these columns:

| Column | What it holds |
|---|---|
| `id` | Stable identifier of the segment, derived from the source file, context, and English string. The same input always produces the same id. |
| `source_file` | The `.po` file the segment came from, for example `pl_units.po`. |
| `source` | The English string (the `msgid`). |
| `target` | The approved Polish translation (the `msgstr`). |
| `msgctxt` | Optional gettext context that separates two identical English strings used in different places. Empty when there is none. |
| `wml_context` | The code comment extracted from the game, for example `[trait]: id=undead`. It hints at what kind of string this is. |
| `occurrences` | Where the string is used in the source, given as file and line references. |
| `flags` | Any gettext flags on the entry, such as `c-format`, which signals printf-style placeholders like `%d`. |

The analysis notebook adds a few extra columns on top of these, such as word-length buckets, but those exist only for exploration and are not part of the memory itself.

## Notes

- The project currently has `.po` files in `data/` and an existing `data/tm` JSONL store.
- `src/ingest.py` uses `polib` and `sentence-transformers` to generate embeddings.
- `docker-compose.yaml` includes `app`, `qdrant`, and `db` services.
