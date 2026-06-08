import io
import logging
import wave
from concurrent.futures import ThreadPoolExecutor, as_completed

from google import genai
from google.genai import types
from google.cloud import storage
from pydub import AudioSegment

from config import load_config

logger = logging.getLogger(__name__)

# Gemini prebuilt voices. Each speaker in an episode is assigned a distinct one.
VOICES = [
    "Zephyr",
    "Puck",
    "Charon",
    "Kore",
    "Fenrir",
    "Leda",
    "Orus",
    "Aoede",
    "Callirrhoe",
    "Autonoe",
    "Enceladus",
    "Iapetus",
    "Umbriel",
    "Algieba",
    "Despina",
    "Erinome",
    "Algenib",
    "Rasalgethi",
    "Laomedeia",
    "Achernar",
    "Alnilam",
    "Schedar",
    "Gacrux",
    "Pulcherrima",
    "Achird",
    "Zubenelgenubi",
    "Vindemiatrix",
    "Sadachbia",
    "Sadaltager",
    "Sulafat",
]

TTS_MODEL = "gemini-3.1-flash-tts-preview"

# Shared delivery guidance; each turn's specific tone is layered on top.
BASE_STYLE = (
    "This is one turn in a natural, unscripted-sounding conversation between two "
    "or more people. Speak conversationally and human, not like an announcer. "
    "Use natural pacing and clear diction. Deliver this line with the following "
    "intent:"
)

# Gap inserted between consecutive turns. Shorter than a monologue's paragraph
# break so the back-and-forth feels like a real conversation.
TURN_GAP_MS = 350


def build_sections(episode: dict) -> list[dict]:
    """Turn the dialogue into ordered TTS sections, one per turn, each tagged
    with the speaker's voice and a delivery style derived from the turn tone."""
    voice_by_name = {s["name"]: s.get("voice", VOICES[0]) for s in episode["speakers"]}
    fallback_voice = next(iter(voice_by_name.values()), VOICES[0])

    sections = []
    for turn in episode["turns"]:
        text = (turn.get("text") or "").strip()
        if not text:
            continue
        tone = (turn.get("tone") or "natural and conversational").strip()
        sections.append(
            {
                "text": text,
                "voice": voice_by_name.get(turn.get("speaker"), fallback_voice),
                "style": f"{BASE_STYLE} {tone}.",
            }
        )
    return sections


def _pcm_to_audio_segment(pcm_data: bytes) -> AudioSegment:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(24000)
        wf.writeframes(pcm_data)
    buf.seek(0)
    return AudioSegment.from_wav(buf)


def synthesize_audio(sections: list[dict], episode_id: str, config: dict) -> dict:
    client = genai.Client(
        vertexai=True,
        project=config["gcp_project"],
        location=config["gcp_region"],
    )

    total_chars = sum(len(s["text"]) for s in sections)
    logger.info(
        "Synthesizing %d turns (%d chars) in parallel", len(sections), total_chars
    )

    def _synthesize_one(i, section):
        logger.info(
            "Turn %d/%d, voice=%s (%d chars)",
            i + 1,
            len(sections),
            section["voice"],
            len(section["text"]),
        )
        tts_config = types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name=section["voice"],
                    )
                )
            ),
        )
        response = client.models.generate_content(
            model=TTS_MODEL,
            contents=f"{section['style']}\n\n{section['text']}",
            config=tts_config,
        )
        if not response.candidates or not response.candidates[0].content.parts:
            logger.warning("Empty TTS response for turn %d, skipping", i + 1)
            return i, None
        pcm_data = response.candidates[0].content.parts[0].inline_data.data
        return i, _pcm_to_audio_segment(pcm_data)

    results = [None] * len(sections)
    skipped = []

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = {
            pool.submit(_synthesize_one, i, s): i for i, s in enumerate(sections)
        }
        for future in as_completed(futures):
            i = futures[future]
            idx, segment = future.result()
            if segment is None:
                skipped.append({"index": i + 1, "preview": sections[i]["text"][:100]})
            else:
                results[i] = segment

    combined = AudioSegment.empty()
    gap = AudioSegment.silent(duration=TURN_GAP_MS)
    for segment in results:
        if segment is None:
            continue
        if len(combined) > 0:
            combined += gap
        combined += segment

    logger.info(
        "TTS synthesized %d chars, total duration %.1fs",
        total_chars,
        len(combined) / 1000,
    )

    mp3_buf = io.BytesIO()
    combined.export(mp3_buf, format="mp3", bitrate="128k")
    mp3_bytes = mp3_buf.getvalue()

    bucket_name = config["podcast_bucket"]
    bucket = storage.Client().bucket(bucket_name)
    blob = bucket.blob(f"episodes/{episode_id}.mp3")
    blob.upload_from_string(mp3_bytes, content_type="audio/mpeg")

    audio_url = (
        f"https://storage.googleapis.com/{bucket_name}/episodes/{episode_id}.mp3"
    )
    logger.info("Uploaded %d bytes to %s", len(mp3_bytes), audio_url)

    return {
        "audio_url": audio_url,
        "duration_secs": int(len(combined) / 1000),
        "size_bytes": len(mp3_bytes),
        "model": TTS_MODEL,
        "skipped_sections": skipped,
    }


def generate_episode_audio(episode: dict, episode_id: str) -> dict:
    config = load_config()
    sections = build_sections(episode)
    if not sections:
        raise ValueError("No speakable turns in episode")
    return synthesize_audio(sections, episode_id, config)
