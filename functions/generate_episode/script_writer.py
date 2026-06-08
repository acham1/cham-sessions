import json
import logging
import os
import random

import anyio
from claude_agent_sdk import ClaudeAgentOptions, ResultMessage, query

from config import load_config
from podcast_generator import VOICES
from prompts import build_system_prompt, build_user_prompt

logger = logging.getLogger(__name__)


def write_script(prepared: dict) -> dict:
    """Run the research/writing agent and return a validated episode dict with
    voices assigned to each speaker."""
    return anyio.run(_write_script, prepared)


async def _write_script(prepared: dict) -> dict:
    config = load_config()
    options = ClaudeAgentOptions(
        system_prompt=build_system_prompt(config),
        model=os.environ.get(
            "CLAUDE_MODEL", config.get("claude_model", "claude-sonnet-4-6")
        ),
        max_turns=40,
        max_budget_usd=float(
            os.environ.get("MAX_BUDGET_USD", config.get("max_budget_usd", 0.75))
        ),
        cwd=prepared["work_dir"],
        allowed_tools=["WebSearch", "WebFetch", "Read", "Glob", "Grep", "Bash"],
        disallowed_tools=["Write", "Edit"],
    )

    full_text = ""
    async for message in query(prompt=build_user_prompt(prepared), options=options):
        if isinstance(message, ResultMessage):
            full_text = message.result

    episode = _parse_episode(full_text)
    _assign_voices(episode)
    return episode


def _parse_episode(text: str) -> dict:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0].strip()
    # Be forgiving of any stray prose around the JSON object.
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in agent output: {text[:500]}")
    episode = json.loads(text[start : end + 1])

    for field in ("title", "format", "speakers", "turns"):
        if field not in episode:
            raise ValueError(f"Episode missing '{field}'")
    if not episode["turns"]:
        raise ValueError("Episode has no turns")

    speaker_names = {s["name"] for s in episode["speakers"]}
    for turn in episode["turns"]:
        if turn.get("speaker") not in speaker_names:
            raise ValueError(f"Turn references unknown speaker: {turn.get('speaker')}")

    episode.setdefault("description", "")
    episode.setdefault("source", {"type": "topic", "title": "", "url": None})
    return episode


def _assign_voices(episode: dict):
    speakers = episode["speakers"]
    voices = random.sample(VOICES, min(len(speakers), len(VOICES)))
    for speaker, voice in zip(speakers, voices):
        speaker["voice"] = voice
