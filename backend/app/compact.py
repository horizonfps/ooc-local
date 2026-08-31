from __future__ import annotations

import math

from app.config import load_config
from app.llm.base import ChatMessage
from app.llm.openai_compat import OpenAICompatProvider

CONTEXT_BUDGET_TOKENS = 24_000
OUTPUT_RESERVE_TOKENS = 800
COMPACT_TARGET_TOKENS = 400

INPUT_BUDGET_TOKENS = CONTEXT_BUDGET_TOKENS - OUTPUT_RESERVE_TOKENS

_PROMPT_TEMPLATES = {
    "pt-br": {
        "system": (
            "Resuma em terceira pessoa, em português do Brasil, o histórico de jogo "
            f"abaixo em no máximo {COMPACT_TARGET_TOKENS} tokens. Foque em promessas "
            "feitas, conflitos abertos e mudanças de relação entre personagens. Não "
            "invente fatos e não reproduza diálogo literal."
        ),
        "previous_label": "RESUMO ANTERIOR",
        "outgoing_label": "TURNOS QUE SAEM DA JANELA",
    },
    "en": {
        "system": (
            "Summarize the game history below in third person, in English, in at "
            f"most {COMPACT_TARGET_TOKENS} tokens. Focus on promises made, open "
            "conflicts and changes in relationships between characters. Do not "
            "invent facts and do not reproduce literal dialogue."
        ),
        "previous_label": "PREVIOUS SUMMARY",
        "outgoing_label": "TURNS LEAVING THE WINDOW",
    },
}


class CompactError(Exception):
    pass


def estimate_tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def fits(messages: list[ChatMessage]) -> bool:
    total = sum(estimate_tokens(message.content) for message in messages)
    return total <= INPUT_BUDGET_TOKENS


def _build_prompt(previous: str | None, outgoing: list[ChatMessage], locale: str) -> list[ChatMessage]:
    template = _PROMPT_TEMPLATES.get(locale, _PROMPT_TEMPLATES["pt-br"])

    body_lines = []
    if previous:
        body_lines.append(f"[{template['previous_label']}]\n{previous}")
    body_lines.append(f"[{template['outgoing_label']}]")
    for message in outgoing:
        body_lines.append(f"{message.role}: {message.content}")

    return [
        ChatMessage(role="system", content=template["system"]),
        ChatMessage(role="user", content="\n".join(body_lines)),
    ]


async def compact_block(previous: str | None, outgoing: list[ChatMessage], locale: str) -> str:
    config = load_config()
    role = config.models["utility"]
    provider = OpenAICompatProvider(config.providers[role.provider])

    prompt_messages = _build_prompt(previous, outgoing, locale)
    try:
        text = await provider.complete(prompt_messages, role.model)
    except Exception as exc:
        raise CompactError(str(exc)) from exc

    text = text.strip()
    if not text:
        raise CompactError("utility returned an empty compact")
    return text
