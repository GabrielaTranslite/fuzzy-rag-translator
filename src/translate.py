from openai import OpenAI
from repair import PROMPTS
from normalization import format_context_hint


def build_translation_messages(new_source: str, target_language: str, prompt_version: str, context: str = "") -> list:
    """Assemble the system + user messages for the translation call."""

    system = PROMPTS[prompt_version].format(target_language=target_language)

    user = f"""New source (English): {new_source}"""

    hint = format_context_hint(context)
    if hint:
        user += f"\n{hint}"

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def call_translation(messages: list, model: str, client: OpenAI, return_usage: bool = False):
    """Send the messages to the API and return the translation.
    With return_usage=True, return (text, {"prompt_tokens", "completion_tokens"})."""
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
    )
    text = response.choices[0].message.content.strip()
    if return_usage:
        u = response.usage
        return text, {"prompt_tokens": u.prompt_tokens, "completion_tokens": u.completion_tokens}
    return text


def translate_segment(new_source, target_language, prompt_version, model, client, context=""):
    """Orchestration: build messages -> call LLM -> return translation."""
    messages = build_translation_messages(new_source, target_language, prompt_version, context=context)
    output = call_translation(messages, model, client)
    return output
