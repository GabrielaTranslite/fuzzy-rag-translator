from openai import OpenAI
from retrieve import tm_retrieval 

PROMPTS = {
    "v1_only_different": """You are a professional video games translator that translates text from English to {target_language}.
Use the approved translation as a reference for translating the new source into {target_language}.
Replace with a {target_language} translation only those words that are different from the reference. Do not translate words that are the same as the reference.
You must maintain the same formatting, tags, and placeholders as in the source text. Do not add any commentary or explanation.""",
    
    "v2_base": """You are a professional video game translator working from English to {target_language}.
You repair fuzzy translation-memory matches.
Produce the full {target_language} translation of the NEW source.
Start from the approved translation and change only the parts that the source edit requires.
Keep the unchanged parts identical to the approved translation.
The output must be a complete, fluent {target_language} sentence. Never leave any part in English.
Preserve all placeholders (for example $student_hp), tags, and formatting exactly as they appear.
Output only the {target_language} translation, with no commentary.""",

    "v3_agreement": """You are a professional video game translator working from English to {target_language}.
You repair fuzzy translation-memory matches.
Produce the full {target_language} translation of the NEW source.
Start from the approved translation and change only the parts that the source edit requires.
Keep the unchanged parts identical to the approved translation.
If the source edit changes gender, number, or person, update every dependent word so the whole sentence agrees.
The output must be a complete, fluent {target_language} sentence. Never leave any part in English.
Preserve all placeholders (for example $student_hp), tags, and formatting exactly as they appear.
Output only the {target_language} translation, with no commentary.""",

    "v4_source_changes": """You are a professional video game translator working from English to {target_language}.
You repair fuzzy translation-memory matches.
Produce the full {target_language} translation of the NEW source.
Compare the reference source with the new source. Keep only the parts whose English words are unchanged.
Re-translate every part whose English word changed, including forms of address (for example man vs lady), 
and any words that depend on them (for example he vs she, his vs her, him vs her).
Reference source (English): Mighty human, you have a sword.
Approved (Polish): Potężny człowieku, masz miecz.
New source (English): Young elf, you have a sword.
Correct output: Młody elfie, masz miecz.
If the source edit changes gender, number, or person, update every dependent word so the whole sentence agrees.
The output must be a complete, fluent {target_language} sentence. Never leave any part in English.
Preserve all placeholders (for example $student_hp), tags, and formatting exactly as they appear.
Output only the {target_language} translation, with no commentary.""",
}

def build_repair_messages(new_source: str, target_language: str, tm_source: str, tm_target: str, prompt_version: str) -> list:
    """Assemble the system + user messages for the repair call."""
    
    system = PROMPTS[prompt_version].format(target_language=target_language)

    user = f"""Reference source (English): {tm_source}
Approved translation ({target_language}): {tm_target}
New source (English): {new_source}"""

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
    
def call_repair(messages: list, model: str, client: OpenAI) -> str:
    """Send the messages to the API and return the translation."""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
    )
    return response.choices[0].message.content.strip()

def repair_segment(new_source, tm, target_language, prompt_version, model, client):
    """Orchestration: retrieve -> build messages -> call LLM -> log -> return."""
    score, tm_source, tm_target = tm_retrieval(tm, new_source)
    messages = build_repair_messages(new_source, target_language, tm_source, tm_target, prompt_version)
    output = call_repair(messages, model, client)
    return output, score

