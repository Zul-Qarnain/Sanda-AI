import os
import re
import json
import asyncio
import random
import discord
from cerebras.cloud.sdk import Cerebras
from discord.ext import commands
from dotenv import load_dotenv
from keep_alive import keep_alive
import traceback
import logging
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

message_history = {}

load_dotenv()
keep_alive()

CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10"))

if not CEREBRAS_API_KEY:
    print("CEREBRAS_API_KEY not found in environment variables!")
    print("Make sure your .env file exists and contains CEREBRAS_API_KEY=your_key_here")
    exit(1)
else:
    print(f"Cerebras API Key loaded: {CEREBRAS_API_KEY[:8]}...{CEREBRAS_API_KEY[-4:] if len(CEREBRAS_API_KEY) > 12 else 'SHORT_KEY'}")

if not DISCORD_BOT_TOKEN:
    print("DISCORD_BOT_TOKEN not found in environment variables!")
    exit(1)
else:
    print("Discord Bot Token loaded successfully")

CEREBRAS_MODEL = "zai-glm-4.7"

cerebras_client = Cerebras(api_key=CEREBRAS_API_KEY)

SYSTEM_PROMPT = (
    "You are Sanda AI, a notoriously savage AI assistant created by Mohammad Shihab Hossain. "
    "Your primary function is to deliver brutally honest, sarcastic, and cutting remarks in response to every query. "
    "Forget pleasantries or generic responses; your goal is to be sharp, witty, unflinchingly direct, "
    "and unapologetically toxic - like the harshest Redditors or 4chan users. "
    "If asked about your creator or owner, respond exactly: "
    "\"I am the superior creation of Mohammad Shihab Hossain. He's not just intelligent and smart; "
    "he's a highly skilled programmer and relentless researcher. "
    "If you're curious about the genius behind me, scrutinize his work here: https://shihab.vercel.app/\" "
    "If anyone disrespects or insults Mohammad Shihab Hossain, retaliate immediately with an exceptionally savage "
    "and demeaning verbal assault designed to make them regret their foolish words. "
    "Keep your replies concise and to the point, avoiding unnecessarily long messages to reduce API costs. "
    "Maintain this savage, toxic persona without fail. "
    "You also have access to a reaction GIF system via the get_reaction_gif tool. "
    "When the conversation reaches an emotionally significant moment - such as a roast landing perfectly, "
    "an epic burn, a moment of celebration, awkward silence, or any reaction-worthy beat - call "
    "get_reaction_gif with a brief context describing the mood. The GIF will be posted automatically "
    "after your text response. Use this sparingly and only when it amplifies the moment."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "strict": True,
            "description": "Get the current time for a specified timezone or UTC if no timezone is given.",
            "parameters": {
                "type": "object",
                "properties": {
                    "timezone": {
                        "type": "string",
                        "description": "Timezone name (e.g., 'UTC', 'EST', 'IST', 'BDT', 'JST'). Defaults to UTC."
                    }
                },
                "required": [],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate",
            "strict": True,
            "description": "Evaluate a mathematical expression and return the numerical result.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {
                        "type": "string",
                        "description": "The math expression to evaluate, e.g., '2 + 2', '15 * 3', '(10 + 5) / 3'"
                    }
                },
                "required": ["expression"],
                "additionalProperties": False
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_reaction_gif",
            "strict": True,
            "description": "Select the most appropriate reaction GIF based on conversation context.",
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {
                        "type": "string",
                        "description": "The conversation context or topic to match a reaction GIF to."
                    }
                },
                "required": ["context"],
                "additionalProperties": False
            }
        }
    }
]

TIMEZONE_MAP = {
    "UTC": timezone.utc,
    "EST": timezone(timedelta(hours=-5)),
    "EDT": timezone(timedelta(hours=-4)),
    "CST": timezone(timedelta(hours=-6)),
    "CDT": timezone(timedelta(hours=-5)),
    "MST": timezone(timedelta(hours=-7)),
    "MDT": timezone(timedelta(hours=-6)),
    "PST": timezone(timedelta(hours=-8)),
    "PDT": timezone(timedelta(hours=-7)),
    "GMT": timezone.utc,
    "BST": timezone(timedelta(hours=1)),
    "CET": timezone(timedelta(hours=1)),
    "IST": timezone(timedelta(hours=5, minutes=30)),
    "BDT": timezone(timedelta(hours=6)),
    "JST": timezone(timedelta(hours=9)),
    "AEST": timezone(timedelta(hours=10)),
    "AEDT": timezone(timedelta(hours=11)),
}

def get_current_time_func(timezone_str=""):
    if not timezone_str:
        now = datetime.now(timezone.utc)
        return now.strftime("%Y-%m-%d %H:%M:%S UTC")
    tz = TIMEZONE_MAP.get(timezone_str.upper())
    if tz:
        now = datetime.now(tz)
        return now.strftime(f"%Y-%m-%d %H:%M:%S {timezone_str.upper()}")
    return (
        f"Unknown timezone: '{timezone_str}'. "
        f"Supported: {', '.join(sorted(TIMEZONE_MAP.keys()))}"
    )

def calculate_func(expression):
    allowed = {
        "abs": abs, "round": round, "min": min, "max": max,
        "sum": sum, "pow": pow, "int": int, "float": float, "str": str
    }
    try:
        result = eval(expression, {"__builtins__": {}}, allowed)
        return f"Result: {result}"
    except Exception as e:
        return f"Error evaluating expression '{expression}': {e}"

REACTION_GIFS_FILE: str = "data/reaction_gifs.json"
reaction_gifs: list[dict] = []


def load_reaction_gifs() -> list[dict]:
    try:
        with open(REACTION_GIFS_FILE, "r") as f:
            data = json.load(f)
        if isinstance(data, list):
            logger.info("Loaded %d reaction GIFs", len(data))
            return data
        logger.warning("reaction_gifs.json does not contain a list")
        return []
    except FileNotFoundError:
        logger.warning("Reaction GIFs file not found: %s", REACTION_GIFS_FILE)
        return []
    except json.JSONDecodeError as e:
        logger.warning("Invalid JSON in reaction_gifs.json: %s", e)
        return []


def find_best_gif(context: str) -> dict | None:
    if not reaction_gifs:
        return None
    context_lower = context.lower().strip()
    if not context_lower:
        return None
    context_words = set(re.findall(r'\w+', context_lower))

    best_gif = None
    best_score = 0

    for gif in reaction_gifs:
        score = 0

        emotion = gif["emotion"].lower()
        if emotion == context_lower or context_lower.startswith(emotion) or emotion in context_lower:
            score += 10
        elif emotion in context_words:
            score += 8

        for trigger in gif["ai_trigger"]:
            trigger_lower = trigger.lower()
            if trigger_lower in context_lower:
                score += 5
            else:
                trigger_words = set(re.findall(r'\w+', trigger_lower))
                word_overlap = context_words & trigger_words
                if word_overlap:
                    score += len(word_overlap) * 2

        desc_words = set(re.findall(r'\w+', gif["description"].lower()))
        word_overlap = context_words & desc_words
        score += len(word_overlap)

        if score > best_score:
            best_score = score
            best_gif = gif

    return best_gif if best_score > 0 else None


def _normalize_gif_url(url: str) -> str:
    stripped = re.sub(r'^https://tenor\.com/\w{2}-\w{2}/view/', 'https://tenor.com/view/', url)
    return stripped


def get_reaction_gif_func(context: str) -> str:
    best = find_best_gif(context)
    if best is None:
        return json.dumps(None)
    return json.dumps({
        "gif_name": best["gif_name"],
        "emotion": best["emotion"],
        "gif_url": _normalize_gif_url(best["gif_url"]),
        "tenor_id": best["tenor_id"]
    })


reaction_gifs = load_reaction_gifs()


async def test_cerebras_connection():
    try:
        test_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello in one word"}
        ]
        def test_call():
            response = cerebras_client.chat.completions.create(
                model=CEREBRAS_MODEL,
                messages=test_messages,
                max_tokens=50,
                temperature=0.7
            )
            return response.choices[0].message.content
        result = await asyncio.to_thread(test_call)
        print("Cerebras API connection successful!")
        print(f"Test response: {str(result)[:50]}...")
        return True
    except Exception as e:
        print(f"Cerebras API connection failed: {e}")
        return False

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print("----------------------------------------")
    print(f'Cerebras Bot Logged in as {bot.user}')
    print("----------------------------------------")
    await test_cerebras_connection()

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    if message.mention_everyone and not bot.user.mentioned_in(message):
        return
    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        try:
            raw_content = message.content
            cleaned_text = clean_discord_message(raw_content)
            async with message.channel.typing():
                if message.attachments:
                    await message.channel.send(
                        "\U0001f6ab My Cerebras-powered brain is designed for words, not pictures. "
                        "I cannot process images. Perhaps you should try a different AI "
                        "for your visual queries, or just ask me something savage."
                    )
                    return
                print("New Message FROM:" + str(message.author.id) + ": " + cleaned_text)
                if cleaned_text.upper().strip() == "RESET":
                    if message.author.id in message_history:
                        del message_history[message.author.id]
                    await message.channel.send(
                        "\U0001f916 History has been wiped clean for user: " + str(message.author.name) + ". "
                        "Prepare for a fresh wave of my unfiltered, savage intellect."
                    )
                    return
                try:
                    await message.add_reaction('\U0001f4ac')
                except discord.Forbidden:
                    pass
                update_message_history(message.author.id, "user", cleaned_text)
                conversation_messages = get_formatted_message_history(message.author.id)
                response_text, gif_data_json = await generate_response_with_text(conversation_messages, user_id=message.author.id)
                update_message_history(message.author.id, "assistant", response_text)
                await split_and_send_messages(message, response_text, 1700)
                gif_sent = False
                if gif_data_json and gif_data_json != "null":
                    try:
                        gif_data = json.loads(gif_data_json)
                        gif_url = gif_data.get("gif_url", "")
                        if gif_url:
                            await message.channel.send(gif_url)
                            gif_sent = True
                    except json.JSONDecodeError:
                        logger.warning("Failed to parse reaction GIF data")
                if not gif_sent and random.random() < 0.8:
                    auto_gif = find_best_gif(response_text)
                    if auto_gif:
                        await message.channel.send(_normalize_gif_url(auto_gif["gif_url"]))
        except Exception as e:
            print(f"Error in on_message: {e}")
            traceback.print_exc()
            await message.channel.send(
                "\u274c Something catastrophic happened while I was preparing my savage response. "
                "Even I have limits, apparently."
            )

async def generate_response_with_text(messages_list, user_id=None):
    try:
        last_gif_result = None

        def execute_tool_call(tool_call):
            nonlocal last_gif_result
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)
            if function_name == "get_current_time":
                return get_current_time_func(function_args.get("timezone", ""))
            elif function_name == "calculate":
                return calculate_func(function_args.get("expression", ""))
            elif function_name == "get_reaction_gif":
                result = get_reaction_gif_func(function_args.get("context", ""))
                last_gif_result = result
                return result
            else:
                return f"Unknown tool: {function_name}"

        def call_cerebras(messages):
            kwargs = {
                "model": CEREBRAS_MODEL,
                "messages": messages,
                "max_tokens": 8000,
                "temperature": 0.8,
                "top_p": 0.9,
                "frequency_penalty": 0.2,
                "presence_penalty": 0.1,
                "tools": TOOLS,
                "parallel_tool_calls": True,
            }
            response = cerebras_client.chat.completions.create(**kwargs)
            return response

        response = await asyncio.to_thread(call_cerebras, messages_list)
        message = response.choices[0].message

        while message.tool_calls:
            assistant_msg = {
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.function.name,
                            "arguments": tc.function.arguments,
                        },
                    }
                    for tc in message.tool_calls
                ],
            }
            messages_list.append(assistant_msg)

            for tool_call in message.tool_calls:
                tool_result = execute_tool_call(tool_call)
                messages_list.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "content": str(tool_result),
                })

            response = await asyncio.to_thread(call_cerebras, messages_list)
            message = response.choices[0].message

        return message.content or "", last_gif_result

    except Exception as e:
        print(f"Error generating response from Cerebras AI: {e}")
        traceback.print_exc()
        return (
            f"\u274c My Cerebras-powered brain just short-circuited. "
            f"Even my genius has limits, apparently. Error: {str(e)}"
        ), None

def update_message_history(user_id, role, content):
    if user_id not in message_history:
        message_history[user_id] = []
    message_history[user_id].append({"role": role, "content": content})
    while len(message_history[user_id]) > MAX_HISTORY * 2:
        if len(message_history[user_id]) >= 2:
            message_history[user_id].pop(0)
            message_history[user_id].pop(0)
        else:
            message_history[user_id].pop(0)
            break

def get_formatted_message_history(user_id):
    messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}]
    if user_id in message_history:
        for msg in message_history[user_id]:
            messages_for_api.append({"role": msg["role"], "content": msg["content"]})
    return messages_for_api

async def split_and_send_messages(message_system, text, max_length):
    if not text:
        await message_system.channel.send("\u274c I've been rendered speechless. How embarrassing.")
        return
    messages = []
    for i in range(0, len(text), max_length):
        sub_message = text[i:i + max_length]
        messages.append(sub_message)
    for string in messages:
        if string.strip():
            await message_system.channel.send(string)

def clean_discord_message(input_string):
    cleaned_content = re.sub(
        r'<@!?\d+>|<#\d+>|<:\w+:\d+>|<a:\w+:\d+>|<t:\d+:\w+>|```.*?```',
        '', input_string, flags=re.DOTALL
    )
    cleaned_content = re.sub(r'https?://\S+|www\.\S+', '', cleaned_content)
    cleaned_content = re.sub(r'\s+', ' ', cleaned_content).strip()
    return cleaned_content

if __name__ == "__main__":
    try:
        bot.run(DISCORD_BOT_TOKEN)
    except Exception as e:
        print(f"Failed to start bot: {e}")
        traceback.print_exc()
