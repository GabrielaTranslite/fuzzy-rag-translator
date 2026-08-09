import json
from rapidfuzz import process, fuzz

# Importing TM as a list
def load_translation_memory(file_path: str):
    with open(file_path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f]

def fuzzy_retrieval(translation_memory: list, retrieved_string: str, top_n: int):
    """Retrieve the top N fuzzy matches from the translation memory for a given string."""
    # Building the list of source strings to reuse it for every query
    sources = [entry["source"] for entry in translation_memory]
    # Using rapidfuzz's process.extract to get the top N matches
    matches = process.extract(retrieved_string, sources, scorer=fuzz.ratio, limit=top_n)
    return [(score, translation_memory[index]) for _, score, index in matches]

def main() -> None:
    # Small smoke test, runs only when you execute this file directly
    tm = load_translation_memory("data/tm/translation_memory.jsonl")
    results = fuzzy_retrieval(tm, "Click on Victoria", top_n=3)
    for score, record in results:
        print(f"{score:.1f}  {record['source']}  ->  {record['target']}")

def tm_retrieval(tm: list,new_source: str, top_n: int = 1):
    """Search the loaded TM and return the best match fields."""
    score, record = fuzzy_retrieval(tm, new_source, top_n=1)[0]
    return score, record["source"], record["target"]


if __name__ == "__main__":
    main()
