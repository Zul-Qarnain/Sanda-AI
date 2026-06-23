# Sanda-AI

A savage Discord bot powered by Cerebras AI with function calling and reaction GIF support.

## Features

-   **AI Chat** — Cerebras-powered conversational AI with a savage, toxic persona
-   **Function Calling** — Tools for timezone lookup, math evaluation, and reaction GIF selection
-   **Reaction GIFs** — Auto-sends context-aware Tenor GIFs ~80% of the time
-   **Message History** — Per-user conversation memory capped at configurable depth
-   **Uptime Monitor** — Flask health-check endpoint on port 8080

## Setup

1. Clone the repo and create a `.env` file:

```
CEREBRAS_API_KEY=your_cerebras_api_key
DISCORD_BOT_TOKEN=your_discord_bot_token
MAX_HISTORY=10
```

2. Install dependencies:

```
pip install -r requirements.txt
```

3. Run the bot:

```
python main.py
```

## Tools

| Tool | Description |
|------|-------------|
| `get_current_time` | Returns the current time for a given timezone |
| `calculate` | Evaluates a math expression |
| `get_reaction_gif` | Selects a reaction GIF matching conversation context |

## GIF Data

Reaction GIFs are stored in `data/reaction_gifs.json`. Each entry has:

- `gif_name` — Unique identifier
- `emotion` — Emotion category (happy, angry, confused, etc.)
- `description` — What the GIF depicts
- `ai_trigger` — Keywords that trigger this GIF
- `gif_url` — Tenor view URL for Discord auto-embed
- `tenor_id` — Tenor media identifier

## License

CC BY-NC 4.0
