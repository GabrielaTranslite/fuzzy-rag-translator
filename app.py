import os
import sys
import json
import time
import uuid
import difflib

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI
from rapidfuzz.distance import Levenshtein
import sacrebleu

from normalization import strip_context, format_context_hint
from retrieve import load_translation_memory, fuzzy_retrieval
from repair import build_repair_messages, call_repair
from translate import build_translation_messages, call_translation
import db
import pricing

load_dotenv(override=True)  # project .env wins over any machine-level OPENAI_MODEL
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
TARGET_LANGUAGE = "Polish"
FUZZY_THRESHOLD = 55  # see eval/02_llm_eval.ipynb, "retrieval-quality threshold" section
ACCENT = "#FF8633"  # sampled from assets/logo.png

st.set_page_config(page_title="Fuzzy RAG Translator", page_icon="assets/logo.png", layout="wide")

st.markdown(
    f"""
    <style>
    div[data-testid="stMetricLabel"] {{ color: {ACCENT}; }}
    .stButton>button[kind="primary"] {{ background-color: {ACCENT}; border-color: {ACCENT}; }}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_client():
    return OpenAI()


@st.cache_resource
def get_tm():
    return load_translation_memory("data/tm/translation_memory.jsonl")


@st.cache_data
def get_gold():
    with open("eval/gold_set.jsonl", encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


@st.cache_data
def get_examples():
    try:
        with open("data/examples.json", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


@st.cache_data
def get_runs_by_case():
    with open("eval/llm_runs.jsonl", encoding="utf-8") as f:
        runs = [json.loads(l) for l in f if l.strip()]
    by_case = {}
    for row in runs:
        by_case.setdefault(row["case_id"], {})[row["condition"]] = row
    return by_case


def diff_html(baseline: str, candidate: str) -> str:
    """Word-level diff, candidate against baseline. Stdlib only, theme-safe colors."""
    a = baseline.split()
    b = candidate.split()
    sm = difflib.SequenceMatcher(a=a, b=b)
    out = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            out.append(" ".join(b[j1:j2]))
        elif tag in ("replace", "insert"):
            out.append(f'<span style="background:#d7f5dd">{" ".join(b[j1:j2])}</span>')
            if tag == "replace":
                out.append(f'<span style="background:#f8d7da;text-decoration:line-through">{" ".join(a[i1:i2])}</span>')
        elif tag == "delete":
            out.append(f'<span style="background:#f8d7da;text-decoration:line-through">{" ".join(a[i1:i2])}</span>')
    return " ".join(out)


@st.cache_resource
def _init_db():
    try:
        db.ensure_schema()
    except Exception:
        pass  # Postgres not reachable yet, log_inference/log_feedback will fall back to JSONL
    return True


_init_db()


col_logo, col_title = st.columns([1, 6])
with col_logo:
    st.image("assets/logo.png", width=120)
with col_title:
    st.title("Fuzzy RAG Translator")
    st.markdown(
        "This tool repairs fuzzy translation-memory matches: instead of translating "
        "game text from scratch, it finds the closest already-approved English to "
        "Polish translation and asks an LLM to edit only what changed, keeping the "
        "human wording everywhere else. **chrF** (0-100) scores similarity to the "
        "correct translation, higher is better. **Preservation** (0-1) scores how "
        "much of the reused approved wording survived, lower means it was kept "
        "rather than rewritten."
    )

mode = st.radio("Mode", ["Live repair", "Evaluation explorer"], horizontal=True)

st.divider()

if mode == "Live repair":
    input_source = st.radio("Input source", ["Type my own", "Try an example", "Pick from gold set"], horizontal=True)

    if input_source == "Type my own":
        source_text = st.text_area("English source", height=100)
    elif input_source == "Try an example":
        examples = get_examples()
        picked_ex = st.selectbox(
            "Example (a lightly edited game line; the app finds the approved match and repairs it)",
            examples,
            format_func=lambda s: (s[:70] + "...") if len(s) > 70 else s,
        )
        source_text = picked_ex or ""
    else:
        gold = get_gold()
        picked = st.selectbox(
            "Gold case",
            gold,
            format_func=lambda r: f"{r['case_id']} — {r['category']} — {r['query'][:60]}",
        )
        source_text = picked["query"] if picked else ""

    show_scratch = st.checkbox("Also show from-scratch translation", value=True)

    if "result" not in st.session_state:
        st.session_state.result = None

    if st.button("Repair", type="primary") and source_text.strip():
        context, query_norm = strip_context(source_text)

        hits = fuzzy_retrieval(get_tm(), query_norm, top_n=1)
        if not hits:
            st.warning("No TM matches found for this source.")
            st.session_state.result = None
        else:
            score, rec = hits[0]
            used_fallback = score < FUZZY_THRESHOLD
            gate_notice = None
            preservation = None

            if used_fallback:
                gate_notice = (
                    f"No sufficiently similar approved translation found "
                    f"(similarity {score:.1f} < {FUZZY_THRESHOLD}); translated from scratch instead."
                )
                messages = build_translation_messages(query_norm, TARGET_LANGUAGE, "baseline_context", context=context)
                t0 = time.time()
                output, usage = call_translation(messages, MODEL, get_client(), return_usage=True)
                latency_ms = int((time.time() - t0) * 1000)
            else:
                messages = build_repair_messages(
                    query_norm, TARGET_LANGUAGE, rec["source_norm"], rec["target"], "v4_source_changes", context=context
                )
                t0 = time.time()
                output, usage = call_repair(messages, MODEL, get_client(), return_usage=True)
                latency_ms = int((time.time() - t0) * 1000)
                preservation = round(Levenshtein.normalized_distance(output, rec["target"]), 3)

            scratch_output = None
            if show_scratch:
                scratch_messages = build_translation_messages(query_norm, TARGET_LANGUAGE, "baseline_scratch")
                scratch_output = call_translation(scratch_messages, MODEL, get_client())

            cost = pricing.cost_usd(MODEL, usage["prompt_tokens"], usage["completion_tokens"])
            record_id = str(uuid.uuid4())
            st.session_state.result = {
                "record_id": record_id,
                "source_text": source_text,
                "context": context,
                "context_hint": format_context_hint(context),
                "used_fallback": used_fallback,
                "gate_notice": gate_notice,
                "tm_source": rec["source_norm"],
                "tm_target": rec["target"],
                "retrieval_score": round(score, 1),
                "output": output,
                "scratch_output": scratch_output,
                "preservation": preservation,
                "latency_ms": latency_ms,
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "cost_usd": cost,
            }

            db.log_inference({
                "id": record_id,
                "source_text": source_text,
                "output_text": output,
                "tm_source": rec["source_norm"],
                "tm_target": rec["target"],
                "retrieval_score": round(score, 1),
                "preservation": preservation,
                "context": context,
                "model": MODEL,
                "latency_ms": latency_ms,
                "prompt_tokens": usage["prompt_tokens"],
                "completion_tokens": usage["completion_tokens"],
                "cost_usd": cost,
                "condition": "scratch_context" if used_fallback else "repair",
                "fell_back": used_fallback,
            })

    result = st.session_state.result
    if result:
        st.subheader("Result")

        if result["used_fallback"]:
            st.warning(result["gate_notice"])
            st.caption(f"Closest match found (not used): \"{result['tm_source']}\" -> \"{result['tm_target']}\" (score {result['retrieval_score']})")
            st.markdown(f"**Output (from scratch, with context hint):** {result['output']}")
        else:
            st.caption(f"Retrieved TM match (score {result['retrieval_score']}):")
            st.markdown(f"**Old source:** {result['tm_source']}  \n**Approved target from TM:** {result['tm_target']}")
            st.markdown("**LLM translation with TM access and fuzzy repair** (highlighted against the approved target):")
            st.markdown(diff_html(result["tm_target"], result["output"]), unsafe_allow_html=True)

        if result["context_hint"]:
            st.caption(f"Context hint used: {result['context_hint']}")

        if result["scratch_output"]:
            st.markdown(f"**From-scratch translation (no TM, no hint):** {result['scratch_output']}")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Retrieval score", result["retrieval_score"])
        m2.metric("Preservation", result["preservation"] if result["preservation"] is not None else "N/A")
        m3.metric("Latency", f"{result['latency_ms']} ms")
        m4.metric("Cost", f"${result['cost_usd']:.4f}")

        st.divider()
        st.markdown("**Feedback**")
        correction = st.text_input("Optional correction", key=f"correction_{result['record_id']}")
        c1, c2 = st.columns(2)
        with c1:
            if st.button("👍 Good", key=f"good_{result['record_id']}"):
                db.log_feedback(result["record_id"], "good", correction or None)
                st.success("Thanks for the feedback.")
        with c2:
            if st.button("👎 Needs fixing", key=f"bad_{result['record_id']}"):
                db.log_feedback(result["record_id"], "needs_fixing", correction or None)
                st.success("Thanks, logged.")

else:
    runs_by_case = get_runs_by_case()
    gold = get_gold()

    picked = st.selectbox(
        "Gold case",
        gold,
        format_func=lambda r: f"{r['case_id']} — {r['category']} — {r['edit_type']}",
    )

    if picked:
        case_runs = runs_by_case.get(picked["case_id"], {})
        reference = picked["reference"]
        repair_row = case_runs.get("repair")

        st.markdown("**Query (new translation):**")
        if repair_row:
            st.markdown(diff_html(repair_row["tm_source_norm"], picked["query"]), unsafe_allow_html=True)
            st.markdown(f"**Found TM hit (with fuzzy score {repair_row['retrieval_score']}):**")
            st.markdown(diff_html(picked["query"], repair_row["tm_source_norm"]), unsafe_allow_html=True)
            st.caption(f"Approved target from TM: {repair_row['tm_target']}")
        else:
            st.markdown(picked["query"])
        st.markdown(f"**Human Translator baseline:** {reference}")

        cols = st.columns(3)
        for col, condition in zip(cols, ["scratch", "scratch_context", "repair"]):
            row = case_runs.get(condition)
            with col:
                st.markdown(f"### {condition}")
                if not row:
                    st.info("No cached run for this condition.")
                    continue
                output = row["output"]
                st.markdown(diff_html(reference, output), unsafe_allow_html=True)
                chrf = sacrebleu.sentence_chrf(output, [reference]).score
                st.metric("chrF", round(chrf, 1))
                if condition == "repair":
                    preservation = round(Levenshtein.normalized_distance(output, row["tm_target"]), 3)
                    st.metric("Preservation", preservation)
                    st.metric("Retrieval score", row["retrieval_score"])

        st.caption(
            "chrF: 0-100 similarity between the output and the human reference, higher is better. "
            "Preservation: 0-1 edit distance from the output to the reused approved target, "
            "lower means the wording was kept rather than rewritten (repair arm only)."
        )
