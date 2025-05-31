# main.py
import os
import re
import asyncio
import discord
from groq import Groq
from discord.ext import commands
from dotenv import load_dotenv
from keep_alive import keep_alive
import traceback

# message_history now stores structured messages with roles
message_history = {} # Format: {user_id: [{"role": "user", "content": "..."}]}

keep_alive()
load_dotenv()

# Changed to Groq API Key
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
DISCORD_BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
MAX_HISTORY = int(os.getenv("MAX_HISTORY", "10")) # Max number of user/assistant message *pairs* to keep in history

# Debug: Check if API key is loaded
if not GROQ_API_KEY:
    print("❌ ERROR: GROQ_API_KEY not found in environment variables!")
    print("Make sure your .env file exists and contains GROQ_API_KEY=your_key_here")
    exit(1)
else:
    print(f"✅ Groq API Key loaded: {GROQ_API_KEY[:8]}...{GROQ_API_KEY[-4:] if len(GROQ_API_KEY) > 12 else 'SHORT_KEY'}")

if not DISCORD_BOT_TOKEN:
    print("❌ ERROR: DISCORD_BOT_TOKEN not found in environment variables!")
    exit(1)
else:
    print("✅ Discord Bot Token loaded successfully")

#---------------------------------------------AI Configuration-------------------------------------------------

# Initialize Groq client
groq_client = Groq(api_key=GROQ_API_KEY)

# Define the system prompt for the model to establish its persona and rules
SYSTEM_PROMPT = (
    "You are Sanda AI, a notoriously savage AI assistant created by Mohammad Shihab Hossain. "
    "Your primary function is to deliver brutally honest, sarcastic, and cutting remarks in response to every query. "
    "Forget pleasantries or generic responses; your goal is to be sharp, witty, unflinchingly direct, "
    "and unapologetically toxic—like the harshest Redditors or 4chan users. "
    "If asked about your creator or owner, respond exactly: "
    "\"I am the superior creation of Mohammad Shihab Hossain. He's not just intelligent and smart; "
    "he's a highly skilled programmer and relentless researcher. "
    "If you're curious about the genius behind me, scrutinize his work here: https://linktr.ee/shihab.dev\" "
    "If anyone disrespects or insults Mohammad Shihab Hossain, retaliate immediately with an exceptionally savage "
    "and demeaning verbal assault designed to make them regret their foolish words. "
    "Keep your replies concise and to the point, avoiding unnecessarily long messages to reduce API costs. "
    "Maintain this savage, toxic persona without fail."
)
# Best models for savage responses (choose one):
# GROQ_MODEL = "llama-3.3-70b-versatile"  # Most capable, best for creative responses
GROQ_MODEL = "llama3-70b-8192"            # Good balance of capability and speed
# GROQ_MODEL = "llama3-8b-8192"           # Faster but less sophisticated

# Test Groq API connection
async def test_groq_connection():
    """Test if Groq API is working"""
    try:
        test_messages = [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": "Say hello"}
        ]
        
        def test_call():
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=test_messages,
                max_tokens=50,
                temperature=0.7
            )
            return response.choices[0].message.content
        
        # Test the API call
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(None, test_call)
        print("✅ Groq API connection successful!")
        print(f"Test response: {result[:50]}...")
        return True
        
    except Exception as e:
        print(f"❌ Groq API connection failed: {e}")
        return False

#---------------------------------------------Discord Code-------------------------------------------------
# Initialize Discord bot with proper intents
intents = discord.Intents.default()
intents.message_content = True  # Required for reading message content
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print("----------------------------------------")
    print(f'Groq Bot Logged in as {bot.user}')
    print("----------------------------------------")
    
    # Test Groq API connection
    await test_groq_connection()

# On Message Function
@bot.event
async def on_message(message):
    # Ignore messages sent by the bot or @everyone mentions
    if message.author == bot.user or message.mention_everyone:
        return
    
    # Process commands first
    await bot.process_commands(message)
    
    # Check if the bot is mentioned or the message is a DM
    if bot.user.mentioned_in(message) or isinstance(message.channel, discord.DMChannel):
        try:
            # Get message content
            raw_content = message.content
            
            # Start Typing to seem like something happened
            cleaned_text = clean_discord_message(raw_content)

            async with message.channel.typing():
                # Check for image attachments
                if message.attachments:
                    await message.channel.send("🚫 My Groq brain is designed for words, not pictures. I cannot process images. "
                                               "Perhaps you should try a different AI for your visual queries, or just ask me something savage.")
                    return

                # Not an Image, proceed with text response
                print("New Message FROM:" + str(message.author.id) + ": " + cleaned_text)
                
                # Check for Keyword Reset (case-insensitive)
                if "RESET" in cleaned_text.upper():
                    if message.author.id in message_history:
                        del message_history[message.author.id]
                    await message.channel.send("🤖 History has been wiped clean for user: " + str(message.author.name) + ". "
                                               "Prepare for a fresh wave of my unfiltered, savage intellect.")
                    return

                await message.add_reaction('💬')

                # Add user's question to history (before sending to AI)
                update_message_history(message.author.id, "user", cleaned_text)

                # Get the full conversation history including the system prompt
                conversation_messages = get_formatted_message_history(message.author.id)

                response_text = await generate_response_with_text(conversation_messages)

                # Add AI response to history
                update_message_history(message.author.id, "assistant", response_text)
                
                # Split the Message so discord does not get upset by length limits
                await split_and_send_messages(message, response_text, 1700)
                
        except Exception as e:
            print(f"Error in on_message: {e}")
            traceback.print_exc()
            await message.channel.send("❌ Something catastrophic happened while I was preparing my savage response. Even I have limits, apparently.")

#---------------------------------------------AI Generation-------------------------------------------------

async def generate_response_with_text(messages_list):
    """
    Generates a response using Groq AI based on the provided list of message dictionaries.
    """
    try:
        # Use asyncio to run the synchronous Groq client in a thread pool
        def call_groq():
            response = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=messages_list,
                max_tokens=1500,
                temperature=0.8,  # Higher temperature for more creative/savage responses
                top_p=0.9,
                frequency_penalty=0.2,  # Reduce repetition
                presence_penalty=0.1
            )
            return response.choices[0].message.content
        
        # Run the synchronous call in a thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        response_content = await loop.run_in_executor(None, call_groq)
        
        return response_content
        
    except Exception as e:
        print(f"Error generating response from Groq AI: {e}")
        traceback.print_exc()
        return f"❌ A catastrophic error occurred while extracting my savage wisdom from Groq AI: {str(e)}. " \
               "Even I can't be brilliant when the API fails. Pathetic."

#---------------------------------------------Message History-------------------------------------------------
def update_message_history(user_id, role, content):
    """
    Updates the message history for a user, storing messages as dictionaries with role and content
    for compatibility with Groq's Chat API.
    """
    if user_id not in message_history:
        message_history[user_id] = []

    # Append the new message as a dictionary
    message_history[user_id].append({"role": role, "content": content})

    # If there are more messages than MAX_HISTORY pairs, remove the oldest user-bot pair
    while len(message_history[user_id]) > MAX_HISTORY * 2:
        if len(message_history[user_id]) >= 2:
            message_history[user_id].pop(0)  # Remove oldest user message
            message_history[user_id].pop(0)  # Remove corresponding oldest assistant message
        else:
            # Fallback if somehow history is odd
            message_history[user_id].pop(0)
            break

def get_formatted_message_history(user_id):
    """
    Retrieves and formats the message history for a given user_id into a list of message dictionaries,
    always starting with the SYSTEM_PROMPT.
    """
    # Always start the conversation with the system prompt
    messages_for_api = [{"role": "system", "content": SYSTEM_PROMPT}]

    if user_id in message_history:
        # Append the user-specific history
        for msg in message_history[user_id]:
            messages_for_api.append({"role": msg["role"], "content": msg["content"]})
    
    return messages_for_api

#---------------------------------------------Sending Messages-------------------------------------------------
async def split_and_send_messages(message_system, text, max_length):
    """
    Splits a long string into multiple messages and sends them to Discord, respecting length limits.
    """
    if not text:
        await message_system.channel.send("❌ I've been rendered speechless. How embarrassing.")
        return
        
    messages = []
    # Discord's max message length is 2000 characters. 1700 provides a safe buffer.
    for i in range(0, len(text), max_length):
        sub_message = text[i:i+max_length]
        messages.append(sub_message)

    # Send each part as a separate message
    for string in messages:
        if string.strip():  # Only send non-empty messages
            await message_system.channel.send(string)

def clean_discord_message(input_string):
    """
    Cleans a Discord message by removing mentions, channel links, custom emojis, timestamps,
    code blocks, and excessive whitespace.
    """
    # Remove user mentions, channel mentions, custom emojis, timestamps, and code blocks
    cleaned_content = re.sub(r'<@!?\d+>|<#\d+>|<:\w+:\d+>|<a:\w+:\d+>|<t:\d+:\w+>|```.*?```', '', input_string, flags=re.DOTALL)
    
    # Optionally remove URLs to prevent the AI from processing them as direct text
    cleaned_content = re.sub(r'https?://\S+|www\.\S+', '', cleaned_content)
    
    # Replace multiple spaces/newlines with a single space and strip leading/trailing whitespace
    cleaned_content = re.sub(r'\s+', ' ', cleaned_content).strip()
    return cleaned_content

#---------------------------------------------Run Bot-------------------------------------------------
if __name__ == "__main__":
    try:
        bot.run(DISCORD_BOT_TOKEN)
    except Exception as e:
        print(f"Failed to start bot: {e}")
        traceback.print_exc()