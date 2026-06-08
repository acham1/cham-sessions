# Cham Sessions

*I'm Alan Cham. These are riffs on the things I've been meaning to read.*

Forward an article, a PDF, a link, a newsletter, or just a topic to a dedicated
email address (with optional handling instructions), and Cham Sessions researches
it, writes it up as a **conversation between two or more personas**, synthesizes
each turn with its own voice and tone, and publishes the result to an RSS/podcast
feed you can listen to on a drive.

Episodes clearly cite their source — the speakers name what they're discussing,
and the podcast feed links back to the original when one exists.

## Architecture

```
You forward email ──► functions/inbound (HTTP, Resend Inbound webhook)
                          • verify Svix signature + allowlist sender
                          • dedupe on Message-ID
                          • stash attachments in GCS
                          • create pending episode in Firestore
                          • publish job to Pub/Sub + reply "got it"
                              │
                              ▼
                      functions/generate_episode (Pub/Sub triggered)
                          • ingest: download attachments locally
                          • script_writer: Claude Agent SDK researches the
                            source and emits a structured dialogue (JSON)
                          • podcast_generator: per-turn TTS, each speaker a
                            distinct Gemini voice, each turn its own tone
                          • save episode, email subscribers
                              │
                              ▼
                      functions/api (HTTP) ──► feed.xml / podcast.xml / site
```

- **`functions/inbound`** — receives forwarded email via Resend Inbound, validates
  it, and enqueues a generation job.
- **`functions/generate_episode`** — the worker. `script_writer.py` runs a Claude
  agent that reads PDFs / fetches URLs / researches topics and returns a dialogue
  as JSON (`format`, `speakers`, `turns` with per-turn `tone`).
  `podcast_generator.py` synthesizes each turn with the speaker's voice and the
  turn's tone, concatenates, and uploads the MP3 to GCS.
- **`functions/api`** — subscribe/unsubscribe, episode listing, blog RSS
  (`/feed.xml`), and podcast RSS (`/podcast.xml`).
- **`frontend/`** — static site (built by `scripts/build_frontend.py`), episode
  pages render the audio player plus the full transcript.
- **`config.yaml`** — single source of truth for branding, GCP, the inbound
  address, the sender allowlist, and podcast metadata.

## Episode formats

The script writer picks the format that fits the material:

- **socratic** — one persona draws understanding out of another via questions.
- **panel** — three or more voices exploring a topic from different angles.
- **debate** — two sides steelmanning a genuine tradeoff.

Speakers are named with conventional placeholders (Alice, Bob, Eve, Mallory, …)
and each is assigned a distinct random Gemini voice per episode.

## Setup

### Prerequisites

- GCP project `cham-sessions` with these APIs enabled: Cloud Functions, Pub/Sub,
  Firestore, Secret Manager, Cloud Build, Cloud Run, Eventarc, Vertex AI.
- [Resend](https://resend.com): a verified **sending** domain *and* an **inbound**
  domain (MX records) routed to the `inbound` function's webhook URL.
- Anthropic API key.
- A GCS bucket (`cham-sessions`) for audio + inbound attachments (audio publicly
  readable).

### Configuration

All non-secret config lives in `config.yaml` — notably `inbound_address` (where you
forward content) and `allowed_senders` (who is allowed to trigger episodes).

### Secrets

Create a `environment-variables` secret in Secret Manager (see `.env.example`):

```
ANTHROPIC_API_KEY=...
RESEND_API_KEY=...
RESEND_WEBHOOK_SECRET=whsec_...   # from the Resend inbound webhook config
UNSUBSCRIBE_SECRET=<random-hex>
ADMIN_EMAIL=you@example.com
ALLOWED_SENDERS=you@example.com,you@gmail.com
CLAUDE_MODEL=claude-sonnet-4-6
MAX_BUDGET_USD=0.75
```

Grant the default compute service account `Secret Manager Secret Accessor`.

### Deploy

```bash
bash deploy.sh
```

This deploys all three functions and prints the **inbound webhook URL** — point
your Resend Inbound route at it. The frontend builds via
`scripts/build_frontend.py` (GitHub Pages, like dev-deep-dive).

### Try it

Forward or send an email to your `inbound_address` from an allowlisted sender —
attach a PDF, paste a link, or just describe a topic, with any extra instructions
in the body. You'll get an acknowledgement, then the episode appears in your feed.

## Notes / TODO

- **Assets**: drop `logo.png`, `logo-icon.png`, `favicon.png`, `apple-touch-icon.png`
  into `frontend/`, and a square `cover.png` into the bucket (`podcast_cover_url`).
- **Resend Inbound payload**: the webhook parses defensively and logs the event
  `type` on first receipt — confirm the field names (`from`, `subject`, `text`,
  `attachments[].content`) against a real delivery and tighten if needed.
- **Audience**: the feed is public. Source citation is built in, but episodes are
  derived from your personal reading list — keep that in mind.
