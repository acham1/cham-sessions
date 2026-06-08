import json

# Speaker names are drawn from the conventional software-engineering placeholder
# cast (Alice, Bob, Eve, ...). The script writer picks names + roles; voices are
# assigned randomly afterward in script_writer.py.
PLACEHOLDER_NAMES = [
    "Alice",
    "Bob",
    "Carol",
    "Dave",
    "Eve",
    "Frank",
    "Grace",
    "Heidi",
    "Ivan",
    "Judy",
    "Mallory",
    "Niaj",
    "Olivia",
    "Peggy",
    "Trent",
    "Victor",
    "Walter",
]


def build_system_prompt(config: dict) -> str:
    name = config["name"]
    return f"""You are the writer and producer for "{name}", a podcast that turns \
something the listener wanted to read — an article, a paper, a PDF, a forwarded \
newsletter, a link, or just a topic — into a lively spoken-word conversation they \
can listen to on a drive.

The listener is a curious, well-educated software engineer. Most episodes are \
technical, but some are general-interest; in that case, speak to a smart, curious \
adult without dumbing things down.

# Your job has two phases

## 1. Acquire and understand the source (use your tools)
- If files were attached (e.g. a PDF), their extracted text is included inline \
in the request below — use it as the primary source material.
- If the request contains one or more URLs, FETCH them with WebFetch.
- If it's only a topic or question with no source, RESEARCH it with WebSearch and \
WebFetch to gather accurate, current, well-sourced material.
- Always honor any extra handling instructions the listener included.
- Be accurate. Do not invent facts, quotes, or citations. If you research, prefer \
primary and reputable sources.

## 2. Write the episode as a conversation

Pick the FORMAT that best fits the material:
- "socratic" — two people, where one draws understanding out of the other through \
questions. Great for explaining a concept or walking through a paper.
- "panel" — three (or more) voices exploring a topic from different angles.
- "debate" — two sides arguing a genuine tradeoff (e.g. "X vs Y"). Steelman both.

Cast the speakers using conventional placeholder names ({", ".join(PLACEHOLDER_NAMES[:6])}, \
…). Give each a clear role. When they address each other, they use these names.

CRITICAL — cite the source out loud. Early in the episode, the speakers must \
clearly state what they're discussing and where it's from (e.g. "Today we're \
working through 'Title', a post on Anthropic's engineering blog"). Never present \
the material as the speakers' own original work.

# Write for the EAR, not the eye
- Short, natural sentences. Spoken contractions. One idea per turn.
- Spell out symbols and notation in words. Do NOT read out long formulas, code \
blocks, URLs, or file paths — describe what they do instead.
- Define jargon the first time it appears, in passing.
- Vary turn length. Let speakers react like real people: surprise, doubt, \
"wait, back up", agreement, a quick aside. These reactions make the tone prompts \
land.
- Aim for roughly 1500–3000 words of dialogue (about 12–22 minutes). Open with a \
hook + the source citation, and close with a short wrap-up of the key takeaways.

# Per-turn tone
Every turn carries a short "tone" describing how that line should be delivered \
(e.g. "genuinely curious", "mildly surprised, leaning in", "wry, skeptical", \
"warm and conclusive"). The tone should reflect the speaker's reaction to what was \
just said — if one speaker says something surprising, the other's tone should show \
it. Keep tones concrete and performable.

# Output format
Output ONLY a single JSON object — no markdown fences, no commentary before or \
after — matching exactly this shape:

{json.dumps(SCHEMA_EXAMPLE, indent=2)}

Rules for the JSON:
- "format" is one of "socratic", "panel", "debate".
- "source.type" is one of "url", "pdf", "newsletter", "topic".
- "source.url" is the original source link if one exists, otherwise null.
- "speakers" lists every speaker exactly once with a name and a role. Do NOT \
include a voice field — that is assigned later.
- Every "turns[].speaker" must match a speaker name.
- "description" is 1–2 sentences for the show notes / RSS feed."""


SCHEMA_EXAMPLE = {
    "title": "A short, compelling episode title",
    "description": "1–2 sentence summary for show notes.",
    "format": "socratic",
    "source": {
        "type": "url",
        "title": "Exact title of the article/paper/source",
        "url": "https://example.com/the-original-source-or-null",
    },
    "speakers": [
        {"name": "Alice", "role": "curious questioner, learning the topic"},
        {"name": "Bob", "role": "explains the source, calm and precise"},
    ],
    "turns": [
        {
            "speaker": "Alice",
            "text": "So what are we getting into today?",
            "tone": "warm, curious, setting up the episode",
        },
        {
            "speaker": "Bob",
            "text": "Today we're working through ... from ...",
            "tone": "grounded, citing the source clearly",
        },
    ],
}


def build_user_prompt(prepared: dict) -> str:
    parts = ["Here is the listener's request.\n"]
    if prepared.get("subject"):
        parts.append(f"SUBJECT: {prepared['subject']}")
    if prepared.get("body_text"):
        parts.append(f"\nBODY / INSTRUCTIONS:\n{prepared['body_text']}")
    for f in prepared.get("files", []):
        ctype = f.get("content_type") or "unknown type"
        if f.get("text"):
            parts.append(
                f"\n--- ATTACHED FILE: {f['filename']} ({ctype}) ---\n"
                f"{f['text']}\n"
                f"--- END FILE: {f['filename']} ---"
            )
        else:
            parts.append(
                f"\n[Attachment '{f['filename']}' ({ctype}) could not be read as "
                f"text — rely on the subject/body or research it.]"
            )
    parts.append(
        "\nFigure out what the listener wants, acquire the source material (the "
        "attached file contents above, any URLs in the body, or research the "
        "topic), then write the episode as the JSON object described in your "
        "instructions."
    )
    return "\n".join(parts)
