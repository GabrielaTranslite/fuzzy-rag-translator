"""Context normalization for the translation memory and for queries.

Wesnoth uses an inline gettext context convention: a source string can carry a
disambiguation prefix separated by a caret, for example "female^steadfast",
"race^Horse" or "race+female^Horse". Everything before the first caret is the
context (gender, race, unit type, ...); everything after it is the text that is
actually shown to the player. In these .po files the context lives inline in the
msgid, not in the standard msgctxt field, so polib does not split it for us.

For fuzzy and semantic retrieval we want to match on the visible text, not on
the context prefix, otherwise the prefix inflates fuzzy distance for short
strings and adds noise to the embeddings. The indexed sources and the incoming
queries must therefore be stripped in exactly the same way. This module is the
single source of truth for that rule: import strip_context wherever
normalization is needed so the two sides can never drift apart.
"""

from typing import Iterable


def strip_context(text: str) -> tuple[str, str]:
    """Split a Wesnoth "context^text" string into (context, text).

    Splitting happens on the first caret only, which matches the gettext rule
    that the context is everything before the first separator (so a compound
    prefix like "race+female^Horse" yields context "race+female", text "Horse").
    When there is no caret the context is an empty string and the text is
    returned unchanged apart from whitespace trimming. A None input is treated
    as an empty string so callers do not have to guard against it.
    """
    if not text:
        return "", ""
    if "^" in text:
        context, _, rest = text.partition("^")
        return context.strip(), rest.strip()
    return "", text.strip()


def format_context_hint(context: str) -> str:
    """Turn a gettext context prefix into one hint line for the prompt.

    Empty context yields an empty string (no line added). Shared by the
    scratch and repair prompt builders so the wording can never drift apart.
    """
    if not context:
        return ""
    return f"Grammatical/domain context for the new source: {context}"


def normalize_records(
    records: Iterable[dict],
    text_field: str,
    norm_field: str,
    context_field: str,
) -> list:
    """Add normalized fields to each record in place and return them as a list.

    For every record the value of text_field is split with strip_context. The
    visible text goes to norm_field (this is what you index and search on) and
    the context prefix to context_field. The original value in text_field is left
    untouched so it stays available for display and for tracing back to the .po
    entry. The function does not deduplicate: two entries that differ only by
    context collapse to the same norm_field value but keep different targets, and
    that is intentional for a translation memory.
    """
    result = []
    for record in records:
        context, text = strip_context(record.get(text_field, ""))
        record[norm_field] = text
        record[context_field] = context
        result.append(record)
    return result


if __name__ == "__main__":
    # Small self-test, runs only when you execute this file directly.
    samples = [
        "female^steadfast",
        "race+female^Horse",
        "Pirate Flagship",
        "^leading caret",
        "",
    ]
    for s in samples:
        print(f"{s!r:30} -> {strip_context(s)}")
