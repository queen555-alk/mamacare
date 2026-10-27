"""Optional language-model step.

The assistant works without any LLM: it then returns the best guidance note
word for word, with its source. If ANTHROPIC_API_KEY is set (and the
`anthropic` package is installed), the notes are given to a model that
rewrites them as a short, simple answer. The model is told to use ONLY the
notes. This is called "grounding" and it is the main defence against made-up
medical facts.

NOTE: this file was written without access to the API, so it has not been run
against the live service. Test it once with your own key before relying on it.
"""

import os

SYSTEM_PROMPT = (
    "You are a health education assistant for pregnant women and new mothers in "
    "Nigeria. Answer ONLY with information found in the numbered passages the "
    "user provides. If the passages do not contain the answer, say you do not "
    "have a reliable source and suggest asking a nurse or midwife. Never "
    "diagnose, never recommend a medicine or a dose. Use simple, kind language "
    "in under 120 words. Mention the passage numbers you used, like [1]. If a "
    "passage mentions danger signs relevant to the question, tell the person to "
    "go to a health facility."
)


def build_prompt(question: str, passages: list[str]) -> str:
    numbered = "\n\n".join(f"[{i}] {text}" for i, text in enumerate(passages, 1))
    return f"Passages:\n{numbered}\n\nQuestion: {question}"


def make_llm():
    """Return a function (question, passages) -> text, or None if unavailable."""
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    client = anthropic.Anthropic(api_key=key)
    model = os.getenv("ASSISTANT_MODEL", "claude-sonnet-5-5")

    def generate(question: str, passages: list[str]) -> str:
        message = client.messages.create(
            model=model,
            max_tokens=400,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_prompt(question, passages)}],
        )
        return "".join(b.text for b in message.content if b.type == "text").strip()

    return generate
