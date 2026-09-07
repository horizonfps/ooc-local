from __future__ import annotations

from app.config import Config
from app.llm.base import ChatMessage, GenerationOptions
from app.llm.openai_compat import OpenAICompatProvider
from app.scenario import AchievementDef, LoadedScenario

MILESTONE_MAX_TOKENS = 160
ENDING_MAX_TOKENS = 700
EPILOGUE_WINDOW_TURNS = 12
EPILOGUE_EXCERPT_CHARS = 600

MILESTONE_OPTIONS = GenerationOptions(max_tokens=MILESTONE_MAX_TOKENS, temperature=0.7, timeout_s=90.0)
ENDING_OPTIONS = GenerationOptions(max_tokens=ENDING_MAX_TOKENS, temperature=0.8, timeout_s=180.0)

_PROMPT_TEMPLATES = {
    "pt-br": {
        "milestone_system": (
            "Você é o mesmo narrador desta história. Escreva de 2 a 4 frases marcando "
            "o que o jogador acabou de alcançar. Use só os fatos dos turnos "
            "apresentados. Não encerre a história, não prometa o futuro, não fale com "
            "o jogador sobre o jogo, e não cite regras, sistema ou nome de conquista."
        ),
        "ending_system": (
            "Escreva o epílogo desta história. Feche o destino de quem apareceu nos "
            "turnos apresentados, usando só os fatos apresentados. Não abra pergunta "
            "nova e não fale com o jogador sobre o jogo."
        ),
        "milestone_label": "MARCO",
        "ending_label": "FINAL",
        "summary_label": "RESUMO ANTERIOR",
        "turns_label": "ÚLTIMOS TURNOS",
    },
    "en": {
        "milestone_system": (
            "You are the same narrator of this story. Write 2 to 4 sentences marking "
            "what the player just achieved. Use only the facts from the turns shown. "
            "Do not close the story, do not promise the future, do not talk to the "
            "player about the game, and do not mention rules, the system, or the "
            "achievement's name."
        ),
        "ending_system": (
            "Write the epilogue of this story. Close the fate of whoever appeared in "
            "the turns shown, using only the facts shown. Do not open a new question "
            "and do not talk to the player about the game."
        ),
        "milestone_label": "MILESTONE",
        "ending_label": "ENDING",
        "summary_label": "PREVIOUS SUMMARY",
        "turns_label": "RECENT TURNS",
    },
}


class EpilogueError(Exception):
    pass


def _field(value: str) -> str:
    return " ".join(value.split()).replace("|", "/")


def _window_lines(window: list[ChatMessage]) -> list[str]:
    recent = window[-(EPILOGUE_WINDOW_TURNS * 2) :] if window else []
    return [f"{m.role}: {m.content[:EPILOGUE_EXCERPT_CHARS]}" for m in recent]


def build_milestone_messages(
    scenario: LoadedScenario, achievement: AchievementDef, window: list[ChatMessage]
) -> list[ChatMessage]:
    template = _PROMPT_TEMPLATES.get(scenario.meta.locale, _PROMPT_TEMPLATES["pt-br"])

    body_lines = [
        f"[{template['milestone_label']}] {_field(achievement.name)} | {_field(achievement.condition)}",
        f"[{template['turns_label']}]",
        *_window_lines(window),
    ]

    return [
        ChatMessage(role="system", content=template["milestone_system"]),
        ChatMessage(role="user", content="\n".join(body_lines)),
    ]


def build_ending_messages(
    scenario: LoadedScenario,
    achievement: AchievementDef,
    window: list[ChatMessage],
    compact: str | None,
) -> list[ChatMessage]:
    template = _PROMPT_TEMPLATES.get(scenario.meta.locale, _PROMPT_TEMPLATES["pt-br"])

    body_lines = [
        f"[{template['ending_label']}] {_field(achievement.name)} | {_field(achievement.condition)}",
    ]
    if compact:
        body_lines.append(f"[{template['summary_label']}]\n{compact}")
    body_lines.append(f"[{template['turns_label']}]")
    body_lines.extend(_window_lines(window))

    return [
        ChatMessage(role="system", content=template["ending_system"]),
        ChatMessage(role="user", content="\n".join(body_lines)),
    ]


async def _write(system: str, body: str, options: GenerationOptions, config: Config) -> str:
    try:
        role = config.models["narrator"]
    except KeyError:
        raise EpilogueError("no narrator role") from None
    provider = OpenAICompatProvider(config.providers[role.provider], options)
    try:
        raw = await provider.complete(
            [ChatMessage(role="system", content=system), ChatMessage(role="user", content=body)],
            role.model,
        )
    except Exception as exc:
        raise EpilogueError(str(exc)) from exc
    text = raw.strip()
    if not text:
        raise EpilogueError("narrator returned an empty epilogue")
    return text


async def write_milestone(
    scenario: LoadedScenario,
    achievement: AchievementDef,
    window: list[ChatMessage],
    config: Config,
) -> str:
    messages = build_milestone_messages(scenario, achievement, window)
    return await _write(messages[0].content, messages[1].content, MILESTONE_OPTIONS, config)


async def write_ending(
    scenario: LoadedScenario,
    achievement: AchievementDef,
    window: list[ChatMessage],
    compact: str | None,
    config: Config,
) -> str:
    messages = build_ending_messages(scenario, achievement, window, compact)
    return await _write(messages[0].content, messages[1].content, ENDING_OPTIONS, config)
