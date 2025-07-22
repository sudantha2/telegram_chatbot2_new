from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import MessageHandler, filters, PollAnswerHandler
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
from keep_alive import keep_alive
import os
import sys
from PIL import Image, ImageDraw, ImageFont
import random
import io
import requests
import asyncio
import psutil
import gc
import time
from motor.motor_asyncio import AsyncIOMotorClient

# Start the Replit web server to keep the bot alive
keep_alive()

# Environment variables - Direct assignment
os.environ['TOKEN'] = '7642209531:AAFkepF4Hvas36NNMUYrsTh3L63L1CQEIbA'
os.environ['MONGO_URI'] = 'mongodb+srv://Sudantha123:sudantha2007@cluster0.qarydyw.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0'
os.environ['TOGETHER_API_KEY'] = 'bd3a8117107d09348c28f43d60f29c2045085159855ca76b9e6426ce0c3850e4'
os.environ['PIXABAY_API_KEY'] = '35389728-c4a24f22d93bd62fa62b389c1'
os.environ['OPENWEATHERMAP_API_KEY'] = 'a623bb300e66747dbe58d672fc045d59'
os.environ['MONGO_QUIZ_URI'] = 'mongodb+srv://tbot5182:Sudantha123@leaderboard.qeysmef.mongodb.net/?retryWrites=true&w=majority&appName=LeaderBoard'
os.environ['MONGO_GRPDATA_URI'] = 'mongodb+srv://sudantha64:Sudantha123@grpdata.h8ny3lf.mongodb.net/?retryWrites=true&w=majority&appName=GrpData'

# Get the bot token from environment
TOKEN = os.environ['TOKEN']

# MongoDB connection
MONGO_URI = os.environ.get('MONGO_URI')
if not MONGO_URI:
    print("ERROR: MONGO_URI environment variable not found!")
    print("Please add MONGO_URI to your secrets in the Replit environment.")
    sys.exit(1)

mongo_client = AsyncIOMotorClient(MONGO_URI)
db = mongo_client.telegram_bot
filters_collection = db.filters

# MongoDB Quiz connection
MONGO_QUIZ_URI = os.environ.get('MONGO_QUIZ_URI')
if MONGO_QUIZ_URI:
    quiz_mongo_client = AsyncIOMotorClient(MONGO_QUIZ_URI)
    quiz_db = quiz_mongo_client.quiz_bot
    quiz_collection = quiz_db.questions
else:
    quiz_mongo_client = None
    quiz_db = None
    quiz_collection = None

# MongoDB Group Data connection
MONGO_GRPDATA_URI = os.environ.get('MONGO_GRPDATA_URI')
if MONGO_GRPDATA_URI:
    grpdata_mongo_client = AsyncIOMotorClient(MONGO_GRPDATA_URI)
    grpdata_db = grpdata_mongo_client.group_data
    group_configs_collection = grpdata_db.group_configs
else:
    grpdata_mongo_client = None
    grpdata_db = None
    group_configs_collection = None
    print("WARNING: MONGO_GRPDATA_URI not found! Group configuration features will be disabled.")

# Group message counters for auto reactions
group_message_counters = {}



# Filter management functions
async def save_filter(chat_id, keyword, reply_type, reply_content):
    """Save a filter to MongoDB"""
    try:
        filter_doc = {
            "chat_id": chat_id,
            "keyword": keyword.lower(),
            "reply_type": reply_type,
            "reply_content": reply_content
        }
        # Replace existing filter with same keyword and chat_id
        await filters_collection.replace_one(
            {"chat_id": chat_id, "keyword": keyword.lower()},
            filter_doc,
            upsert=True
        )
        return True
    except Exception as e:
        print(f"Error saving filter: {e}")
        return False

async def delete_filter(chat_id, keyword):
    """Delete a filter from MongoDB"""
    try:
        result = await filters_collection.delete_one({
            "chat_id": chat_id,
            "keyword": keyword.lower()
        })
        return result.deleted_count > 0
    except Exception as e:
        print(f"Error deleting filter: {e}")
        return False

async def get_filters(chat_id):
    """Get all filters for a chat"""
    try:
        cursor = filters_collection.find({"chat_id": chat_id})
        return await cursor.to_list(length=None)
    except Exception as e:
        print(f"Error getting filters: {e}")
        return []

async def get_filter_by_keyword(chat_id, keyword):
    """Get a specific filter by keyword"""
    try:
        return await filters_collection.find_one({
            "chat_id": chat_id,
            "keyword": keyword.lower()
        })
    except Exception as e:
        print(f"Error getting filter: {e}")
        return None

# Group configuration management functions
async def get_group_config(chat_id):
    """Get group configuration from MongoDB"""
    if group_configs_collection is None:
        return {"auto_reactions": False, "sticker_blocker": False}

    try:
        config = await group_configs_collection.find_one({"chat_id": chat_id})
        if config:
            # Ensure all default keys exist
            default_config = {"auto_reactions": False, "sticker_blocker": False}
            default_config.update(config)
            return default_config
        else:
            # Return default config if not found
            return {"auto_reactions": False, "sticker_blocker": False}
    except Exception as e:
        print(f"Error getting group config: {e}")
        return {"auto_reactions": False, "sticker_blocker": False}

async def save_group_config(chat_id, config_data):
    """Save group configuration to MongoDB"""
    if group_configs_collection is None:
        return False

    try:
        config_doc = {
            "chat_id": chat_id,
            **config_data
        }
        await group_configs_collection.replace_one(
            {"chat_id": chat_id},
            config_doc,
            upsert=True
        )
        return True
    except Exception as e:
        print(f"Error saving group config: {e}")
        return False

async def toggle_auto_reactions(chat_id):
    """Toggle auto reactions setting for a group"""
    config = await get_group_config(chat_id)
    config["auto_reactions"] = not config.get("auto_reactions", False)
    success = await save_group_config(chat_id, config)
    return success, config["auto_reactions"]

async def toggle_sticker_blocker(chat_id):
    """Toggle sticker blocker setting for a group"""
    config = await get_group_config(chat_id)
    config["sticker_blocker"] = not config.get("sticker_blocker", False)
    success = await save_group_config(chat_id, config)
    return success, config["sticker_blocker"]

async def set_password_protection(chat_id, protected=True):
    """Set password protection for a group"""
    if group_configs_collection is None:
        return False
    
    try:
        # Update or create group config with password protection
        config_doc = {
            "chat_id": chat_id,
            "password_protected": protected
        }
        
        await group_configs_collection.update_one(
            {"chat_id": chat_id},
            {"$set": {"password_protected": protected}},
            upsert=True
        )
        
        # Update in-memory protected groups set
        if protected:
            PROTECTED_GROUPS.add(chat_id)
        else:
            PROTECTED_GROUPS.discard(chat_id)
        
        return True
    except Exception as e:
        print(f"Error setting password protection: {e}")
        return False

async def load_protected_groups():
    """Load password-protected groups from MongoDB on startup"""
    if group_configs_collection is None:
        return
    
    try:
        protected_configs = group_configs_collection.find({"password_protected": True})
        async for config in protected_configs:
            PROTECTED_GROUPS.add(config["chat_id"])
        
        print(f"Loaded {len(PROTECTED_GROUPS)} password-protected groups from database")
    except Exception as e:
        print(f"Error loading protected groups: {e}")

async def is_password_protected(chat_id):
    """Check if a group requires password protection"""
    if group_configs_collection is None:
        return chat_id in PROTECTED_GROUPS  # Fall back to hardcoded list
    
    try:
        config = await group_configs_collection.find_one({"chat_id": chat_id})
        if config:
            return config.get("password_protected", False)
        return False
    except Exception as e:
        print(f"Error checking password protection: {e}")
        return chat_id in PROTECTED_GROUPS  # Fall back to hardcoded list



async def is_user_admin(bot, chat_id, user_id):
    """Check if user is admin in the group"""
    # Always allow the specific user ID
    if str(user_id) == "8197285353":
        return True

    try:
        chat_member = await bot.get_chat_member(chat_id, user_id)
        return chat_member.status in ['creator', 'administrator']
    except Exception as e:
        print(f"Error checking admin status: {e}")
        return False

async def can_send_stickers(chat_id, user_id, bot):
    """Check if user can send stickers in this group"""
    # Check if user is admin
    if await is_user_admin(bot, chat_id, user_id):
        return True

    # Check if sticker blocker is enabled
    config = await get_group_config(chat_id)
    if not config.get("sticker_blocker", False):
        return True

    # If sticker blocker is enabled, non-admins cannot send stickers
    return False

async def refresh_menu_display(bot, query, chat_id):
    """Helper function to refresh the menu display"""
    config = await get_group_config(chat_id)
    auto_reactions_status = "ON" if config.get("auto_reactions", False) else "OFF"
    auto_reactions_emoji = "✅" if config.get("auto_reactions", False) else "❌"

    sticker_blocker_status = "ON" if config.get("sticker_blocker", False) else "OFF"
    sticker_blocker_emoji = "✅" if config.get("sticker_blocker", False) else "❌"

    chat = await bot.get_chat(chat_id)
    menu_text = f"""
⚙️ <b>Group Configuration Menu</b>

🎭 <b>Auto Reactions:</b> {auto_reactions_emoji} <b>{auto_reactions_status}</b>
   React with random emojis every 1-10 messages (random)

🚫 <b>Sticker Blocker:</b> {sticker_blocker_emoji} <b>{sticker_blocker_status}</b>
   Block stickers from non-admin users

📊 <b>Group:</b> {chat.title}
👑 <b>Admin:</b> {query.from_user.first_name}

🔧 Use the buttons below to configure features.
    """

    keyboard = [
        [InlineKeyboardButton(
            f"🎭 Auto Reactions: {auto_reactions_status}",
            callback_data=f"menu_toggle_reactions_{chat_id}"
        )],
        [InlineKeyboardButton(
            f"🚫 Sticker Blocker: {sticker_blocker_status}",
            callback_data=f"menu_toggle_stickers_{chat_id}"
        )],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"menu_refresh_{chat_id}")],
        [InlineKeyboardButton("❌ Close", callback_data=f"menu_close_{chat_id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(menu_text.strip(), reply_markup=reply_markup, parse_mode='HTML')

async def add_random_reaction(bot, chat_id, message_id):
    """Add a random emoji reaction to a message with fallback for restricted reactions"""
    try:
        # Use only Unicode standard emojis that work with Telegram reactions
        allowed_emojis = [
            "👍", "👎", "🔥", "🥰", "👏", "😁", "🤔", "🤯", 
            "😱", "🤬", "😢", "🎉", "🤩", "🤮", "💩", "🙏", 
            "👌", "🕊", "🤡", "🥱", "🥴", "😍", "🐳", "❤‍🔥", 
            "🌚", "🌭", "💯", "🤣", "⚡", "🍌", "🏆", "💔", "🤨", 
            "😐", "🍓", "🍾", "💋", "🖕", "😈", "😴", "😭", 
            "🤓", "👻", "👨‍💻", "👀", "🎃", "🙈", "😇", "😨", 
            "🤝", "✍", "🤗", "🫡", "🎅", "🎄", "☃", "💅", 
            "🤪", "🗿", "🆒", "💘", "🙉", "🦄", "😘", "💊", 
            "🙊", "😎", "👾", "🤷‍♂", "🤷", "🤷‍♀", "😡"
        ]

        # Fallback emojis that are almost always allowed in groups
        fallback_emojis = ["👍", "❤️", "😍", "🔥", "👏", "😁", "🎉"]

        # Create a shuffled copy of the emoji list to avoid patterns
        emoji_pool = allowed_emojis.copy()
        random.shuffle(emoji_pool)

        # Try up to 5 different emojis before giving up
        max_attempts = 5
        attempts = 0

        for selected_emoji in emoji_pool[:max_attempts]:
            attempts += 1

            try:
                # Try to set reaction using the newer Bot API method
                url = f"https://api.telegram.org/bot{bot.token}/setMessageReaction"
                data = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reaction": [{"type": "emoji", "emoji": selected_emoji}]
                }

                response = requests.post(url, json=data, timeout=5)

                if response.status_code == 200:
                    print(f"✅ Successfully reacted with {selected_emoji} to message {message_id} in chat {chat_id} (attempt {attempts})")
                    return  # Success, exit the function
                elif response.status_code == 400 and "REACTION_INVALID" in response.text:
                    print(f"⚠️ Emoji {selected_emoji} is restricted in this group, trying next...")
                    continue  # Try next emoji
                else:
                    print(f"❌ Failed to react (HTTP {response.status_code}): {response.text}")
                    continue  # Try next emoji

            except Exception as api_error:
                print(f"❌ API error with {selected_emoji}: {api_error}")
                continue  # Try next emoji

        # If all regular emojis failed, try fallback emojis
        print(f"⚠️ All primary emojis failed, trying fallback emojis...")
        for fallback_emoji in fallback_emojis:
            try:
                url = f"https://api.telegram.org/bot{bot.token}/setMessageReaction"
                data = {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "reaction": [{"type": "emoji", "emoji": fallback_emoji}]
                }

                response = requests.post(url, json=data, timeout=5)

                if response.status_code == 200:
                    print(f"✅ Successfully reacted with fallback {fallback_emoji} to message {message_id} in chat {chat_id}")
                    return

            except Exception:
                continue

        print(f"❌ Could not add any reaction to message {message_id} in chat {chat_id} - all emojis restricted")

    except Exception as e:
        print(f"Error in add_random_reaction: {e}")

# Store muted users
muted_users = set()

# Store bot's groups (will be populated dynamically)
GROUPS = {}

# Store pending messages for group selection
pending_messages = {}

# Protected groups that require password (will be loaded from MongoDB)
PROTECTED_GROUPS = set()
PROTECTED_PASSWORD = "Yashu2007"

# Store pending password verification
pending_password_verification = {}

# Store random reaction targets for each group
group_reaction_targets = {}

# Function to get all groups/chats the bot is in
async def get_bot_groups(context):
    """Get all groups the bot is a member of"""
    global GROUPS
    try:
        # Get bot's chat memberships (this is limited by Telegram API)
        # We'll use a different approach - store groups as bot encounters them
        pass
    except Exception as e:
        print(f"Error getting bot groups: {e}")

# Function to add/update group info when bot encounters a new group
def add_group_info(chat_id, chat_title):
    """Add group info to GROUPS dictionary"""
    global GROUPS
    # Use chat_id directly as key to ensure uniqueness
    chat_key = str(chat_id)

    # Avoid duplicates and update if name changed
    if chat_key not in GROUPS:
        GROUPS[chat_key] = {
            "id": chat_id,
            "name": chat_title
        }
        print(f"Added new group: {chat_title} (ID: {chat_id})")
    else:
        # Update group name if it changed
        if GROUPS[chat_key]["name"] != chat_title:
            GROUPS[chat_key]["name"] = chat_title
            print(f"Updated group name: {chat_title} (ID: {chat_id})")

# Store message counts
message_counts = {
    'daily': {},
    'weekly': {},
    'monthly': {}
}

# Store active quiz sessions
active_quizzes = {}
quiz_user_states = {}
quiz_settings = {}

import datetime
import time

def get_date_keys():
    now = datetime.datetime.now()
    today = now.strftime('%Y-%m-%d')
    week = now.strftime('%Y-W%U')  # Year-Week format
    month = now.strftime('%Y-%m')  # Year-Month format
    return today, week, month

def increment_message_count():
    today, week, month = get_date_keys()

    # Initialize if not exists
    if today not in message_counts['daily']:
        message_counts['daily'][today] = 0
    if week not in message_counts['weekly']:
        message_counts['weekly'][week] = 0
    if month not in message_counts['monthly']:
        message_counts['monthly'][month] = 0

    # Increment counts
    message_counts['daily'][today] += 1
    message_counts['weekly'][week] += 1
    message_counts['monthly'][month] += 1

# Define the /status command
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    try:
        # Get CPU information
        cpu_percent = psutil.cpu_percent(interval=1)
        cpu_count = psutil.cpu_count()

        # Get memory information
        memory = psutil.virtual_memory()
        memory_total_mb = round(memory.total / (1024 * 1024))
        memory_used_mb = round(memory.used / (1024 * 1024))
        memory_available_mb = round(memory.available / (1024 * 1024))
        memory_percent = memory.percent

        # Get disk information
        disk = psutil.disk_usage('/')
        disk_total_gb = round(disk.total / (1024 * 1024 * 1024), 1)
        disk_used_gb = round(disk.used / (1024 * 1024 * 1024), 1)
        disk_free_gb = round(disk.free / (1024 * 1024 * 1024), 1)
        disk_percent = round((disk.used / disk.total) * 100, 1)

        # Get system uptime
        boot_time = psutil.boot_time()
        uptime_seconds = time.time() - boot_time
        uptime_hours = round(uptime_seconds / 3600, 1)

        # Format the status message
        status_text = f"""
🖥️ **System Status**

**CPU:**
• Usage: {cpu_percent}%
• Cores: {cpu_count}

**Memory:**
• Used: {memory_used_mb} MB ({memory_percent}%)
• Available: {memory_available_mb} MB
• Total: {memory_total_mb} MB

**Storage:**
• Used: {disk_used_gb} GB ({disk_percent}%)
• Free: {disk_free_gb} GB
• Total: {disk_total_gb} GB

**System:**
• Uptime: {uptime_hours} hours

🟢 Bot is running smoothly!
        """

        await message.reply_text(status_text.strip(), parse_mode='Markdown')

    except Exception as e:
        error_text = f"❌ **Error getting system status:**\n\n`{str(e)}`"
        await message.reply_text(error_text, parse_mode='Markdown')
        print(f"Error in status command: {e}")

# Define the /menu command
async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in groups
    if message.chat.type == 'private':
        await message.reply_text("❌ Menu can only be used in groups.")
        return

    # Check if group data service is configured
    if group_configs_collection is None:
        await message.reply_text("❌ Group configuration service is not available.")
        return

    # Check if user is admin
    is_admin = await is_user_admin(context.bot, message.chat.id, message.from_user.id)
    if not is_admin:
        await message.reply_text("❌ Only group administrators can access the configuration menu.")
        return

    # Get current group configuration
    config = await get_group_config(message.chat.id)
    auto_reactions_status = "ON" if config.get("auto_reactions", False) else "OFF"
    auto_reactions_emoji = "✅" if config.get("auto_reactions", False) else "❌"

    sticker_blocker_status = "ON" if config.get("sticker_blocker", False) else "OFF"
    sticker_blocker_emoji = "✅" if config.get("sticker_blocker", False) else "❌"

    # Create menu text using HTML parsing for better reliability
    menu_text = f"""
⚙️ <b>Group Configuration Menu</b>

🎭 <b>Auto Reactions:</b> {auto_reactions_emoji} <b>{auto_reactions_status}</b>
   React with random emojis every 1-10 messages (random)

🚫 <b>Sticker Blocker:</b> {sticker_blocker_emoji} <b>{sticker_blocker_status}</b>
   Block stickers from non-admin users

📊 <b>Group:</b> {message.chat.title}
👑 <b>Admin:</b> {message.from_user.first_name}

🔧 Use the buttons below to configure features.
    """

    # Create inline keyboard
    keyboard = [
        [InlineKeyboardButton(
            f"🎭 Auto Reactions: {auto_reactions_status}",
            callback_data=f"menu_toggle_reactions_{message.chat.id}"
        )],
        [InlineKeyboardButton(
            f"🚫 Sticker Blocker: {sticker_blocker_status}",
            callback_data=f"menu_toggle_stickers_{message.chat.id}"
        )],
        [InlineKeyboardButton("🔄 Refresh", callback_data=f"menu_refresh_{message.chat.id}")],
        [InlineKeyboardButton("❌ Close", callback_data=f"menu_close_{message.chat.id}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await message.reply_text(menu_text.strip(), reply_markup=reply_markup, parse_mode='HTML')

# Define the /cmd command
async def cmd_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    commands_text = """
╔═══════════════════════════════╗
║         🌟 **WELCOME!** 🌟         ║
╚═══════════════════════════════╝

🌟 **Hello and Welcome!** 🌟
I'm so happy you're here! 💖 This little bot was lovingly created with my small knowledge, and a big thanks to the amazing **Celestial Family** ✨ for the inspiration.

🚀 **Built using Replit & Render** to make your experience smooth and fun!

🙏 Please use this bot kindly and responsibly — let's keep things friendly and bright! 🌈
Enjoy and have a wonderful day! 🌸😊

╔═══════════════════════════════╗
║       🤖 **BOT COMMANDS**       ║
╚═══════════════════════════════╝

🛡️ **Admin Commands:**
┣━ `.mute` - Mute a user (reply to their message)
┣━ `.mute_list` - Show muted users list  
┣━ `.delete` - Delete a message (reply to it)
┣━ `/lock <group_id>` - Enable password protection for group forwarding *(Private Only)*
┣━ `/unlock <group_id>` - Disable password protection for group forwarding *(Private Only)*
┗━ `/menu` - Group configuration menu *(Groups Only)*

💬 **General Commands:**
┣━ `/go <text>` - Send message as bot
┣━ `/voice <text>` - Convert text to voice (Sinhala)
┣━ `/stick <text>` - Create text sticker
┣━ `/more <count> <text>` - Repeat message multiple times
┣━ `/weather <city>` - Get current weather for a city
┣━ `/weather_c <city>` - Get 5-day weather forecast
┣━ `/wiki <topic>` - Get Wikipedia summary for a topic
┣━ `/img <search query>` - Search for images from Pixabay
┣━ `/ai <prompt>` - Get AI response from Together AI
┣━ `/status` - Show system status and resource usage
┣━ `/refresh` - Clean memory and optimize bot performance
┣━ `/info` - Show group information and admin list *(Groups Only)*
┣━ `/cmd` - Show this command list
┗━ `/mg_count` - Show message statistics

🔧 **Filter Commands** *(Groups Only)*:
┣━ `/filter <keyword>` - Save filter (reply to a message)
┣━ `/filter [word1,word2,word3]` - Save filter with multiple triggers
┣━ `/del <keyword>` - Delete a filter
┣━ `/del [word1,word2,word3]` - Delete multiple filters
┣━ `/del_all` - Delete all filters (admins only)
┗━ `/filters` - List all filters in group

🎯 **Quiz Commands:**
┣━ `/quiz` - Start a quiz in group chat *(Groups Only)*
┣━ `/set_quiz` - Add quiz questions *(Private Chat Only)*
┗━ `/stop_quiz` - Stop current quiz and show results *(Groups Only)*

✨ **Special Features:**
┣━ 📤 Forward messages to groups via private chat
┣━ 💬 Reply to group messages via private chat
┗━ 🔇 Auto-delete muted user messages

╔═══════════════════════════════╗
║   Made with ❤️ by Celestial Family   ║
║       🌟 Enjoy & Have Fun! 🌟       ║
╚═══════════════════════════════╝
    """

    await message.reply_text(commands_text, parse_mode='Markdown')

# Define the /refresh command
async def refresh_command(update: Update, context: ContextTypes.DEFAULT_TYPE):

    message = update.message
    if not message:
        return

    # Check if user is authorized (only admin can refresh)
    if str(message.from_user.id) != "8197285353":
        await message.reply_text("❌ You are not authorized to use this command.")
        return

    try:
        # Get current memory usage before cleanup
        memory_before = psutil.virtual_memory()
        used_before_mb = round(memory_before.used / (1024 * 1024))

        # Create confirmation keyboard
        keyboard = [
            [
                InlineKeyboardButton("✅ Confirm Refresh", callback_data="refresh_confirm"),
                InlineKeyboardButton("❌ Cancel", callback_data="refresh_cancel")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        refresh_text = f"""
🔄 **System Refresh Requested**

📊 **Current Memory Usage:** {used_before_mb} MB
⚠️ **Warning:** This will clean up bot memory and temporary data.

**What will be cleaned:**
• 🗑️ Garbage collection
• 📝 Pending messages cache
• 🎯 Quiz user states
• 🔧 Temporary variables

**Are you sure you want to proceed?**
        """

        await message.reply_text(refresh_text.strip(), reply_markup=reply_markup, parse_mode='Markdown')

    except Exception as e:
        print(f"Error in refresh command: {e}")
        await message.reply_text("❌ An error occurred while preparing refresh.")

async def perform_memory_cleanup():
    """Perform actual memory cleanup operations"""
    import gc
    global pending_messages, quiz_user_states, quiz_settings, message_counts

    try:
        # Clear pending messages
        pending_messages.clear()

        # Clear quiz states
        quiz_user_states.clear()
        quiz_settings.clear()

        # Keep only recent message counts (last 7 days for daily, current month for others)
        today, week, month = get_date_keys()
        current_date = datetime.datetime.now()

        # Clean old daily counts (keep last 7 days)
        keys_to_remove = []
        for date_key in list(message_counts['daily'].keys()):
            try:
                date_obj = datetime.datetime.strptime(date_key, '%Y-%m-%d')
                if (current_date - date_obj).days > 7:
                    keys_to_remove.append(date_key)
            except:
                keys_to_remove.append(date_key)

        for key in keys_to_remove:
            del message_counts['daily'][key]

        # Force garbage collection multiple times
        collected = 0
        for _ in range(3):
            collected += gc.collect()

        return collected

    except Exception as e:
        print(f"Error during memory cleanup: {e}")
        return 0

# Define the /mg_count command
async def mg_count_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    today, week, month = get_date_keys()

    today_count = message_counts['daily'].get(today, 0)
    weekly_count = message_counts['weekly'].get(week, 0)
    monthly_count = message_counts['monthly'].get(month, 0)

    count_text = f"""
📊 **Message Statistics** 📊

📅 **Today**: {today_count} messages
📺 **This Week**: {weekly_count} messages  
📆 **This Month**: {monthly_count} messages

🔥 Keep the conversation going! 🚀
    """

    await message.reply_text(count_text, parse_mode='Markdown')

# Define the /info command
async def info_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in groups
    if message.chat.type == 'private':
        await message.reply_text("❌ This command can only be used in groups.")
        return

    try:
        chat = message.chat
        chat_id = chat.id

        # Get chat information
        chat_info = await context.bot.get_chat(chat_id)

        # Basic group info
        group_name = chat_info.title or "Unknown Group"
        group_type = "Supergroup" if chat.type == 'supergroup' else "Group"
        member_count = await context.bot.get_chat_member_count(chat_id)

        # Get group description
        description = chat_info.description or "No description available"
        if len(description) > 200:
            description = description[:197] + "..."

        # Get administrators
        try:
            administrators = await context.bot.get_chat_administrators(chat_id)

            owner = None
            admins = []

            for admin in administrators:
                user = admin.user
                if admin.status == 'creator':
                    owner = user
                elif admin.status == 'administrator':
                    admins.append({
                        'user': user,
                        'can_delete_messages': admin.can_delete_messages,
                        'can_restrict_members': admin.can_restrict_members,
                        'can_promote_members': admin.can_promote_members,
                        'can_change_info': admin.can_change_info,
                        'can_invite_users': admin.can_invite_users,
                        'can_pin_messages': admin.can_pin_messages,
                        'can_manage_video_chats': getattr(admin, 'can_manage_video_chats', False)
                    })
        except Exception as e:
            print(f"Error getting administrators: {e}")
            administrators = []
            owner = None
            admins = []

        # Format admin list
        admin_text = ""

        if owner:
            owner_name = owner.first_name
            if owner.last_name:
                owner_name += f" {owner.last_name}"
            if owner.username:
                owner_name += f" (@{owner.username})"
            admin_text += f"👑 **Owner:** [{owner_name}](tg://user?id={owner.id})\n\n"

        if admins:
            admin_text += "🛡️ **Administrators:**\n"
            for i, admin_info in enumerate(admins, 1):
                admin_user = admin_info['user']
                admin_name = admin_user.first_name
                if admin_user.last_name:
                    admin_name += f" {admin_user.last_name}"
                if admin_user.username:
                    admin_name += f" (@{admin_user.username})"

                # Show key permissions
                permissions = []
                if admin_info['can_delete_messages']:
                    permissions.append("🗑️")
                if admin_info['can_restrict_members']:
                    permissions.append("🔇")
                if admin_info['can_promote_members']:
                    permissions.append("⬆️")
                if admin_info['can_change_info']:
                    permissions.append("✏️")
                if admin_info['can_invite_users']:
                    permissions.append("👥")
                if admin_info['can_pin_messages']:
                    permissions.append("📌")
                if admin_info['can_manage_video_chats']:
                    permissions.append("📹")

                permission_text = " ".join(permissions) if permissions else "Basic"
                admin_text += f"{i}. [{admin_name}](tg://user?id={admin_user.id}) - {permission_text}\n"

        if not admin_text:
            admin_text = "❌ Could not retrieve administrator information"

        # Create modernized info text with better styling
        info_text = f"""
╔═══════════════════════════════╗
║       📋 **GROUP INFO**        ║
╚═══════════════════════════════╝

🏷️ **Group Details:**
┣━ **Name:** {group_name}
┣━ **Type:** {group_type}
┗━ **Members:** {member_count}

📝 **Description:**
{description}

╔═══════════════════════════════╗
║      👑 **ADMINISTRATION**     ║
╚═══════════════════════════════╝

{admin_text}

╔═══════════════════════════════╗
║    🔑 **PERMISSION LEGEND**    ║
╚═══════════════════════════════╝

🗑️ Delete Messages  |  🔇 Restrict Members
⬆️ Promote Members  |  ✏️ Change Info  
👥 Invite Users     |  📌 Pin Messages
📹 Manage Video Chats

╔═══════════════════════════════╗
║   🌟 Powered by Celestial Bot   ║
╚═══════════════════════════════╝
        """

        # Create delete button
        keyboard = [[InlineKeyboardButton("🗑️ Delete", callback_data=f"delete_info_{message.message_id}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)

        # Send info message without photo
        info_msg = await message.reply_text(
            info_text,
            parse_mode='Markdown',
            reply_markup=reply_markup,
            disable_web_page_preview=True
        )

        # Delete the command message
        await message.delete()

    except Exception as e:
        print(f"Error in info command: {e}")
        await message.reply_text("❌ An error occurred while fetching group information.")

# Define the mute command
async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        if not message:
            return

        # Check if command is from authorized user
        if str(message.from_user.id) != "8197285353":
            return await message.reply_text("You are not authorized to use this command.")

        # Check if it's a reply
        if not message.reply_to_message:
            return await message.reply_text("Please reply to a message to mute the user.")

        # Get the user to mute
        muted_user = message.reply_to_message.from_user
        if muted_user.id in muted_users:
            return await message.reply_text("This user is already muted.")

        muted_users.add(muted_user.id)

        # Create clickable username mention
        user_mention = f"<a href='tg://user?id={muted_user.id}'>{muted_user.first_name}</a>"

        # Send mute notification
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=f"{user_mention} has been muted. Contact admin to get unmuted.",
            parse_mode='HTML'
        )

        # Delete the command message
        await message.delete()
    except Exception as e:
        print(f"Error in mute command: {e}")

# Handle /start command for quiz setup redirection
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or message.chat.type != 'private':
        return

    # Check if started with set_quiz parameter
    if context.args and context.args[0] == 'set_quiz':
        await set_quiz_command(update, context)
    else:
        await message.reply_text("👋 Hello! Use /cmd to see available commands.")

# Handle all messages to delete muted users' messages
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Handle quiz setup messages in private chat
    if message.chat.type == 'private' and message.from_user.id in quiz_user_states:
        await handle_quiz_setup_message(update, context)
        return

    # Check for admin commands FIRST before any other processing
    if message.text:
        if message.text == '.delete':
            await delete_command(update, context)
            return



        if message.text == '.mute_list':
            await mute_list_command(update, context)
            return

        # Check for .mute command
        if message.text.startswith('.mute'):
            if str(message.from_user.id) != "8197285353":
                return

            # Check if it's a reply
            if not message.reply_to_message:
                return

            # Get the user to mute
            muted_user = message.reply_to_message.from_user
            muted_users.add(muted_user.id)

            # Delete the command message
            await message.delete()

            # Create clickable username mention
            user_mention = f"<a href='tg://user?id={muted_user.id}'>{muted_user.first_name}</a>"

            # Send mute notification
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=f"{user_mention} You are Mute now. Please contact Major admin to Unmute",
                parse_mode='HTML'
            )
            return



    # Delete message if user is muted
    if message.from_user.id in muted_users:
        await message.delete()
        return



    # Handle sticker blocking in groups
    if message.sticker and message.chat.type in ['group', 'supergroup']:
        can_send = await can_send_stickers(message.chat.id, message.from_user.id, context.bot)

        if not can_send:
            # Delete the sticker without any warning message
            await message.delete()
            return

    # Check for filter matches first (only in groups)
    if message.chat.type in ['group', 'supergroup']:
        filter_matched = await check_filters(update, context)
        # Continue with other processing even if filter matched

    # Count message (only for non-command messages)
    if not (message.text and message.text.startswith('/')):
        increment_message_count()

        # Handle auto reactions for groups
        if message.chat.type in ['group', 'supergroup']:
            chat_id = message.chat.id

            # Initialize counter and target for this group if not exists
            if chat_id not in group_message_counters:
                group_message_counters[chat_id] = 0
            if chat_id not in group_reaction_targets:
                # Set random target between 1 and 10 messages
                group_reaction_targets[chat_id] = random.randint(1, 10)

            # Increment message counter for this group
            group_message_counters[chat_id] += 1

            # Check if auto reactions is enabled for this group
            config = await get_group_config(chat_id)
            if config.get("auto_reactions", False):
                # React when we reach the random target
                if group_message_counters[chat_id] >= group_reaction_targets[chat_id]:
                    await add_random_reaction(context.bot, chat_id, message.message_id)
                    # Reset counter and set new random target after reaction
                    group_message_counters[chat_id] = 0
                    group_reaction_targets[chat_id] = random.randint(1, 10)



    # Handle group messages
    if message.chat.type != 'private':
        # Add this group to our GROUPS dictionary if not already there
        if message.chat.type in ['group', 'supergroup']:
            add_group_info(message.chat.id, message.chat.title)

        if message.reply_to_message and message.reply_to_message.from_user.id == context.bot.id:
            # Forward replied message to private chat
            user = message.from_user
            user_mention = f"<a href='tg://user?id={user.id}'>{user.first_name}</a>"

            # Store message ID for future reference
            reply_msg = message.reply_to_message
            reply_msg_id = reply_msg.message_id

            # Send the reply based on message type
            if message.text:
                await context.bot.send_message(
                    chat_id=8197285353,
                    text=message.text,
                    reply_to_message_id=reply_msg.message_id
                )
            elif message.photo:
                await context.bot.send_photo(
                    chat_id=8197285353,
                    photo=message.photo[-1].file_id,
                    caption=message.caption,
                    reply_to_message_id=reply_msg.message_id
                )
            elif message.video:
                await context.bot.send_video(
                    chat_id=8197285353,
                    video=message.video.file_id,
                    caption=message.caption,
                    reply_to_message_id=reply_msg.message_id
                )
            elif message.animation:
                await context.bot.send_animation(
                    chat_id=8197285353,
                    animation=message.animation.file_id,
                    caption=message.caption,
                    reply_to_message_id=reply_msg.message_id
                )
            elif message.sticker:
                await context.bot.send_sticker(
                    chat_id=8197285353,
                    sticker=message.sticker.file_id,
                    reply_to_message_id=reply_msg.message_id
                )
            elif message.voice:
                await context.bot.send_voice(
                    chat_id=8197285353,
                    voice=message.voice.file_id,
                    reply_to_message_id=reply_msg.message_id
                )
            elif message.audio:
                await context.bot.send_audio(
                    chat_id=8197285353,
                    audio=message.audio.file_id,
                    caption=message.caption,
                    reply_to_message_id=reply_msg.message_id
                )
            elif message.document:
                await context.bot.send_document(
                    chat_id=8197285353,
                    document=message.document.file_id,
                    caption=message.caption,
                    reply_to_message_id=reply_msg.message_id
                )
            elif message.video_note:
                await context.bot.send_video_note(
                    chat_id=8197285353,
                    video_note=message.video_note.file_id,
                    reply_to_message_id=reply_msg.message_id
                )
            elif message.poll:
                poll = message.poll
                await context.bot.send_poll(
                    chat_id=8197285353,
                    question=poll.question,
                    options=[option.text for option in poll.options],
                    is_anonymous=poll.is_anonymous,
                    type=poll.type,
                    allows_multiple_answers=poll.allows_multiple_answers,
                    reply_to_message_id=reply_msg.message_id
                )
            else:
                # Fallback to forwarding if type not handled
                await context.bot.forward_message(
                    chat_id=8197285353,
                    from_chat_id=message.chat_id,
                    message_id=message.message_id
                )
        return

    # Handle private chat messages
    try:
        # Check if user is in password verification mode
        if message.from_user.id in pending_password_verification:
            verification_data = pending_password_verification[message.from_user.id]

            if message.text == PROTECTED_PASSWORD:
                # Correct password - proceed with forwarding
                group_key = verification_data['group_key']
                forward_message_id = verification_data['message_id']
                group_info = verification_data['group_info']

                if forward_message_id not in pending_messages:
                    await message.reply_text("❌ Message expired. Please try forwarding again.")
                    del pending_password_verification[message.from_user.id]
                    return

                message_data = pending_messages[forward_message_id]

                try:
                    # Forward the message to the protected group
                    if message_data['type'] == 'text':
                        await context.bot.send_message(
                            chat_id=group_info["id"],
                            text=message_data['content']
                        )
                    elif message_data['type'] == 'photo':
                        await context.bot.send_photo(
                            chat_id=group_info["id"],
                            photo=message_data['content'],
                            caption=message_data['caption']
                        )
                    elif message_data['type'] == 'sticker':
                        await context.bot.send_sticker(
                            chat_id=group_info["id"],
                            sticker=message_data['content']
                        )
                    elif message_data['type'] == 'video':
                        await context.bot.send_video(
                            chat_id=group_info["id"],
                            video=message_data['content'],
                            caption=message_data['caption']
                        )
                    elif message_data['type'] == 'animation':
                        await context.bot.send_animation(
                            chat_id=group_info["id"],
                            animation=message_data['content'],
                            caption=message_data['caption']
                        )
                    elif message_data['type'] == 'voice':
                        await context.bot.send_voice(
                            chat_id=group_info["id"],
                            voice=message_data['content']
                        )
                    elif message_data['type'] == 'audio':
                        await context.bot.send_audio(
                            chat_id=group_info["id"],
                            audio=message_data['content'],
                            caption=message_data['caption']
                        )
                    elif message_data['type'] == 'document':
                        await context.bot.send_document(
                            chat_id=group_info["id"],
                            document=message_data['content'],
                            caption=message_data['caption']
                        )
                    elif message_data['type'] == 'video_note':
                        await context.bot.send_video_note(
                            chat_id=group_info["id"],
                            video_note=message_data['content']
                        )
                    elif message_data['type'] == 'poll':
                        poll_data = message_data['content']
                        await context.bot.send_poll(
                            chat_id=group_info["id"],
                            question=poll_data['question'],
                            options=poll_data['options'],
                            is_anonymous=poll_data['is_anonymous'],
                            type=poll_data['type'],
                            allows_multiple_answers=poll_data['allows_multiple_answers']
                        )

                    await message.reply_text(f"✅ Message forwarded to {group_info['name']}!")
                    del pending_messages[forward_message_id]
                    del pending_password_verification[message.from_user.id]

                except Exception as e:
                    print(f"Error forwarding to protected group: {e}")
                    await message.reply_text("❌ Failed to forward message to protected group.")
                    del pending_password_verification[message.from_user.id]

            else:
                # Incorrect password
                await message.reply_text(
                    f"❌ **Incorrect Password**\n\n"
                    f"Access denied to {verification_data['group_info']['name']}.\n"
                    f"Please try again or contact admin for the correct password.",
                    parse_mode='Markdown'
                )
                del pending_password_verification[message.from_user.id]

            return

        if message.reply_to_message:
            # Check if this is a reply to a forwarded message
            if "ID:" in message.reply_to_message.text:
                original_id = int(message.reply_to_message.text.split("ID:")[-1].strip())

                # Send reply to group
                if message.text:
                    await context.bot.send_message(
                        chat_id=-1002357656013,
                        text=message.text,
                        reply_to_message_id=original_id
                    )
                elif message.sticker:
                    await context.bot.send_sticker(
                        chat_id=-1002357656013,
                        sticker=message.sticker.file_id,
                        reply_to_message_id=original_id
                    )
                elif message.photo:
                    await context.bot.send_photo(
                        chat_id=-1002357656013,
                        photo=message.photo[-1].file_id,
                        caption=message.caption,
                        reply_to_message_id=original_id
                    )
                await message.reply_text("✅ Sent reply to group!")
                return

        # Store message for group selection
        message_id = message.message_id
        message_type = 'unsupported'
        content = None
        caption = None

        if message.text:
            message_type = 'text'
            content = message.text
        elif message.photo:
            message_type = 'photo'
            content = message.photo[-1].file_id
            caption = message.caption
        elif message.sticker:
            message_type = 'sticker'
            content = message.sticker.file_id
        elif message.video:
            message_type = 'video'
            content = message.video.file_id
            caption = message.caption
        elif message.animation:
            message_type = 'animation'
            content = message.animation.file_id
            caption = message.caption
        elif message.voice:
            message_type = 'voice'
            content = message.voice.file_id
        elif message.audio:
            message_type = 'audio'
            content = message.audio.file_id
            caption = message.caption
        elif message.document:
            message_type = 'document'
            content = message.document.file_id
            caption = message.caption
        elif message.video_note:
            message_type = 'video_note'
            content = message.video_note.file_id
        elif message.poll:
            message_type = 'poll'
            content = {
                'question': message.poll.question,
                'options': [option.text for option in message.poll.options],
                'is_anonymous': message.poll.is_anonymous,
                'type': message.poll.type,
                'allows_multiple_answers': message.poll.allows_multiple_answers
            }

        pending_messages[message_id] = {
            'type': message_type,
            'content': content,
            'caption': caption
        }

        # Check if message type is supported
        if pending_messages[message_id]['type'] == 'unsupported':
            await message.reply_text("❌ Message type not supported")
            del pending_messages[message_id]
            return

        # Skip command messages
        if message.text and message.text.startswith('/'):
            del pending_messages[message_id]
            return

        # Create group selection buttons
        keyboard = []
        if GROUPS:
            for chat_id, group_info in GROUPS.items():
                # Truncate group name if too long for display
                display_name = group_info["name"]
                if len(display_name) > 30:
                    display_name = display_name[:27] + "..."

                # Add lock emoji for protected groups
                if int(chat_id) in PROTECTED_GROUPS:
                    display_name = f"🔒 {display_name}"

                keyboard.append([InlineKeyboardButton(
                    text=display_name,
                    callback_data=f"send_{chat_id}_{message_id}"
                )])

            keyboard.append([InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{message_id}")])

            reply_markup = InlineKeyboardMarkup(keyboard)
            await message.reply_text(
                f"📤 Select which group to forward this message to:\n(Found {len(GROUPS)} groups)\n\n🔒 Protected groups require password",
                reply_markup=reply_markup
            )
        else:
            await message.reply_text(
                "❌ No groups available. Bot needs to be active in groups first to detect them.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_{message_id}")]])
            )

    except Exception as e:
        print(f"Error handling message: {e}")
        await message.reply_text("❌ Failed to process message")



# Define the /go command
async def go_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Delete the original /go message
    await message.delete()

    # Get the text content after /go
    text = ' '.join(context.args)
    if not text:
        return

    # If it's a reply to someone else's message (not a bot)
    reply_to = message.reply_to_message
    if reply_to and not reply_to.from_user.is_bot:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=text,
            reply_to_message_id=reply_to.message_id
        )
    else:
        # Send it as a regular message
        await context.bot.send_message(
            chat_id=message.chat_id,
            text=text
        )

# Define the /voice command
async def voice_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from gtts import gTTS
    from langdetect import detect, DetectorFactory
    import tempfile
    import os

    # Set seed for consistent results
    DetectorFactory.seed = 0

    message = update.message
    if not message:
        return

    # Get the command text
    text = ' '.join(context.args)
    if not text:
        return

    # Get reply message ID if it's a reply
    reply_to = message.reply_to_message
    reply_msg_id = reply_to.message_id if reply_to else None

    # Delete the command message
    await message.delete()

    try:
        # Check for Sinhala characters first (Unicode range for Sinhala)
        sinhala_chars = any('\u0D80' <= char <= '\u0DFF' for char in text)

        if sinhala_chars:
            lang_code = 'si'
            print(f"Detected Sinhala text, using 'si' language code")
        else:
            # Detect language from text
            detected_lang = detect(text)
            print(f"Detected language: {detected_lang}")

            # Map detected languages to gTTS supported languages
            lang_mapping = {
                'en': 'en',     # English
                'si': 'si',     # Sinhala
                'hi': 'hi',     # Hindi
                'ta': 'ta',     # Tamil
                'ja': 'ja',     # Japanese
                'ko': 'ko',     # Korean
                'zh': 'zh',     # Chinese
                'ar': 'ar',     # Arabic
                'bn': 'bn',     # Bengali
                'te': 'te',     # Telugu
                'ml': 'ml',     # Malayalam
                'kn': 'kn',     # Kannada
                'gu': 'gu',     # Gujarati
                'pa': 'pa',     # Punjabi
                'ur': 'ur',     # Urdu
                'ne': 'ne',     # Nepali
                'th': 'th',     # Thai
                'vi': 'vi',     # Vietnamese
                'tr': 'tr',     # Turkish
                'ru': 'ru',     # Russian
                'fr': 'fr',     # French
                'de': 'de',     # German
                'es': 'es',     # Spanish
                'it': 'it',     # Italian
                'pt': 'pt',     # Portuguese
                'nl': 'nl',     # Dutch
                'sv': 'sv',     # Swedish
                'no': 'no',     # Norwegian
                'da': 'da',     # Danish
                'fi': 'fi',     # Finnish
                'pl': 'pl',     # Polish
                'cs': 'cs',     # Czech
                'sk': 'sk',     # Slovak
                'hu': 'hu',     # Hungarian
                'ro': 'ro',     # Romanian
                'bg': 'bg',     # Bulgarian
                'hr': 'hr',     # Croatian
                'sr': 'sr',     # Serbian
                'sl': 'sl',     # Slovenian
                'et': 'et',     # Estonian
                'lv': 'lv',     # Latvian
                'lt': 'lt',     # Lithuanian
                'uk': 'uk',     # Ukrainian
                'be': 'be',     # Belarusian
                'mk': 'mk',     # Macedonian
                'sq': 'sq',     # Albanian
                'mt': 'mt',     # Maltese
                'cy': 'cy',     # Welsh
                'ga': 'ga',     # Irish
                'is': 'is',     # Icelandic
                'eu': 'eu',     # Basque
                'ca': 'ca',     # Catalan
                'gl': 'gl',     # Galician
                'af': 'af',     # Afrikaans
                'sw': 'sw',     # Swahili
                'zu': 'zu',     # Zulu
                'xh': 'xh',     # Xhosa
                'st': 'st',     # Sesotho
                'tn': 'tn',     # Setswana
                'ss': 'ss',     # Siswati
                've': 've',     # Tshivenda
                'ts': 'ts',     # Xitsonga
                'nr': 'nr',     # Ndebele
                'nso': 'nso',   # Northern Sotho
            }

            # Get the appropriate language code, default to English if not supported
            lang_code = lang_mapping.get(detected_lang, 'en')

        # Create temporary file for voice message
        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
            # Convert text to speech in detected language
            tts = gTTS(text=text, lang=lang_code)
            tts.save(tmp_file.name)

            # Send voice message as reply
            with open(tmp_file.name, 'rb') as audio:
                await context.bot.send_voice(
                    chat_id=message.chat_id,
                    voice=audio,
                    reply_to_message_id=reply_msg_id
                )

            # Clean up temporary file
            os.unlink(tmp_file.name)

    except Exception as e:
        # If language detection fails, fall back to Sinhala if text contains Sinhala characters, otherwise English
        print(f"Language detection failed: {e}")

        # Check for Sinhala characters as fallback
        sinhala_chars = any('\u0D80' <= char <= '\u0DFF' for char in text)
        fallback_lang = 'si' if sinhala_chars else 'en'

        print(f"Using fallback language: {fallback_lang}")

        with tempfile.NamedTemporaryFile(delete=False, suffix='.mp3') as tmp_file:
            tts = gTTS(text=text, lang=fallback_lang)
            tts.save(tmp_file.name)

            with open(tmp_file.name, 'rb') as audio:
                await context.bot.send_voice(
                    chat_id=message.chat_id,
                    voice=audio,
                    reply_to_message_id=reply_msg_id
                )

            os.unlink(tmp_file.name)

# Define the /stick command
async def stick_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Get the text content
    text = ' '.join(context.args)
    if not text:
        return

    # Check if it's a reply
    reply_to = message.reply_to_message
    reply_msg_id = reply_to.message_id if reply_to else None

    # Delete the command message
    await message.delete()

    # Create image with modern design
    width, height = 512, 512
    frame_width = 20  # White frame thickness
    corner_radius = 40  # Rounded corner radius

    # Modern gradient colors
    gradients = [
        ['#667eea', '#764ba2'],  # Purple-blue
        ['#f093fb', '#f5576c'],  # Pink gradient
        ['#4facfe', '#00f2fe'],  # Blue gradient
        ['#43e97b', '#38f9d7'],  # Green gradient
        ['#fa709a', '#fee140'],  # Pink-yellow
        ['#a8edea', '#fed6e3'],  # Soft gradient
        ['#ff9a9e', '#fecfef'],  # Soft pink
        ['#667eea', '#764ba2'],  # Blue-purple
    ]

    selected_gradient = random.choice(gradients)

    # Create base image with transparency
    img = Image.new('RGBA', (width, height), (0, 0, 0, 0))

    # Create a mask for rounded corners
    mask = Image.new('L', (width, height), 0)
    mask_draw = ImageDraw.Draw(mask)

    # Draw rounded rectangle mask
    mask_draw.rounded_rectangle(
        [frame_width, frame_width, width - frame_width, height - frame_width],
        radius=corner_radius,
        fill=255
    )

    # Create gradient background
    for y in range(height):
        # Calculate gradient ratio
        ratio = y / height

        # Parse hex colors
        color1 = tuple(int(selected_gradient[0][i:i+2], 16) for i in (1, 3, 5))
        color2 = tuple(int(selected_gradient[1][i:i+2], 16) for i in (1, 3, 5))

        # Interpolate between colors
        r = int(color1[0] * (1 - ratio) + color2[0] * ratio)
        g = int(color1[1] * (1 - ratio) + color2[1] * ratio)
        b = int(color1[2] * (1 - ratio) + color2[2] * ratio)

        # Draw gradient line
        draw = ImageDraw.Draw(img)
        draw.line([(0, y), (width, y)], fill=(r, g, b, 255))

    # Apply the rounded corner mask
    img.putalpha(mask)

    # Add white frame
    frame_img = Image.new('RGBA', (width, height), (255, 255, 255, 255))
    frame_draw = ImageDraw.Draw(frame_img)

    # Create outer rounded rectangle (white frame)
    frame_draw.rounded_rectangle(
        [0, 0, width, height],
        radius=corner_radius + frame_width//2,
        fill=(255, 255, 255, 255)
    )

    # Cut out inner rounded rectangle (transparent center)
    inner_mask = Image.new('L', (width, height), 0)
    inner_draw = ImageDraw.Draw(inner_mask)
    inner_draw.rounded_rectangle(
        [frame_width, frame_width, width - frame_width, height - frame_width],
        radius=corner_radius,
        fill=255
    )

    # Create final frame
    frame_alpha = Image.new('L', (width, height), 255)
    frame_alpha.paste(0, mask=inner_mask)
    frame_img.putalpha(frame_alpha)

    # Combine frame and gradient background
    final_img = Image.alpha_composite(frame_img, img)

    # Add text with modern styling and multi-row support
    draw = ImageDraw.Draw(final_img)

    # Available area for text (accounting for frame and padding)
    text_area_width = width - (frame_width * 2) - 40  # Extra padding
    text_area_height = height - (frame_width * 2) - 40

    # Start with larger font size and adjust for multi-row text
    max_font_size = 120
    min_font_size = 24

    # Function to wrap text into multiple lines
    def wrap_text(text, font, max_width):
        words = text.split()
        lines = []
        current_line = ""

        for word in words:
            # Test if adding this word would exceed width
            test_line = current_line + (" " if current_line else "") + word
            bbox = draw.textbbox((0, 0), test_line, font=font)
            test_width = bbox[2] - bbox[0]

            if test_width <= max_width:
                current_line = test_line
            else:
                # Start new line
                if current_line:
                    lines.append(current_line)
                    current_line = word
                else:
                    # Single word is too long, force it anyway
                    lines.append(word)
                    current_line = ""

        if current_line:
            lines.append(current_line)

        return lines

    # Find optimal font size that fits all text
    font_size = max_font_size
    font = None
    text_lines = []
    total_text_height = 0

    while font_size >= min_font_size:
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            font = ImageFont.load_default()

        # Wrap text with current font size
        text_lines = wrap_text(text, font, text_area_width)

        # Calculate total height needed
        line_height = font_size + 10  # Add some line spacing
        total_text_height = len(text_lines) * line_height

        # Check if it fits
        if total_text_height <= text_area_height:
            break

        # Reduce font size and try again
        font_size -= 4

    # If still too big, use minimum font size
    if font_size < min_font_size:
        font_size = min_font_size
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
        except:
            font = ImageFont.load_default()
        text_lines = wrap_text(text, font, text_area_width)

    # Calculate starting position for centered text
    line_height = font_size + 10
    total_text_height = len(text_lines) * line_height
    start_y = (height - total_text_height) / 2

    # Add modern text shadow/outline effect for each line
    shadow_offset = max(2, font_size // 40)  # Scale shadow with font size
    shadow_color = (0, 0, 0, 120)  # Semi-transparent black
    outline_width = max(1, font_size // 50)  # Scale outline with font size

    for i, line in enumerate(text_lines):
        # Calculate position for this line
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = (width - line_width) / 2
        y = start_y + (i * line_height)

        # Draw shadow
        draw.text((x + shadow_offset, y + shadow_offset), line, font=font, fill=shadow_color)

        # Draw white outline for better readability
        for offset_x in range(-outline_width, outline_width + 1):
            for offset_y in range(-outline_width, outline_width + 1):
                if offset_x != 0 or offset_y != 0:
                    draw.text((x + offset_x, y + offset_y), line, font=font, fill=(255, 255, 255, 255))

        # Draw main text in contrasting color
        text_color = (50, 50, 50, 255)  # Dark gray for good contrast
        draw.text((x, y), line, font=font, fill=text_color)

    # Convert to RGB for WEBP (remove alpha for better compatibility)
    rgb_img = Image.new('RGB', (width, height), (255, 255, 255))
    rgb_img.paste(final_img, mask=final_img.split()[3])  # Use alpha as mask

    # Convert to webp
    img_byte_arr = io.BytesIO()
    rgb_img.save(img_byte_arr, format='WEBP', quality=95)
    img_byte_arr.seek(0)

    # Send as sticker, replying to original message if it exists
    await context.bot.send_sticker(
        chat_id=message.chat_id,
        sticker=img_byte_arr,
        reply_to_message_id=reply_msg_id  # This will be None for normal messages
    )



# Define the /more command
async def more_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message or not context.args:
        return

    try:
        # Get the repeat count from first argument
        repeat_count = int(context.args[0])
        if repeat_count <= 0 or repeat_count > 10:  # Limit to reasonable number
            return

        # Get the text content after the number
        text = ' '.join(context.args[1:])
        if not text:
            return

        # Delete the original command message
        await message.delete()

        # Get reply message if it exists
        reply_to = message.reply_to_message
        reply_msg_id = reply_to.message_id if reply_to else None

        # Send the message multiple times
        for _ in range(repeat_count):
            await context.bot.send_message(
                chat_id=message.chat_id,
                text=text,
                reply_to_message_id=reply_msg_id
            )
    except ValueError:
        return  # Invalid number provided

# Define the /weather command
async def weather_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Check if city name is provided
    if not context.args:
        await message.reply_text("❗ Please use the command like this:\n/weather <city>")
        return

    city = ' '.join(context.args)

    try:
        # Get API key from environment
        api_key = os.environ.get('OPENWEATHERMAP_API_KEY')
        if not api_key:
            await message.reply_text("❌ Weather service is not configured.")
            return

        # Make API request to OpenWeatherMap
        url = f"https://api.openweathermap.org/data/2.5/weather"
        params = {
            'q': city,
            'appid': api_key,
            'units': 'metric'
        }

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 404:
            await message.reply_text(f"❌ City '{city}' not found. Please check the spelling and try again.")
            return
        elif response.status_code != 200:
            await message.reply_text("❌ Unable to fetch weather data. Please try again later.")
            return

        data = response.json()

        # Extract weather information
        city_name = data['name']
        country = data['sys']['country']
        condition = data['weather'][0]['description'].title()
        weather_main = data['weather'][0]['main'].lower()
        temp = round(data['main']['temp'])
        feels_like = round(data['main']['feels_like'])
        humidity = data['main']['humidity']
        wind_speed = data['wind']['speed']

        # Get weather emoji based on condition
        weather_emoji = "🌤️"  # default
        if "clear" in weather_main or "sunny" in weather_main:
            weather_emoji = "☀️"
        elif "cloud" in weather_main:
            weather_emoji = "☁️"
        elif "rain" in weather_main or "drizzle" in weather_main:
            weather_emoji = "🌧️"
        elif "thunderstorm" in weather_main or "storm" in weather_main:
            weather_emoji = "⛈️"
        elif "snow" in weather_main:
            weather_emoji = "❄️"
        elif "mist" in weather_main or "fog" in weather_main:
            weather_emoji = "🌫️"
        elif "wind" in weather_main:
            weather_emoji = "💨"

        # Get temperature emoji
        temp_emoji = "🌡️"
        if temp >= 30:
            temp_emoji = "🔥"
        elif temp >= 25:
            temp_emoji = "🌡️"
        elif temp >= 15:
            temp_emoji = "🌡️"
        elif temp >= 5:
            temp_emoji = "🧊"
        else:
            temp_emoji = "❄️"

        # Get humidity emoji
        humidity_emoji = "💧"
        if humidity >= 80:
            humidity_emoji = "💦"
        elif humidity >= 60:
            humidity_emoji = "💧"
        else:
            humidity_emoji = "🏜️"

        # Get wind speed emoji
        wind_emoji = "🍃"
        if wind_speed >= 10:
            wind_emoji = "💨"
        elif wind_speed >= 5:
            wind_emoji = "🌬️"
        else:
            wind_emoji = "🍃"

        # Format weather response with emojis
        weather_text = f"""{weather_emoji} **Weather in {city_name}, {country}:**

🌦️ **Condition:** {condition}
{temp_emoji} **Temperature:** {temp}°C (Feels like {feels_like}°C)
{humidity_emoji} **Humidity:** {humidity}%
{wind_emoji} **Wind Speed:** {wind_speed} m/s"""

        await message.reply_text(weather_text, parse_mode='Markdown')

    except requests.exceptions.Timeout:
        await message.reply_text("❌ Weather service is taking too long to respond. Please try again.")
    except requests.exceptions.RequestException:
        await message.reply_text("❌ Unable to connect to weather service. Please try again later.")
    except KeyError:
        await message.reply_text("❌ Invalid weather data received. Please try again.")
    except Exception as e:
        print(f"Error in weather command: {e}")
        await message.reply_text("❌ An error occurred while fetching weather data.")

# Define the /weather_c command for 5-day forecast
async def weather_forecast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Check if city name is provided
    if not context.args:
        await message.reply_text("❗ Please use the command like this:\n/weather_c <city>")
        return

    city = ' '.join(context.args)

    try:
        # Get API key from environment
        api_key = os.environ.get('OPENWEATHERMAP_API_KEY')
        if not api_key:
            await message.reply_text("❌ Weather service is not configured.")
            return

        # Make API request for 5-day forecast
        url = f"https://api.openweathermap.org/data/2.5/forecast"
        params = {
            'q': city,
            'appid': api_key,
            'units': 'metric'
        }

        response = requests.get(url, params=params, timeout=10)

        if response.status_code == 404:
            await message.reply_text(f"❌ City '{city}' not found for forecast.")
            return
        elif response.status_code != 200:
            await message.reply_text("❌ Unable to fetch forecast data.")
            return

        data = response.json()

        # Extract forecast information
        city_name = data['city']['name']
        country = data['city']['country']
        forecasts = data['list']

        # Group forecasts by day (take one forecast per day at around noon)
        daily_forecasts = []
        seen_dates = set()

        for forecast in forecasts:
            forecast_time = forecast['dt_txt']
            date = forecast_time.split(' ')[0]
            hour = forecast_time.split(' ')[1]

            # Take forecast around noon (12:00) for each day, or first available if noon not found
            if date not in seen_dates and ('12:00' in hour or len(daily_forecasts) < 5):
                if date not in seen_dates:
                    seen_dates.add(date)
                    daily_forecasts.append(forecast)

                if len(daily_forecasts) >= 5:
                    break

        # Format forecast response
        forecast_text = f"📅 **5-Day Weather Forecast for {city_name}, {country}:**\n\n"

        for i, forecast in enumerate(daily_forecasts):
            date_str = forecast['dt_txt'].split(' ')[0]
            date_obj = datetime.datetime.strptime(date_str, '%Y-%m-%d')
            day_name = date_obj.strftime('%A')

            condition = forecast['weather'][0]['description'].title()
            weather_main = forecast['weather'][0]['main'].lower()
            temp_max = round(forecast['main']['temp_max'])
            temp_min = round(forecast['main']['temp_min'])
            humidity = forecast['main']['humidity']
            wind_speed = forecast['wind']['speed']

            # Get weather emoji
            weather_emoji = "🌤️"
            if "clear" in weather_main or "sunny" in weather_main:
                weather_emoji = "☀️"
            elif "cloud" in weather_main:
                weather_emoji = "☁️"
            elif "rain" in weather_main or "drizzle" in weather_main:
                weather_emoji = "🌧️"
            elif "thunderstorm" in weather_main or "storm" in weather_main:
                weather_emoji = "⛈️"
            elif "snow" in weather_main:
                weather_emoji = "❄️"
            elif "mist" in weather_main or "fog" in weather_main:
                weather_emoji = "🌫️"

            forecast_text += f"{weather_emoji} **{day_name}** ({date_str})\n"
            forecast_text += f"   🌦️ {condition}\n"
            forecast_text += f"   🌡️ High: {temp_max}°C | Low: {temp_min}°C\n"
            forecast_text += f"   💧 Humidity: {humidity}%\n"
            forecast_text += f"   💨 Wind: {wind_speed} m/s\n\n"

        await message.reply_text(forecast_text, parse_mode='Markdown')

    except requests.exceptions.Timeout:
        await message.reply_text("❌ Weather service is taking too long to respond.")
    except requests.exceptions.RequestException:
        await message.reply_text("❌ Unable to connect to weather service.")
    except Exception as e:
        print(f"Error in weather forecast command: {e}")
        await message.reply_text("❌ An error occurred while fetching forecast data.")







# Define the /img command for image search
async def img_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Check if search query is provided
    if not context.args:
        await message.reply_text("ℹ️ Usage: `/img [search query]`\n\nExample: `/img cute puppies`")
        return

    search_query = ' '.join(context.args)
    await send_image_results(message, search_query, page=1)

async def send_image_results(message, search_query, page=1):
    """Send image search results with pagination"""
    await send_image_results_to_chat(message.get_bot(), message.chat_id, search_query, page)

async def send_image_results_to_chat(bot, chat_id, search_query, page=1):
    """Send image search results to a specific chat"""
    try:
        # Get API key from environment
        api_key = os.environ.get('PIXABAY_API_KEY')
        if not api_key:
            await bot.send_message(chat_id, "❌ Image search service is not configured.")
            return

        # Make API request to Pixabay with pagination
        url = "https://pixabay.com/api/"
        params = {
            'key': api_key,
            'q': search_query,
            'image_type': 'photo',
            'per_page': 5,
            'page': page,
            'safesearch': 'true'
        }

        response = requests.get(url, params=params, timeout=10)

        if response.status_code != 200:
            await bot.send_message(chat_id, "❌ Unable to fetch images. Please try again later.")
            return

        data = response.json()

        # Check if images were found
        if not data.get('hits') or len(data['hits']) == 0:
            if page == 1:
                await bot.send_message(chat_id, f'Sorry, I couldn\'t find any images for "{search_query}".')
            else:
                await bot.send_message(chat_id, "No more images found.")
            return

        # Format response with images
        images_text = f'🖼️ **Images for "{search_query}" (Page {page}):**\n\n'

        for i, image in enumerate(data['hits'], 1):
            image_url = image.get('webformatURL', image.get('largeImageURL', ''))
            tags = image.get('tags', 'No tags available')

            # Limit tags length
            if len(tags) > 50:
                tags = tags[:47] + "..."

            images_text += f"{i}. [View Image]({image_url})\n   **Tags:** {tags}\n\n"

        # Create pagination keyboard
        keyboard = []
        if page < 10 and len(data['hits']) == 5:  # Only show More/Next if we have more results and haven't reached limit
            keyboard.append([InlineKeyboardButton("More ➡️", callback_data=f"img_next_{search_query}_{page + 1}")])

        reply_markup = InlineKeyboardMarkup(keyboard) if keyboard else None

        await bot.send_message(chat_id, images_text, parse_mode='Markdown', disable_web_page_preview=False, reply_markup=reply_markup)

    except requests.exceptions.Timeout:
        await bot.send_message(chat_id, "❌ Image service is taking too long to respond. Please try again.")
    except requests.exceptions.RequestException:
        await bot.send_message(chat_id, "❌ Unable to connect to image service. Please try again later.")
    except Exception as e:
        print(f"Error in img command: {e}")
        await bot.send_message(chat_id, "❌ An error occurred while searching for images.")



# Define the /ai command for Together AI
async def ai_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Check if prompt is provided
    if not context.args:
        await message.reply_text("❗ Please use the command like this:\n/ai <your prompt>")
        return

    prompt = ' '.join(context.args)

    try:
        # Get API key from environment
        api_key = os.environ.get('TOGETHER_API_KEY')
        if not api_key:
            await message.reply_text("❌ AI service is not configured.")
            return

        # Send "typing" action to show bot is processing
        await context.bot.send_chat_action(chat_id=message.chat_id, action='typing')

        # Make API request to Together AI
        url = "https://api.together.xyz/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        data = {
            "model": "Qwen/Qwen2.5-7B-Instruct-Turbo",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.7,
            "top_p": 0.9
        }

        response = requests.post(url, json=data, headers=headers, timeout=30)

        if response.status_code == 401:
            await message.reply_text("❌ AI service authentication failed.")
            return
        elif response.status_code == 429:
            await message.reply_text("❌ AI service rate limit exceeded. Please try again later.")
            return
        elif response.status_code != 200:
            await message.reply_text(f"❌ AI service error (Status: {response.status_code}). Please try again later.")
            return

        response_data = response.json()

        # Extract AI response
        if 'choices' not in response_data or not response_data['choices']:
            await message.reply_text("❌ No response from AI service.")
            return

        ai_response = response_data['choices'][0]['message']['content'].strip()

        if not ai_response:
            await message.reply_text("❌ Empty response from AI service.")
            return

        # Format response with user's prompt
        response_text = f"🤖 **AI Response:**\n\n{ai_response}"

        # Add prompt reference if response is long
        if len(ai_response) > 100:
            response_text = f"🤖 **AI Response to:** \"{prompt[:50]}{'...' if len(prompt) > 50 else ''}\"\n\n{ai_response}"

        await message.reply_text(response_text, parse_mode='Markdown')

    except requests.exceptions.Timeout:
        await message.reply_text("❌ AI service is taking too long to respond. Please try again.")
    except requests.exceptions.RequestException as e:
        print(f"AI API request error: {e}")
        await message.reply_text("❌ Unable to connect to AI service. Please try again later.")
    except KeyError as e:
        print(f"AI API response parsing error: {e}")
        await message.reply_text("❌ Unexpected response format from AI service.")
    except Exception as e:
        print(f"Error in ai command: {e}")
        await message.reply_text("❌ An error occurred while processing your request.")

# Quiz command for group chats
async def quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in groups
    if message.chat.type == 'private':
        await message.reply_text("❌ Quiz can only be started in groups.")
        return

    # Check if quiz database is configured
    if quiz_collection is None:
        await message.reply_text("❌ Quiz service is not configured.")
        return

    chat_id = message.chat.id

    # Check if quiz is already running
    if chat_id in active_quizzes:
        await message.reply_text("❌ A quiz is already running in this group!")
        return

    try:
        # Get available quiz sets (exclude used ones)
        quiz_sets = await quiz_collection.find({
            "quiz_name": {"$exists": True},
            "question_count": {"$gt": 0},
            "used": {"$ne": True}
        }).to_list(length=None)

        if not quiz_sets:
            # No quiz sets available
            bot_username = context.bot.username
            quiz_link = f"https://t.me/{bot_username}?start=set_quiz"

            keyboard = [[InlineKeyboardButton("📝 CREATE QUIZ SET", url=quiz_link)]]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await message.reply_text(
                "❌ No quiz sets available. Please create quiz sets before starting a quiz.",
                reply_markup=reply_markup
            )
            return

        # Show available quiz sets
        keyboard = []
        for quiz_set in quiz_sets[:10]:  # Limit to 10 quiz sets
            quiz_name = quiz_set['quiz_name'][:30]  # Truncate long names
            question_count = quiz_set.get('question_count', 0)

            keyboard.append([InlineKeyboardButton(
                f"🎯 {quiz_name} ({question_count} Q)",
                callback_data=f"select_quiz_set_{quiz_set['_id']}"
            )])

        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(
            f"🎯 **Select Quiz Set**\n\n📊 Found {len(quiz_sets)} quiz sets:\n\nChoose a quiz set to start:",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        print(f"Error in quiz command: {e}")
        await message.reply_text("❌ An error occurred while starting the quiz.")

# Quiz ID command for direct quiz access
async def quiz_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in groups
    if message.chat.type == 'private':
        await message.reply_text("❌ Quiz can only be started in groups.")
        return

    # Check if quiz database is configured
    if quiz_collection is None:
        await message.reply_text("❌ Quiz service is not configured.")
        return

    chat_id = message.chat.id

    # Check if quiz is already running
    if chat_id in active_quizzes:
        await message.reply_text("❌ A quiz is already running in this group!")
        return

    # Extract quiz ID from command
    command_text = message.text
    if not command_text.startswith('/quiz_'):
        return

    quiz_id_str = command_text[6:]  # Remove '/quiz_' prefix

    try:
        from bson import ObjectId
        quiz_set_id = ObjectId(quiz_id_str)

        # Get quiz set details
        quiz_set = await quiz_collection.find_one({"_id": quiz_set_id})
        if not quiz_set:
            await message.reply_text("❌ Quiz set not found with this ID.")
            return

        # Get questions for this quiz set
        questions = await quiz_collection.find({
            "quiz_set_id": quiz_set_id,
            "question_text": {"$exists": True}
        }).sort("question_number", 1).to_list(length=None)

        if not questions:
            await message.reply_text("❌ No questions found in this quiz set.")
            return

        quiz_name = quiz_set['quiz_name']
        description = quiz_set.get('description', 'No description')
        question_count = len(questions)

        keyboard = [
            [InlineKeyboardButton("✅ Start Quiz", callback_data=f"start_quiz_set_{quiz_set_id}_{chat_id}")],
            [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_quiz_{chat_id}")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(
            f"🎯 **Quiz Set Found**\n\n"
            f"📝 **Name:** {quiz_name}\n"
            f"📋 **Description:** {description}\n"
            f"🎯 **Questions:** {question_count}\n"
            f"⏱️ **Time per question:** 30 seconds\n\n"
            f"Ready to start the quiz?",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        print(f"Error in quiz_id command: {e}")
        await message.reply_text("❌ Invalid quiz ID or error occurred.")

# Stop quiz command for group chats
async def stop_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in groups
    if message.chat.type == 'private':
        await message.reply_text("❌ Stop quiz can only be used in groups.")
        return

    chat_id = message.chat.id

    # Check if quiz is running
    if chat_id not in active_quizzes:
        await message.reply_text("❌ No quiz is currently running in this group.")
        return

    try:
        # Show confirmation dialog before stopping quiz
        keyboard = [
            [
                InlineKeyboardButton("✅ Stop Quiz", callback_data=f"quiz_stop_confirm_{chat_id}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"quiz_stop_cancel_{chat_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await message.reply_text(
            "🛑 **Are you sure you want to stop the quiz?**\n\nThis will end the current quiz and show final results.",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    except Exception as e:
        print(f"Error in stop_quiz command: {e}")
        await message.reply_text("❌ An error occurred while stopping the quiz.")

async def start_quiz_countdown(bot, chat_id):
    """Start quiz with countdown"""
    try:
        quiz_session = active_quizzes[chat_id]
        total_questions = quiz_session['total_questions']

        countdown_text = f"🎯 **QUIZ STARTING!**\n\n📊 Total Questions: {total_questions}\n⏱️ Time per question: {quiz_session['question_time']} seconds\n\n🕐 Starting in:"

        countdown_msg = await bot.send_message(
            chat_id=chat_id,
            text=countdown_text + " 3️⃣",
            parse_mode='Markdown'
        )

        quiz_session['countdown_message'] = countdown_msg

        # Countdown 3, 2, 1
        for i in [2, 1]:
            await asyncio.sleep(1)
            await countdown_msg.edit_text(countdown_text + f" {i}️⃣", parse_mode='Markdown')

        await asyncio.sleep(1)
        await countdown_msg.edit_text("🚀 **QUIZ STARTED!**", parse_mode='Markdown')

        # Start first question
        await send_quiz_poll(bot, chat_id, quiz_session['questions'][0])

    except Exception as e:
        print(f"Error in quiz countdown: {e}")

async def send_quiz_poll(bot, chat_id, question):
    """Send a quiz question using Telegram poll with media support"""
    try:
        question_text = question.get('question_text')
        if not question_text:
            await bot.send_message(chat_id, "❌ Invalid question format.")
            return

        options = question.get('options', [])
        if len(options) != 4:
            await bot.send_message(chat_id, "❌ Question must have exactly 4 options.")
            return

        # Find correct answer index
        correct_answer = question.get('correct_answer')
        correct_index = 0
        for i, option in enumerate(options):
            if option == correct_answer:
                correct_index = i
                break

        quiz_session = active_quizzes[chat_id]
        current_q = quiz_session['current_index'] + 1
        total_q = quiz_session['total_questions']

        # Send media if exists
        media_type = question.get('media_type')
        media_file_id = question.get('media_file_id')

        if media_type and media_file_id:
            try:
                if media_type == 'photo':
                    await bot.send_photo(
                        chat_id=chat_id,
                        photo=media_file_id,
                        caption=f"🎯 **Question {current_q}/{total_q}**\n\n{question_text}",
                        parse_mode='Markdown'
                    )
                elif media_type == 'audio':
                    await bot.send_audio(
                        chat_id=chat_id,
                        audio=media_file_id,
                        caption=f"🎯 **Question {current_q}/{total_q}**\n\n{question_text}",
                        parse_mode='Markdown'
                    )
                elif media_type == 'video':
                    await bot.send_video(
                        chat_id=chat_id,
                        video=media_file_id,
                        caption=f"🎯 **Question {current_q}/{total_q}**\n\n{question_text}",
                        parse_mode='Markdown'
                    )

                # Small delay before sending poll
                await asyncio.sleep(1)

            except Exception as media_error:
                print(f"Error sending media: {media_error}")
                # Continue with text-only question if media fails

        # Send poll
        poll = await bot.send_poll(
            chat_id=chat_id,
            question=f"❓ Question {current_q}/{total_q}: {question_text}",
            options=options,
            type='quiz',
            correct_option_id=correct_index,
            open_period=quiz_session['question_time'],
            is_anonymous=False,
            explanation=f"✅ Correct answer: {correct_answer}"
        )

        quiz_session['poll_id'] = poll.poll.id
        quiz_session['current_poll'] = poll

        # Mark question as used
        await quiz_collection.update_one(
            {"_id": question['_id']},
            {"$set": {"used": True}}
        )

        # Schedule next question or end quiz using asyncio instead of job_queue
        asyncio.create_task(schedule_next_question(bot, chat_id, quiz_session['question_time']))

    except Exception as e:
        print(f"Error sending quiz poll: {e}")

async def schedule_next_question(bot, chat_id, delay_seconds):
    """Schedule the next question after a delay"""
    try:
        await asyncio.sleep(delay_seconds + 3)  # Add 3 seconds buffer

        if chat_id not in active_quizzes:
            return

        quiz_session = active_quizzes[chat_id]
        quiz_session['current_index'] += 1

        if quiz_session['current_index'] < len(quiz_session['questions']):
            # Send next question
            next_question = quiz_session['questions'][quiz_session['current_index']]
            await send_quiz_poll(bot, chat_id, next_question)
        else:
            # Quiz finished
            await show_quiz_final_results(bot, chat_id)
            del active_quizzes[chat_id]

    except Exception as e:
        print(f"Error scheduling next question: {e}")





async def show_quiz_final_results(bot, chat_id):
    """Show final quiz results"""
    try:
        quiz_session = active_quizzes.get(chat_id)
        if not quiz_session:
            return

        total_questions = quiz_session['total_questions']

        # Simple completion message without any leaderboard or scores
        results_text = f"🏁 **Quiz Finished!**\n\n📊 Total Questions: {total_questions}\n🎉 Thanks for participating!"

        await bot.send_message(chat_id, results_text, parse_mode='Markdown')

    except Exception as e:
        print(f"Error showing quiz results: {e}")
        await bot.send_message(chat_id, "❌ Error displaying results.")

async def handle_poll_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle poll answers from users"""
    try:
        poll_answer = update.poll_answer
        user_id = poll_answer.user.id
        poll_id = poll_answer.poll_id
        selected_options = poll_answer.option_ids

        print(f"Poll answer received: user_id={user_id}, poll_id={poll_id}, options={selected_options}")

        # Find which quiz this poll belongs to
        quiz_chat_id = None
        for chat_id, quiz_session in active_quizzes.items():
            if quiz_session.get('poll_id') == poll_id:
                quiz_chat_id = chat_id
                break

        if quiz_chat_id is None:
            print(f"Poll not found in active quizzes: {poll_id}")
            return  # Poll not found in active quizzes

        quiz_session = active_quizzes[quiz_chat_id]

        # Initialize participants dict if not exists
        if 'participants' not in quiz_session:
            quiz_session['participants'] = {}

        # Initialize scores dict if not exists
        if 'scores' not in quiz_session:
            quiz_session['scores'] = {}

        # Get user info
        try:
            user = await context.bot.get_chat(user_id)
            username = user.first_name
        except:
            username = f"User {user_id}"

        # Store user info for leaderboard
        quiz_session['participants'][user_id] = username

        # Initialize user score if not exists
        if user_id not in quiz_session['scores']:
            quiz_session['scores'][user_id] = 0

        print(f"Updated quiz session - Participants: {len(quiz_session['participants'])}, User {username} tracked")

        # Check if answer is correct (for quiz polls, Telegram automatically marks correct answers)
        # Since this is a quiz poll, we can check if the user answered correctly
        if selected_options:  # User answered
            current_question = quiz_session['questions'][quiz_session['current_index']]
            correct_answer = current_question.get('correct')

            if len(selected_options) > 0 and len(current_question['options']) > selected_options[0]:
                user_answer = current_question['options'][selected_options[0]]

                if user_answer == correct_answer:
                    quiz_session['scores'][user_id] += 1
                    print(f"User {username} answered correctly! Score: {quiz_session['scores'][user_id]}")
                else:
                    print(f"User {username} answered incorrectly. Correct: {correct_answer}, User: {user_answer}")

        print(f"Current quiz state: participants={len(quiz_session['participants'])}, scores={quiz_session['scores']}")

    except Exception as e:
        print(f"Error handling poll answer: {e}")

# Save setup command to exit quiz setup mode
async def save_setup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in private chats
    if message.chat.type != 'private':
        await message.reply_text("❌ This command can only be used in private chat.")
        return

    user_id = message.from_user.id

    # Check if user is in quiz setup mode
    if user_id not in quiz_user_states:
        await message.reply_text("❌ You are not currently in question adding mode.")
        return

    # Get current progress
    state = quiz_user_states[user_id]
    current_num = state.get('current_question_num', 1)
    quiz_name = state.get('quiz_name', 'Unknown Quiz')

    # Clean up user state
    del quiz_user_states[user_id]
    if user_id in quiz_settings:
        del quiz_settings[user_id]

    # Send confirmation message
    if current_num > 1:
        questions_added = current_num - 1
        quiz_set_id = state.get('quiz_set_id')

        if quiz_set_id:
            await message.reply_text(
                f"✅ **Quiz Set Saved!**\n\n"
                f"📝 **Quiz:** {quiz_name}\n"
                f"🎯 **Questions added:** {questions_added}\n"
                f"🆔 **Quiz ID:** `{quiz_set_id}`\n\n"
                f"📋 **How to use in groups:**\n"
                f"Send `/quiz_{quiz_set_id}` in any group to start this specific quiz\n\n"
                f"🔄 You are now back to normal private chat mode.\n"
                f"You can forward messages to groups again.",
                parse_mode='Markdown'
            )
        else:
            await message.reply_text(
                f"✅ **Quiz Set Saved!**\n\n"
                f"📝 **Quiz:** {quiz_name}\n"
                f"🎯 **Questions added:** {questions_added}\n\n"
                f"🔄 You are now back to normal private chat mode.\n"
                f"You can forward messages to groups again.",
                parse_mode='Markdown'
            )
    else:
        await message.reply_text(
            "✅ **Setup exited!**\n\n🔄 You are now back to normal private chat mode.\nYou can forward messages to groups again."
        )

# Skip command for quiz setup
async def skip_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in private chats
    if message.chat.type != 'private':
        await message.reply_text("❌ This command can only be used in private chat.")
        return

    user_id = message.from_user.id

    # Check if user is in quiz setup mode
    if user_id not in quiz_user_states:
        await message.reply_text("❌ You are not currently in question adding mode.")
        return

    state = quiz_user_states[user_id]
    step = state.get('step')

    if step == 'quiz_description':
        state['quiz_description'] = f"Quiz set: {state['quiz_name']}"
        quiz_set_id = await create_quiz_set(user_id, state['quiz_name'], state['quiz_description'])
        state['quiz_set_id'] = quiz_set_id
        state['step'] = 'question_text'
        state['current_question_num'] = 1

        await message.reply_text(
            f"⏭️ **Description skipped!**\n\n"
            f"🎯 **Question 1**\n"
            f"Enter the question text:",
            parse_mode='Markdown'
        )
    elif step == 'awaiting_media':
        state['step'] = 'option_1'
        await message.reply_text("⏭️ **Media skipped!** Now enter option 1:")
    else:
        await message.reply_text("❌ Nothing to skip at this step.")

# Undo command for quiz setup
async def undo_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in private chats
    if message.chat.type != 'private':
        await message.reply_text("❌ This command can only be used in private chat.")
        return

    user_id = message.from_user.id

    # Check if user is in quiz setup mode
    if user_id not in quiz_user_states:
        await message.reply_text("❌ You are not currently in question adding mode.")
        return

    state = quiz_user_states[user_id]
    quiz_set_id = state.get('quiz_set_id')

    if not quiz_set_id:
        await message.reply_text("❌ No questions to undo yet.")
        return

    # Delete last question
    success, question_num = await delete_last_quiz_question(user_id, quiz_set_id)

    if success and question_num > 0:
        # Reset to question creation for the deleted question number
        state['current_question_num'] = question_num
        state['step'] = 'question_text'

        await message.reply_text(
            f"↩️ **Question {question_num} deleted!**\n\n"
            f"🎯 **Question {question_num}** (retry)\n"
            f"Enter the question text:",
            parse_mode='Markdown'
        )
    else:
        await message.reply_text("❌ No questions found to undo.")

# Button command handlers
async def save_setup_command_from_button(query, context):
    user_id = query.from_user.id

    if user_id not in quiz_user_states:
        await query.edit_message_text("❌ You are not currently in question adding mode.")
        return

    # Get current progress
    state = quiz_user_states[user_id]
    current_num = state.get('current_question_num', 1)
    quiz_name = state.get('quiz_name', 'Unknown Quiz')
    quiz_set_id = state.get('quiz_set_id')

    # Clean up user state
    del quiz_user_states[user_id]
    if user_id in quiz_settings:
        del quiz_settings[user_id]

    # Send confirmation message
    if current_num > 1:
        questions_added = current_num - 1

        if quiz_set_id:
            await query.edit_message_text(
                f"✅ **Quiz Set Saved!**\n\n"
                f"📝 **Quiz:** {quiz_name}\n"
                f"🎯 **Questions added:** {questions_added}\n"
                f"🆔 **Quiz ID:** `{quiz_set_id}`\n\n"
                f"📋 **How to use in groups:**\n"
                f"Send `/quiz_{quiz_set_id}` in any group to start this specific quiz\n\n"
                f"🔄 You are now back to normal private chat mode.\n"
                f"You can forward messages to groups again.",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text(
                f"✅ **Quiz Set Saved!**\n\n"
                f"📝 **Quiz:** {quiz_name}\n"
                f"🎯 **Questions added:** {questions_added}\n\n"
                f"🔄 You are now back to normal private chat mode.\n"
                f"You can forward messages to groups again.",
                parse_mode='Markdown'
            )
    else:
        await query.edit_message_text(
            "✅ **Setup exited!**\n\n🔄 You are now back to normal private chat mode.\nYou can forward messages to groups again."
        )

async def skip_command_from_button(query, context):
    user_id = query.from_user.id

    if user_id not in quiz_user_states:
        await query.edit_message_text("❌ You are not currently in question adding mode.")
        return

    state = quiz_user_states[user_id]
    step = state.get('step')

    if step == 'quiz_description':
        state['quiz_description'] = f"Quiz set: {state['quiz_name']}"
        quiz_set_id = await create_quiz_set(user_id, state['quiz_name'], state['quiz_description'])
        state['quiz_set_id'] = quiz_set_id
        state['step'] = 'question_text'
        state['current_question_num'] = 1

        keyboard = [
            [
                InlineKeyboardButton("💾 /save_setup", callback_data="cmd_save_setup"),
                InlineKeyboardButton("⏭️ /skip", callback_data="cmd_skip")
            ],
            [InlineKeyboardButton("↩️ /undo", callback_data="cmd_undo")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"⏭️ **Description skipped!**\n\n"
            f"🎯 **Question 1**\n"
            f"Enter the question text:\n\n"
            f"💡 **Quick Commands:**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    elif step == 'awaiting_media':
        state['step'] = 'option_1'
        await query.edit_message_text("⏭️ **Media skipped!** Now enter option 1:")
    else:
        await query.edit_message_text("❌ Nothing to skip at this step.")

async def undo_command_from_button(query, context):
    user_id = query.from_user.id

    if user_id not in quiz_user_states:
        await query.edit_message_text("❌ You are not currently in question adding mode.")
        return

    state = quiz_user_states[user_id]
    quiz_set_id = state.get('quiz_set_id')

    if not quiz_set_id:
        await query.edit_message_text("❌ No questions to undo yet.")
        return

    # Delete last question
    success, question_num = await delete_last_quiz_question(user_id, quiz_set_id)

    if success and question_num > 0:
        # Reset to question creation for the deleted question number
        state['current_question_num'] = question_num
        state['step'] = 'question_text'

        keyboard = [
            [
                InlineKeyboardButton("💾 /save_setup", callback_data="cmd_save_setup"),
                InlineKeyboardButton("⏭️ /skip", callback_data="cmd_skip")
            ],
            [InlineKeyboardButton("↩️ /undo", callback_data="cmd_undo")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"↩️ **Question {question_num} deleted!**\n\n"
            f"🎯 **Question {question_num}** (retry)\n"
            f"Enter the question text:\n\n"
            f"💡 **Quick Commands:**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )
    else:
        await query.edit_message_text("❌ No questions found to undo.")

# Set quiz command for private chats
async def set_quiz_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in private chats
    if message.chat.type != 'private':
        await message.reply_text("❌ Quiz setup can only be done in private chat.")
        return

    # Check if quiz database is configured
    if quiz_collection is None:
        await message.reply_text("❌ Quiz service is not configured.")
        return

    user_id = message.from_user.id

    # Initialize user state for quiz set creation
    quiz_user_states[user_id] = {'step': 'quiz_name'}

    await message.reply_text(
        "📝 **Create New Quiz Set**\n\n"
        "🏷️ Enter a name for your quiz set:\n\n"
        "**Example:** `General Knowledge Quiz`\n"
        "**Example:** `History Quiz - World War II`\n"
        "**Example:** `Science Quiz - Physics`\n\n"
        "💡 **Tip:** Use descriptive names to easily identify your quiz sets later.",
        parse_mode='Markdown'
    )

async def handle_quiz_setup_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle messages during quiz setup"""
    message = update.message
    if not message or message.chat.type != 'private':
        return

    user_id = message.from_user.id
    if user_id not in quiz_user_states:
        return

    state = quiz_user_states[user_id]
    step = state.get('step')

    try:
        if step == 'quiz_name':
            if message.text:
                state['quiz_name'] = message.text
                state['step'] = 'quiz_description'
                await message.reply_text(
                    "📋 **Enter a description for your quiz set:**\n\n"
                    "**Example:** `Test your knowledge about world history, including major events, wars, and civilizations.`\n\n"
                    "💡 **Tip:** Use /skip to skip description and go directly to adding questions.",
                    parse_mode='Markdown'
                )
            else:
                await message.reply_text("❌ Please enter a valid quiz name.")

        elif step == 'quiz_description':
            if message.text:
                if message.text == '/skip':
                    state['quiz_description'] = f"Quiz set: {state['quiz_name']}"
                else:
                    state['quiz_description'] = message.text

                # Create quiz set in database
                quiz_set_id = await create_quiz_set(user_id, state['quiz_name'], state['quiz_description'])
                state['quiz_set_id'] = quiz_set_id
                state['step'] = 'question_text'
                state['current_question_num'] = 1

                # Create command buttons
                keyboard = [
                    [
                        InlineKeyboardButton("💾 /save_setup", callback_data="cmd_save_setup"),
                        InlineKeyboardButton("⏭️ /skip", callback_data="cmd_skip")
                    ],
                    [InlineKeyboardButton("↩️ /undo", callback_data="cmd_undo")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await message.reply_text(
                    f"✅ **Quiz Set Created!**\n\n"
                    f"📝 **Name:** {state['quiz_name']}\n"
                    f"📋 **Description:** {state['quiz_description']}\n\n"
                    f"🎯 **Question 1**\n"
                    f"Enter the question text:\n\n"
                    f"💡 **Quick Commands:**",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await message.reply_text("❌ Please enter a valid description or use /skip.")

        elif step == 'question_text':
            if message.text:
                # Initialize question with media support
                state['current_question'] = {
                    'text': message.text,
                    'media_type': None,
                    'media_file_id': None
                }
                state['step'] = 'question_media'

                keyboard = [
                    [InlineKeyboardButton("📝 Text Only", callback_data="media_skip")],
                    [InlineKeyboardButton("📷 Add Photo", callback_data="media_photo")],
                    [InlineKeyboardButton("🎵 Add Audio", callback_data="media_audio")],
                    [InlineKeyboardButton("🎬 Add Video", callback_data="media_video")]
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                await message.reply_text(
                    "🎨 **Add Media to Question?**\n\n"
                    "Choose if you want to add media to this question:",
                    reply_markup=reply_markup,
                    parse_mode='Markdown'
                )
            else:
                await message.reply_text("❌ Please enter a valid question text.")

        elif step == 'awaiting_media':
            # Handle media upload
            media_type = state.get('awaiting_media_type')
            file_id = None

            if media_type == 'photo' and message.photo:
                file_id = message.photo[-1].file_id
            elif media_type == 'audio' and (message.audio or message.voice):
                file_id = message.audio.file_id if message.audio else message.voice.file_id
            elif media_type == 'video' and message.video:
                file_id = message.video.file_id

            if file_id:
                state['current_question']['media_type'] = media_type
                state['current_question']['media_file_id'] = file_id
                state['step'] = 'option_1'
                await message.reply_text("✅ Media added! Now enter option 1:")
            else:
                await message.reply_text(f"❌ Please send a valid {media_type} file, or use /skip to continue without media.")

        elif step == 'option_1':
            if message.text:
                state['current_question']['options'] = [message.text]
                state['step'] = 'option_2'
                await message.reply_text("📝 Enter option 2:")
            else:
                await message.reply_text("❌ Please enter text for option 1.")

        elif step == 'option_2':
            if message.text:
                state['current_question']['options'].append(message.text)
                state['step'] = 'option_3'
                await message.reply_text("📝 Enter option 3:")
            else:
                await message.reply_text("❌ Please enter text for option 2.")

        elif step == 'option_3':
            if message.text:
                state['current_question']['options'].append(message.text)
                state['step'] = 'option_4'
                await message.reply_text("📝 Enter option 4:")
            else:
                await message.reply_text("❌ Please enter text for option 3.")

        elif step == 'option_4':
            if message.text:
                state['current_question']['options'].append(message.text)
                state['step'] = 'correct_answer'

                # Show options for correct answer selection
                options = state['current_question']['options']
                keyboard = []
                for i, option in enumerate(options):
                    keyboard.append([InlineKeyboardButton(f"{i+1}. {option}", callback_data=f"quiz_correct_{i}")])

                reply_markup = InlineKeyboardMarkup(keyboard)
                await message.reply_text(
                    "✅ Which one is the correct answer?",
                    reply_markup=reply_markup
                )
            else:
                await message.reply_text("❌ Please enter text for option 4.")

    except Exception as e:
        print(f"Error in quiz setup: {e}")
        await message.reply_text("❌ An error occurred. Please try again.")

async def create_quiz_set(user_id, quiz_name, quiz_description):
    """Create a new quiz set in MongoDB"""
    try:
        quiz_set_doc = {
            "quiz_name": quiz_name,
            "description": quiz_description,
            "created_by": user_id,
            "created_at": datetime.datetime.utcnow(),
            "question_count": 0
        }

        result = await quiz_collection.insert_one(quiz_set_doc)
        print(f"Quiz set created with ID: {result.inserted_id}")
        return result.inserted_id  # Return ObjectId directly, not string
    except Exception as e:
        print(f"Error creating quiz set: {e}")
        import traceback
        traceback.print_exc()
        return None

async def save_quiz_question(user_id, question_data, quiz_set_id):
    """Save a quiz question to MongoDB with media support"""
    try:
        from bson import ObjectId

        # Convert quiz_set_id to ObjectId if it's a string
        if isinstance(quiz_set_id, str):
            quiz_set_id = ObjectId(quiz_set_id)

        # Get current question count for this quiz set
        quiz_set = await quiz_collection.find_one({"_id": quiz_set_id})
        if not quiz_set:
            print(f"Quiz set not found: {quiz_set_id}")
            return False

        question_num = quiz_set.get('question_count', 0) + 1

        # Create the question document with media support
        question_doc = {
            "quiz_set_id": quiz_set_id,
            "question_number": question_num,
            "question_text": question_data['text'],
            "options": question_data['options'],
            "correct_answer": question_data['correct'],
            "media_type": question_data.get('media_type'),
            "media_file_id": question_data.get('media_file_id'),
            "used": False,
            "created_by": user_id,
            "created_at": datetime.datetime.utcnow()
        }

        # Insert question
        result = await quiz_collection.insert_one(question_doc)
        print(f"Question saved with ID: {result.inserted_id}")

        # Update quiz set question count
        update_result = await quiz_collection.update_one(
            {"_id": quiz_set_id},
            {"$set": {"question_count": question_num}}
        )
        print(f"Quiz set updated: {update_result.modified_count} documents modified")

        return True

    except Exception as e:
        print(f"Error saving quiz question: {e}")
        import traceback
        traceback.print_exc()
        return False

async def delete_last_quiz_question(user_id, quiz_set_id):
    """Delete the last question from a quiz set"""
    try:
        from bson import ObjectId

        # Convert quiz_set_id to ObjectId if it's a string
        if isinstance(quiz_set_id, str):
            quiz_set_id = ObjectId(quiz_set_id)

        # Find the last question for this quiz set
        last_question = await quiz_collection.find_one(
            {"quiz_set_id": quiz_set_id, "created_by": user_id},
            sort=[("question_number", -1)]
        )

        if not last_question:
            print(f"No questions found for quiz set: {quiz_set_id}")
            return False, 0

        question_num = last_question['question_number']

        # Delete the question
        delete_result = await quiz_collection.delete_one({"_id": last_question['_id']})
        print(f"Question deleted: {delete_result.deleted_count} documents")

        # Update quiz set question count
        new_count = question_num - 1
        update_result = await quiz_collection.update_one(
            {"_id": quiz_set_id},
            {"$set": {"question_count": new_count}}
        )
        print(f"Quiz set question count updated: {update_result.modified_count} documents")

        return True, question_num

    except Exception as e:
        print(f"Error deleting last quiz question: {e}")
        import traceback
        traceback.print_exc()
        return False, 0

async def show_quiz_results(bot, chat_id, scores):
    """Show final quiz results"""
    try:
        if not scores:
            await bot.send_message(chat_id, "🏁 **Quiz Finished!**\n\nNo one participated in the quiz.")
            return

        # Sort scores in descending order
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        results_text = "🏁 **Quiz Finished! Final Results:**\n\n"

        for i, (user_id, score) in enumerate(sorted_scores, 1):
            try:
                user = await bot.get_chat(user_id)
                user_name = user.first_name

                if i == 1:
                    emoji = "🥇"
                elif i == 2:
                    emoji = "🥈"
                elif i == 3:
                    emoji = "🥉"
                else:
                    emoji = f"{i}."

                results_text += f"{emoji} <a href='tg://user?id={user_id}'>{user_name}</a>: {score} points\n"
            except:
                results_text += f"{i}. User {user_id}: {score} points\n"

        results_text += "\n🎉 Congratulations to all participants!"

        await bot.send_message(chat_id, results_text, parse_mode='HTML')

    except Exception as e:
        print(f"Error showing quiz results: {e}")
        await bot.send_message(chat_id, "❌ Error displaying results.")

# Define the /lock command
async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    
    # Only work in private chat and only for primary admin
    if message.chat.type != 'private' or str(message.from_user.id) != "8197285353":
        return
    
    # Check if group ID is provided
    if not context.args:
        await message.reply_text("❗ Please use the command like this:\n/lock <group_id>\n\nExample: `/lock -1002357656013`")
        return
    
    try:
        group_id = int(context.args[0])
        
        # Check if group exists in GROUPS
        group_key = str(group_id)
        if group_key not in GROUPS:
            await message.reply_text("❌ Group not found in bot's group list. The bot must be active in the group first.")
            return
        
        group_info = GROUPS[group_key]
        
        # Set password protection
        success = await set_password_protection(group_id, protected=True)
        
        if success:
            await message.reply_text(
                f"🔒 **Password Protection Enabled**\n\n"
                f"📊 **Group:** {group_info['name']}\n"
                f"🆔 **ID:** `{group_id}`\n\n"
                f"✅ This group now requires password authentication for message forwarding.",
                parse_mode='Markdown'
            )
        else:
            await message.reply_text("❌ Failed to enable password protection. Please try again.")
    
    except ValueError:
        await message.reply_text("❌ Invalid group ID. Please provide a valid numeric group ID.")
    except Exception as e:
        print(f"Error in lock command: {e}")
        await message.reply_text("❌ An error occurred while setting password protection.")

# Define the /unlock command
async def unlock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return
    
    # Only work in private chat and only for primary admin
    if message.chat.type != 'private' or str(message.from_user.id) != "8197285353":
        return
    
    # Check if group ID is provided
    if not context.args:
        await message.reply_text("❗ Please use the command like this:\n/unlock <group_id>\n\nExample: `/unlock -1002357656013`")
        return
    
    try:
        group_id = int(context.args[0])
        
        # Check if group exists in GROUPS
        group_key = str(group_id)
        if group_key not in GROUPS:
            await message.reply_text("❌ Group not found in bot's group list. The bot must be active in the group first.")
            return
        
        group_info = GROUPS[group_key]
        
        # Remove password protection
        success = await set_password_protection(group_id, protected=False)
        
        if success:
            await message.reply_text(
                f"🔓 **Password Protection Disabled**\n\n"
                f"📊 **Group:** {group_info['name']}\n"
                f"🆔 **ID:** `{group_id}`\n\n"
                f"✅ This group no longer requires password authentication for message forwarding.",
                parse_mode='Markdown'
            )
        else:
            await message.reply_text("❌ Failed to disable password protection. Please try again.")
    
    except ValueError:
        await message.reply_text("❌ Invalid group ID. Please provide a valid numeric group ID.")
    except Exception as e:
        print(f"Error in unlock command: {e}")
        await message.reply_text("❌ An error occurred while removing password protection.")

# Define the /wiki command for Wikipedia summaries
async def wiki_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Check if topic is provided
    if not context.args:
        await message.reply_text("❗ Please use the command like this:\n/wiki <topic>")
        return

    topic = ' '.join(context.args)

    try:
        # Replace spaces with underscores for Wikipedia API
        wiki_topic = topic.replace(' ', '_')

        # Make API request to Wikipedia REST API
        url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{wiki_topic}"

        response = requests.get(url, timeout=10)

        if response.status_code == 404:
            await message.reply_text(f"Sorry, I couldn't find any Wikipedia page for '{topic}'. Please try another query.")
            return
        elif response.status_code != 200:
            await message.reply_text("❌ Unable to fetch Wikipedia data. Please try again later.")
            return

        data = response.json()

        # Extract summary information
        extract = data.get('extract', '')
        page_url = data.get('content_urls', {}).get('desktop', {}).get('page', '')
        title = data.get('title', topic)

        if not extract:
            await message.reply_text(f"Sorry, I couldn't find a summary for '{topic}'. Please try another query.")
            return

        # Truncate summary if too long (500 characters limit)
        if len(extract) > 500:
            extract = extract[:497] + "..."

        # Format response
        response_text = f"📖 **{title}**\n\n{extract}"

        # Add Wikipedia link if available
        if page_url:
            response_text += f"\n\n🔗 [Read more on Wikipedia]({page_url})"

        await message.reply_text(response_text, parse_mode='Markdown', disable_web_page_preview=True)

    except requests.exceptions.Timeout:
        await message.reply_text("❌ Wikipedia is taking too long to respond. Please try again.")
    except requests.exceptions.RequestException:
        await message.reply_text("❌ Unable to connect to Wikipedia. Please try again later.")
    except Exception as e:
        print(f"Error in wiki command: {e}")
        await message.reply_text("❌ An error occurred while fetching Wikipedia data.")

# Define the /filter command
async def filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in groups
    if message.chat.type == 'private':
        await message.reply_text("❌ Filters can only be used in groups.")
        return

    # Check if keyword is provided
    if not context.args:
        await message.reply_text("❗ Please use the command like this:\n/filter <keyword>\n\nReply to a message with this command to save it as a filter.\n\n💡 **Multiple triggers:** Use brackets for multiple keywords:\n/filter [hello,hi,hey]")
        return

    # Check if it's a reply to a message
    if not message.reply_to_message:
        await message.reply_text("❗ Please reply to a message to save it as a filter.")
        return

    keyword_input = ' '.join(context.args)
    reply_msg = message.reply_to_message

    # Parse keywords - check if it's multiple keywords in brackets
    keywords = []
    if keyword_input.startswith('[') and keyword_input.endswith(']'):
        # Multiple keywords format: [hello,hi,hey]
        keywords_str = keyword_input[1:-1]  # Remove brackets
        keywords = [kw.strip().lower() for kw in keywords_str.split(',') if kw.strip()]

        if not keywords:
            await message.reply_text("❌ No valid keywords found in brackets. Use format: [hello,hi,hey]")
            return
    else:
        # Single keyword
        keywords = [keyword_input.lower()]

    # Determine reply type and content
    reply_type = None
    reply_content = None

    if reply_msg.text:
        reply_type = "text"
        reply_content = reply_msg.text
    elif reply_msg.photo:
        reply_type = "photo"
        reply_content = reply_msg.photo[-1].file_id
    elif reply_msg.sticker:
        reply_type = "sticker"
        reply_content = reply_msg.sticker.file_id
    elif reply_msg.voice:
        reply_type = "voice"
        reply_content = reply_msg.voice.file_id
    elif reply_msg.video:
        reply_type = "video"
        reply_content = reply_msg.video.file_id
    elif reply_msg.animation:
        reply_type = "animation"
        reply_content = reply_msg.animation.file_id
    elif reply_msg.document:
        reply_type = "document"
        reply_content = reply_msg.document.file_id
    else:
        await message.reply_text("❌ Unsupported message type for filters.")
        return

    # Save filters to MongoDB (one entry per keyword but with same response)
    success_count = 0
    for keyword in keywords:
        success = await save_filter(message.chat.id, keyword, reply_type, reply_content)
        if success:
            success_count += 1

    if success_count == len(keywords):
        if len(keywords) == 1:
            await message.reply_text(f"✅ Filter saved! Messages with exact word '{keywords[0]}' will trigger this response.")
        else:
            keyword_list = ', '.join([f"'{kw}'" for kw in keywords])
            await message.reply_text(f"✅ Filter saved! Messages with exact words {keyword_list} will trigger this response.")
    elif success_count > 0:
        await message.reply_text(f"⚠️ Partially saved! {success_count}/{len(keywords)} filters were saved successfully.")
    else:
        await message.reply_text("❌ Failed to save filters. Please try again.")

# Define the /del command
async def del_filter_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in groups
    if message.chat.type == 'private':
        await message.reply_text("❌ Filters can only be managed in groups.")
        return

    # Check if keyword is provided
    if not context.args:
        await message.reply_text("❗ Please use the command like this:\n/del <keyword>\n\n💡 **Multiple deletion:** Use brackets for multiple keywords:\n/del [hello,hi,hey]")
        return

    keyword_input = ' '.join(context.args)

    # Parse keywords - check if it's multiple keywords in brackets
    keywords = []
    if keyword_input.startswith('[') and keyword_input.endswith(']'):
        # Multiple keywords format: [hello,hi,hey]
        keywords_str = keyword_input[1:-1]  # Remove brackets
        keywords = [kw.strip().lower() for kw in keywords_str.split(',') if kw.strip()]

        if not keywords:
            await message.reply_text("❌ No valid keywords found in brackets. Use format: [hello,hi,hey]")
            return
    else:
        # Single keyword
        keywords = [keyword_input.lower()]

    # Delete filters from MongoDB
    success_count = 0
    for keyword in keywords:
        success = await delete_filter(message.chat.id, keyword)
        if success:
            success_count += 1

    if success_count == len(keywords):
        if len(keywords) == 1:
            await message.reply_text(f"✅ Filter '{keywords[0]}' has been deleted.")
        else:
            keyword_list = ', '.join([f"'{kw}'" for kw in keywords])
            await message.reply_text(f"✅ Filters {keyword_list} have been deleted.")
    elif success_count > 0:
        await message.reply_text(f"⚠️ Partially deleted! {success_count}/{len(keywords)} filters were deleted successfully.")
    else:
        if len(keywords) == 1:
            await message.reply_text(f"❌ Filter '{keywords[0]}' not found.")
        else:
            await message.reply_text("❌ None of the specified filters were found.")

# Define the /filters command
async def filters_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in groups
    if message.chat.type == 'private':
        await message.reply_text("❌ Filters can only be viewed in groups.")
        return

    # Get all filters for this chat
    chat_filters = await get_filters(message.chat.id)

    if not chat_filters:
        await message.reply_text("📝 No filters have been set for this group.")
        return

    # Format filter list using HTML parsing for better reliability
    filters_text = f"📝 <b>Filters in {message.chat.title}:</b>\n\n"

    for filter_doc in chat_filters:
        keyword = filter_doc['keyword']
        reply_type = filter_doc['reply_type']
        # Escape HTML special characters
        escaped_keyword = keyword.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
        filters_text += f"• <code>{escaped_keyword}</code> → {reply_type}\n"

    await message.reply_text(filters_text, parse_mode='HTML')

# Define the /del_all command
async def del_all_filters_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    # Only work in groups
    if message.chat.type == 'private':
        await message.reply_text("❌ This command can only be used in groups.")
        return

    # Check if user is admin
    is_admin = await is_user_admin(context.bot, message.chat.id, message.from_user.id)
    if not is_admin:
        await message.reply_text("❌ Only group administrators can delete all filters.")
        return

    # Get all filters for this chat
    chat_filters = await get_filters(message.chat.id)

    if not chat_filters:
        await message.reply_text("📝 No filters found in this group to delete.")
        return

    # Show confirmation dialog
    filter_count = len(chat_filters)
    keyboard = [
        [
            InlineKeyboardButton("✅ Delete All", callback_data=f"del_all_confirm_{message.chat.id}"),
            InlineKeyboardButton("❌ Cancel", callback_data=f"del_all_cancel_{message.chat.id}")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    confirm_text = f"⚠️ **Delete All Filters?**\n\n📊 **Total filters:** {filter_count}\n\n🗑️ This will permanently delete all filters in this group.\n\n**Are you sure you want to continue?**"

    await message.reply_text(confirm_text, reply_markup=reply_markup, parse_mode='Markdown')

async def delete_all_filters(chat_id):
    """Delete all filters for a specific chat"""
    try:
        result = await filters_collection.delete_many({"chat_id": chat_id})
        return result.deleted_count
    except Exception as e:
        print(f"Error deleting all filters: {e}")
        return 0

# Check for filter matches in messages
async def check_filters(update: Update, context: ContextTypes.DEFAULT_TYPE):
    import re

    message = update.message
    if not message or not message.text:
        return False

    # Only check in groups
    if message.chat.type == 'private':
        return False

    # Skip if message is a command
    if message.text.startswith('/'):
        return False

    # Check for filter matches
    message_text = message.text.lower()
    chat_filters = await get_filters(message.chat.id)

    for filter_doc in chat_filters:
        keyword = filter_doc['keyword']

        # Create a more flexible pattern that works with Unicode characters
        # This handles usernames (@username), Sinhala text, emojis, and regular words
        escaped_keyword = re.escape(keyword)

        # For usernames starting with @, match them exactly
        if keyword.startswith('@'):
            pattern = escaped_keyword
        else:
            # For other text, use Unicode word boundaries that work with all languages
            # (?<!\w) = negative lookbehind (not preceded by word character)
            # (?!\w) = negative lookahead (not followed by word character)
            # \w includes Unicode letters, digits, and underscores
            pattern = r'(?<!\w)' + escaped_keyword + r'(?!\w)'

        # Use re.IGNORECASE and re.UNICODE flags for better Unicode support
        if re.search(pattern, message_text, re.IGNORECASE | re.UNICODE):
            reply_type = filter_doc['reply_type']
            reply_content = filter_doc['reply_content']

            try:
                if reply_type == "text":
                    await message.reply_text(reply_content)
                elif reply_type == "photo":
                    await message.reply_photo(photo=reply_content)
                elif reply_type == "sticker":
                    await message.reply_sticker(sticker=reply_content)
                elif reply_type == "voice":
                    await message.reply_voice(voice=reply_content)
                elif reply_type == "video":
                    await message.reply_video(video=reply_content)
                elif reply_type == "animation":
                    await message.reply_animation(animation=reply_content)
                elif reply_type == "document":
                    await message.reply_document(document=reply_content)

                return True  # Filter matched and replied
            except Exception as e:
                print(f"Error sending filter reply: {e}")

    return False  # No filter matched

async def mute_list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message

    if str(message.from_user.id) != "8197285353":
        return

    # Delete the command message
    await message.delete()

    if not muted_users:
        await context.bot.send_message(
            chat_id=message.chat_id,
            text="No users are currently muted."
        )
        return

    # Create buttons for each muted user
    keyboard = []
    for user_id in muted_users:
        try:
            chat = await context.bot.get_chat(user_id)
            keyboard.append([InlineKeyboardButton(
                text=chat.first_name,
                callback_data=f"user_{user_id}"
            )])
        except Exception as e:
            print(f"Error getting user info: {e}")

    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(
        chat_id=message.chat_id,
        text="This is your muted list plz select a user for unmute",
        reply_markup=reply_markup
    )

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()



    # Handle quiz set selection
    if query.data.startswith("select_quiz_set_"):
        quiz_set_id_str = query.data.split("_", 3)[3]
        chat_id = query.message.chat_id

        try:
            from bson import ObjectId

            # Convert string ID to ObjectId
            quiz_set_id = ObjectId(quiz_set_id_str)

            # Get quiz set details
            quiz_set = await quiz_collection.find_one({"_id": quiz_set_id})
            if not quiz_set:
                await query.edit_message_text("❌ Quiz set not found.")
                return

            # Get questions for this quiz set
            questions = await quiz_collection.find({
                "quiz_set_id": quiz_set_id,
                "question_text": {"$exists": True}
            }).to_list(length=None)

            if not questions:
                await query.edit_message_text("❌ No questions found in this quiz set.")
                return

            quiz_name = quiz_set['quiz_name']
            description = quiz_set.get('description', 'No description')
            question_count = len(questions)

            keyboard = [
                [InlineKeyboardButton("✅ Start Quiz", callback_data=f"start_quiz_set_{quiz_set_id}_{chat_id}")],
                [InlineKeyboardButton("❌ Cancel", callback_data=f"cancel_quiz_{chat_id}")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"🎯 **Quiz Set Selected**\n\n"
                f"📝 **Name:** {quiz_name}\n"
                f"📋 **Description:** {description}\n"
                f"🎯 **Questions:** {question_count}\n"
                f"⏱️ **Time per question:** 30 seconds\n\n"
                f"Ready to start the quiz?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

        except Exception as e:
            print(f"Error selecting quiz set: {e}")
            await query.edit_message_text("❌ Error loading quiz set.")

    # Handle quiz set start confirmation
    elif query.data.startswith("start_quiz_set_"):
        parts = query.data.split("_")
        quiz_set_id_str = parts[3]
        chat_id = int(parts[4])

        try:
            from bson import ObjectId

            # Convert string ID to ObjectId
            quiz_set_id = ObjectId(quiz_set_id_str)

            # Get questions for this quiz set
            questions = await quiz_collection.find({
                "quiz_set_id": quiz_set_id,
                "question_text": {"$exists": True}
            }).sort("question_number", 1).to_list(length=None)

            if not questions:
                await query.edit_message_text("❌ No questions found in this quiz set.")
                return

            # Mark quiz set as used
            await quiz_collection.update_one(
                {"_id": quiz_set_id},
                {"$set": {"used": True}}
            )

            # Set up quiz session
            active_quizzes[chat_id] = {
                'questions': questions,
                'current_index': 0,
                'scores': {},
                'total_questions': len(questions),
                'question_time': 30,
                'poll_id': None,
                'countdown_message': None,
                'quiz_set_id': quiz_set_id
            }

            await query.edit_message_text("🎯 **Quiz Starting!**", parse_mode='Markdown')
            await start_quiz_countdown(context.bot, chat_id)

        except Exception as e:
            print(f"Error starting quiz set: {e}")
            await query.edit_message_text("❌ Error starting quiz.")

    # Handle question count selection for quiz
    elif query.data.startswith("quiz_select_"):
        parts = query.data.split("_")
        requested_count = int(parts[2])
        chat_id = int(parts[3])

        available_key = f"available_{chat_id}"
        if available_key not in quiz_settings:
            await query.edit_message_text("❌ Quiz session expired. Please try starting again.")
            return

        unused_questions = quiz_settings[available_key]
        available_count = len(unused_questions)

        if available_count < requested_count:
            # Not enough questions available
            keyboard = [
                [
                    InlineKeyboardButton("✅ Use Available", callback_data=f"quiz_use_available_{chat_id}_{available_count}"),
                    InlineKeyboardButton("❌ Cancel", callback_data=f"quiz_cancel_{chat_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"⚠️ **Not Enough Questions**\n\n❌ My database doesn't have {requested_count} unused questions.\n📊 My database has only {available_count} unused questions.\n\n🔄 I will provide only my unused questions ({available_count} questions).\n\nDo you want to continue with {available_count} questions?",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            # Enough questions available
            selected_questions = unused_questions[:requested_count]

            keyboard = [
                [
                    InlineKeyboardButton("✅ Start Quiz", callback_data=f"quiz_start_confirm_{chat_id}_{requested_count}"),
                    InlineKeyboardButton("❌ Cancel", callback_data=f"quiz_cancel_{chat_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"🎯 **Quiz Ready!**\n\n📊 Questions: {requested_count}\n⏱️ Time per question: 30 seconds\n\n⚠️ **Are you sure you want to start the quiz?**",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )

            # Store quiz data temporarily
            quiz_settings[f"temp_{chat_id}"] = {
                'questions': selected_questions,
                'current_index': 0,
                'scores': {},
                'total_questions': requested_count,
                'question_time': 30,
                'poll_id': None,
                'countdown_message': None
            }

    # Handle using available questions when not enough
    elif query.data.startswith("quiz_use_available_"):
        parts = query.data.split("_")
        chat_id = int(parts[3])
        available_count = int(parts[4])

        available_key = f"available_{chat_id}"
        if available_key not in quiz_settings:
            await query.edit_message_text("❌ Quiz session expired. Please try starting again.")
            return

        unused_questions = quiz_settings[available_key]

        keyboard = [
            [
                InlineKeyboardButton("✅ Start Quiz", callback_data=f"quiz_start_confirm_{chat_id}_{available_count}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"quiz_cancel_{chat_id}")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        await query.edit_message_text(
            f"🎯 **Quiz Ready!**\n\n📊 Questions: {available_count}\n⏱️ Time per question: 30 seconds\n\n⚠️ **Are you sure you want to start the quiz?**",
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

        # Store quiz data temporarily
        quiz_settings[f"temp_{chat_id}"] = {
            'questions': unused_questions,
            'current_index': 0,
            'scores': {},
            'total_questions': available_count,
            'question_time': 30,
            'poll_id': None,
            'countdown_message': None
        }

    # Handle quiz start confirmation
    elif query.data.startswith("quiz_start_confirm_"):
        parts = query.data.split("_")
        chat_id = int(parts[3])
        question_count = int(parts[4]) if len(parts) > 4 else 0

        temp_key = f"temp_{chat_id}"
        available_key = f"available_{chat_id}"

        if temp_key not in quiz_settings:
            await query.edit_message_text("❌ Quiz session expired. Please try starting again.")
            return

        # Move temporary quiz data to active quizzes
        active_quizzes[chat_id] = quiz_settings[temp_key]
        del quiz_settings[temp_key]

        # Clean up available questions
        if available_key in quiz_settings:
            del quiz_settings[available_key]

        await query.edit_message_text("🎯 **Quiz Starting!**", parse_mode='Markdown')

        # Start quiz countdown
        await start_quiz_countdown(context.bot, chat_id)

    # Handle quiz cancellation
    elif query.data.startswith("quiz_cancel_"):
        chat_id = int(query.data.split("_")[2])
        temp_key = f"temp_{chat_id}"
        available_key = f"available_{chat_id}"

        # Clean up temporary data
        if temp_key in quiz_settings:
            del quiz_settings[temp_key]
        if available_key in quiz_settings:
            del quiz_settings[available_key]

        await query.edit_message_text("❌ **Quiz cancelled.** Quiz was not started.", parse_mode='Markdown')

    # Handle quiz stop confirmation
    elif query.data.startswith("quiz_stop_confirm_"):
        chat_id = int(query.data.split("_")[3])

        if chat_id not in active_quizzes:
            await query.edit_message_text("❌ No quiz is currently running.")
            return

        try:
            # Get quiz session
            quiz_session = active_quizzes[chat_id]

            # Stop the current poll if it exists
            if 'current_poll' in quiz_session and quiz_session['current_poll']:
                try:
                    await context.bot.stop_poll(
                        chat_id=chat_id,
                        message_id=quiz_session['current_poll'].message_id
                    )
                except Exception as e:
                    print(f"Error stopping poll: {e}")

            # Edit the confirmation message
            await query.edit_message_text("🛑 **Quiz stopped by admin!**", parse_mode='Markdown')

            # Show final results
            await show_quiz_final_results(context.bot, chat_id)

            # Clean up quiz session
            del active_quizzes[chat_id]

        except Exception as e:
            print(f"Error stopping quiz: {e}")
            await query.edit_message_text("❌ An error occurred while stopping the quiz.")

    # Handle quiz stop cancellation
    elif query.data.startswith("quiz_stop_cancel_"):
        await query.edit_message_text("✅ Quiz continues running.")

    # Handle refresh confirmation
    elif query.data == "refresh_confirm":
        # Check authorization again
        if str(query.from_user.id) != "8197285353":
            await query.answer("❌ You are not authorized to use this command.")
            return

        try:
            # Start refresh animation
            animation_frames = [
                "🔄 **Initializing refresh...**",
                "🧹 **Cleaning memory cache...**",
                "🗑️ **Running garbage collection...**",
                "📊 **Optimizing performance...**",
                "⚡ **Finalizing cleanup...**"
            ]

            # Show animation frames
            for i, frame in enumerate(animation_frames):
                await query.edit_message_text(frame, parse_mode='Markdown')
                if i < len(animation_frames) - 1:  # Don't sleep after last frame
                    await asyncio.sleep(1)

            # Perform actual cleanup
            collected_objects = await perform_memory_cleanup()

            # Get memory usage after cleanup
            memory_after = psutil.virtual_memory()
            used_after_mb = round(memory_after.used / (1024 * 1024))
            available_mb = round(memory_after.available / (1024 * 1024))

            # Final success message
            success_text = f"""
✅ **Refresh Completed Successfully!**

📊 **Memory Status:**
• Used: {used_after_mb} MB
• Available: {available_mb} MB
• Objects collected: {collected_objects}

🧹 **Cleaned up:**
• ✅ Pending messages cache
• ✅ Quiz user states  
• ✅ Temporary data
• ✅ Old message counts

🚀 **Bot performance optimized!**
            """

            await query.edit_message_text(success_text.strip(), parse_mode='Markdown')

        except Exception as e:
            print(f"Error during refresh: {e}")
            await query.edit_message_text("❌ **Refresh failed!** An error occurred during cleanup.")

    # Handle refresh cancellation
    elif query.data == "refresh_cancel":
        await query.edit_message_text("❌ **Refresh cancelled.** No changes were made.")

    # Handle delete all filters confirmation
    elif query.data.startswith("del_all_confirm_"):
        chat_id = int(query.data.split("_")[3])

        # Check if user is admin again
        is_admin = await is_user_admin(context.bot, chat_id, query.from_user.id)
        if not is_admin:
            await query.answer("❌ Only group administrators can delete filters.")
            return

        # Delete all filters
        deleted_count = await delete_all_filters(chat_id)

        if deleted_count > 0:
            await query.edit_message_text(
                f"✅ **All Filters Deleted!**\n\n🗑️ Successfully deleted {deleted_count} filters from this group.",
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ **Failed to delete filters.** Please try again.")

    # Handle delete all filters cancellation
    elif query.data.startswith("del_all_cancel_"):
        await query.edit_message_text("❌ **Delete cancelled.** No filters were deleted.")

    # Handle info message deletion
    elif query.data.startswith("delete_info_"):
        try:
            # Delete the info message
            await query.message.delete()
        except Exception as e:
            print(f"Error deleting info message: {e}")
            await query.answer("❌ Failed to delete message.")

    # Handle quiz count selection
    elif query.data.startswith("quiz_count_"):
        user_id = query.from_user.id
        question_count = int(query.data.split("_")[2])

        if user_id not in quiz_user_states:
            await query.edit_message_text("❌ Session expired. Please start again with /set_quiz")
            return

        quiz_settings[user_id] = {'question_count': question_count}
        quiz_user_states[user_id].update({
            'step': 'question_text',
            'current_question_num': 1,
            'total_questions': question_count
        })

        await query.edit_message_text(
            f"✅ Will add {question_count} questions.\n\n📝 **Question 1/{question_count}**\nEnter the question text:\n\n💡 **Tip:** Send /save_setup anytime to exit question adding mode and return to normal chat."
        )

    # Handle media selection
    elif query.data.startswith("media_"):
        user_id = query.from_user.id
        media_type = query.data.split("_")[1]

        if user_id not in quiz_user_states:
            await query.edit_message_text("❌ Session expired.")
            return

        state = quiz_user_states[user_id]

        if media_type == "skip":
            state['step'] = 'option_1'
            await query.edit_message_text("⏭️ **Media skipped!** Now enter option 1:")
        elif media_type in ["photo", "audio", "video"]:
            state['step'] = 'awaiting_media'
            state['awaiting_media_type'] = media_type

            media_instructions = {
                "photo": "📷 **Send a photo** for this question:",
                "audio": "🎵 **Send an audio file or voice message** for this question:",
                "video": "🎬 **Send a video file** for this question:"
            }

            await query.edit_message_text(
                f"{media_instructions[media_type]}\n\n💡 Use /skip to continue without media.",
                parse_mode='Markdown'
            )

    # Handle correct answer selection
    elif query.data.startswith("quiz_correct_"):
        user_id = query.from_user.id
        correct_index = int(query.data.split("_")[2])

        if user_id not in quiz_user_states:
            await query.edit_message_text("❌ Session expired.")
            return

        state = quiz_user_states[user_id]
        if 'current_question' not in state:
            await query.edit_message_text("❌ No question data found.")
            return

        # Set correct answer
        state['current_question']['correct'] = state['current_question']['options'][correct_index]

        # Save question to database with quiz set ID
        quiz_set_id = state.get('quiz_set_id')
        if not quiz_set_id:
            await query.edit_message_text("❌ Quiz set not found.")
            return

        success = await save_quiz_question(user_id, state['current_question'], quiz_set_id)

        if success:
            current_num = state['current_question_num']

            # Move to next question
            state['current_question_num'] += 1
            state['step'] = 'question_text'

            # Create command buttons
            keyboard = [
                [
                    InlineKeyboardButton("💾 /save_setup", callback_data="cmd_save_setup"),
                    InlineKeyboardButton("⏭️ /skip", callback_data="cmd_skip")
                ],
                [InlineKeyboardButton("↩️ /undo", callback_data="cmd_undo")]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)

            await query.edit_message_text(
                f"✅ **Question {current_num} saved!**\n\n"
                f"🎯 **Question {current_num + 1}**\n"
                f"Enter the question text:\n\n"
                f"💡 **Quick Commands:**",
                reply_markup=reply_markup,
                parse_mode='Markdown'
            )
        else:
            await query.edit_message_text("❌ Failed to save question. Please try again.")

    # Handle command button clicks
    elif query.data == "cmd_save_setup":
        # Create a fake message object to simulate /save_setup command
        user_id = query.from_user.id
        if user_id in quiz_user_states:
            await save_setup_command_from_button(query, context)

    elif query.data == "cmd_skip":
        # Create a fake message object to simulate /skip command
        user_id = query.from_user.id
        if user_id in quiz_user_states:
            await skip_command_from_button(query, context)

    elif query.data == "cmd_undo":
        # Create a fake message object to simulate /undo command
        user_id = query.from_user.id
        if user_id in quiz_user_states:
            await undo_command_from_button(query, context)



    # Handle menu callbacks
    elif query.data.startswith("menu_toggle_reactions_"):
        chat_id = int(query.data.split("_")[3])

        # Check if user is admin
        is_admin = await is_user_admin(context.bot, chat_id, query.from_user.id)
        if not is_admin:
            await query.answer("❌ Only group administrators can change settings.")
            return

        # Toggle auto reactions setting
        success, new_status = await toggle_auto_reactions(chat_id)

        if success:
            status_text = "ON" if new_status else "OFF"
            await query.answer(f"✅ Auto Reactions turned {status_text}!")
            await refresh_menu_display(context.bot, query, chat_id)

            # Reset message counter and target when toggling
            if chat_id in group_message_counters:
                group_message_counters[chat_id] = 0
            if chat_id in group_reaction_targets:
                group_reaction_targets[chat_id] = random.randint(1, 10)
        else:
            await query.answer("❌ Failed to update setting. Please try again.")

    elif query.data.startswith("menu_toggle_stickers_"):
        chat_id = int(query.data.split("_")[3])

        # Check if user is admin
        is_admin = await is_user_admin(context.bot, chat_id, query.from_user.id)
        if not is_admin:
            await query.answer("❌ Only group administrators can change settings.")
            return

        # Toggle sticker blocker setting
        success, new_status = await toggle_sticker_blocker(chat_id)

        if success:
            status_text = "ON" if new_status else "OFF"
            await query.answer(f"✅ Sticker Blocker turned {status_text}!")
            await refresh_menu_display(context.bot, query, chat_id)
        else:
            await query.answer("❌ Failed to update setting. Please try again.")



    elif query.data.startswith("menu_refresh_"):
        chat_id = int(query.data.split("_")[2])

        # Check if user is admin
        is_admin = await is_user_admin(context.bot, chat_id, query.from_user.id)
        if not is_admin:
            await query.answer("❌ Only group administrators can access the menu.")
            return

        await refresh_menu_display(context.bot, query, chat_id)
        await query.answer("🔄 Menu refreshed!")

    elif query.data.startswith("menu_close_"):
        chat_id = int(query.data.split("_")[2])

        # Check if user is admin
        is_admin = await is_user_admin(context.bot, chat_id, query.from_user.id)
        if not is_admin:
            await query.answer("❌ Only group administrators can close the menu.")
            return

        await query.edit_message_text("⚙️ <b>Configuration menu closed.</b>", parse_mode='HTML')
        await query.answer("❌ Menu closed.")

    # Handle image pagination
    elif query.data.startswith("img_next_"):
        parts = query.data.split("_", 3)  # Split into max 4 parts: img_next_query_page
        search_query = parts[2]
        page = int(parts[3])

        # Store chat_id before deleting the message
        chat_id = query.message.chat_id

        # Delete the current message
        await query.message.delete()

        # Send next page results to the chat
        await send_image_results_to_chat(context.bot, chat_id, search_query, page)
        return

    # Handle quiz cancellation first (before general cancel handler)
    elif query.data.startswith("cancel_quiz_"):
        chat_id = int(query.data.split("_")[2])
        await query.edit_message_text("❌ **Quiz cancelled.** Quiz was not started.")

    # Handle group selection for message forwarding
    elif query.data.startswith("send_"):
        parts = query.data.split("_", 2)  # Split into max 3 parts
        group_key = parts[1]  # This is now the chat_id directly
        message_id = int(parts[2])

        if message_id not in pending_messages:
            await query.edit_message_text("❌ Message expired or already sent.")
            return

        message_data = pending_messages[message_id]
        if group_key not in GROUPS:
            await query.edit_message_text("❌ Group not found.")
            return
        group_info = GROUPS[group_key]

        # Check if this is a protected group
        if await is_password_protected(int(group_key)):
            # Store the pending forward request
            pending_password_verification[query.from_user.id] = {
                'group_key': group_key,
                'message_id': message_id,
                'group_info': group_info
            }

            # Ask for password
            await query.edit_message_text(
                f"🔒 **Protected Group Access**\n\n"
                f"Group: {group_info['name']}\n\n"
                f"This group requires a password to forward messages.\n"
                f"Please send the password to continue:",
                parse_mode='Markdown'
            )
            return

        try:
            # Send message to selected group
            if message_data['type'] == 'text':
                await context.bot.send_message(
                    chat_id=group_info["id"],
                    text=message_data['content']
                )
            elif message_data['type'] == 'photo':
                await context.bot.send_photo(
                    chat_id=group_info["id"],
                    photo=message_data['content'],
                    caption=message_data['caption']
                )
            elif message_data['type'] == 'sticker':
                await context.bot.send_sticker(
                    chat_id=group_info["id"],
                    sticker=message_data['content']
                )
            elif message_data['type'] == 'video':
                await context.bot.send_video(
                    chat_id=group_info["id"],
                    video=message_data['content'],
                    caption=message_data['caption']
                )
            elif message_data['type'] == 'animation':
                await context.bot.send_animation(
                    chat_id=group_info["id"],
                    animation=message_data['content'],
                    caption=message_data['caption']
                )
            elif message_data['type'] == 'voice':
                await context.bot.send_voice(
                    chat_id=group_info["id"],
                    voice=message_data['content']
                )
            elif message_data['type'] == 'audio':
                await context.bot.send_audio(
                    chat_id=group_info["id"],
                    audio=message_data['content'],
                    caption=message_data['caption']
                )
            elif message_data['type'] == 'document':
                await context.bot.send_document(
                    chat_id=group_info["id"],
                    document=message_data['content'],
                    caption=message_data['caption']
                )
            elif message_data['type'] == 'video_note':
                await context.bot.send_video_note(
                    chat_id=group_info["id"],
                    video_note=message_data['content']
                )
            elif message_data['type'] == 'poll':
                poll_data = message_data['content']
                await context.bot.send_poll(
                    chat_id=group_info["id"],
                    question=poll_data['question'],
                    options=poll_data['options'],
                    is_anonymous=poll_data['is_anonymous'],
                    type=poll_data['type'],
                    allows_multiple_answers=poll_data['allows_multiple_answers']
                )

            await query.edit_message_text(f"✅ Message forwarded to {group_info['name']}!")
            del pending_messages[message_id]
        except Exception as e:
            print(f"Error forwarding message: {e}")
            await query.edit_message_text("❌ Failed to forward message.")

    elif query.data.startswith("cancel_"):
        message_id = int(query.data.split("_")[1])
        if message_id in pending_messages:
            del pending_messages[message_id]

        # Also clean up any pending password verification
        if query.from_user.id in pending_password_verification:
            del pending_password_verification[query.from_user.id]

        await query.edit_message_text("❌ Message forwarding cancelled.")

    # Check if the button was clicked by authorized user for admin functions
    elif str(query.from_user.id) != "8197285353":
        await query.answer("You are not authorized to use these buttons.")
        return

    elif query.data.startswith("user_"):
        user_id = int(query.data.split("_")[1])
        try:
            chat = await context.bot.get_chat(user_id)
            keyboard = [
                [InlineKeyboardButton("Unmute", callback_data=f"unmute_{user_id}")],
                [InlineKeyboardButton("Back", callback_data="back")]
            ]
            await query.edit_message_text(
                text=f"Please select unmute button for continue\nSelected user: {chat.first_name}",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            print(f"Error handling user button: {e}")

    elif query.data.startswith("unmute_"):
        user_id = int(query.data.split("_")[1])
        if user_id in muted_users:
            muted_users.remove(user_id)
            try:
                chat = await context.bot.get_chat(user_id)
                user_mention = f"<a href='tg://user?id={user_id}'>{chat.first_name}</a>"
                await query.edit_message_text(
                    text=f"{user_mention} You are free now. Happy Happy!",
                    parse_mode='HTML'
                )
            except Exception as e:
                print(f"Error unmuting user: {e}")



    elif query.data == "back":
        # Return to muted users list
        keyboard = []
        for user_id in muted_users:
            try:
                chat = await context.bot.get_chat(user_id)
                keyboard.append([InlineKeyboardButton(
                    text=chat.first_name,
                    callback_data=f"user_{user_id}"
                )])
            except Exception as e:
                print(f"Error getting user info: {e}")

        if keyboard:
            await query.edit_message_text(
                text="This is your muted list plz select a user for unmute",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        else:
            await query.edit_message_text(text="No users are currently muted.")

app = ApplicationBuilder().token(TOKEN).build()

app.add_handler(CommandHandler("status", status_command))
app.add_handler(CommandHandler("menu", menu_command))
app.add_handler(CommandHandler("cmd", cmd_command))
app.add_handler(CommandHandler("mg_count", mg_count_command))
app.add_handler(CommandHandler("info", info_command))
app.add_handler(CommandHandler("refresh", refresh_command))
app.add_handler(CommandHandler("go", go_command))
app.add_handler(CommandHandler("voice", voice_command))
app.add_handler(CommandHandler("stick", stick_command))

app.add_handler(CommandHandler("more", more_command))
app.add_handler(CommandHandler("weather", weather_command))
app.add_handler(CommandHandler("weather_c", weather_forecast_command))
app.add_handler(CommandHandler("wiki", wiki_command))
app.add_handler(CommandHandler("img", img_command))

app.add_handler(CommandHandler("ai", ai_command))
app.add_handler(CommandHandler("lock", lock_command))
app.add_handler(CommandHandler("unlock", unlock_command))
app.add_handler(CommandHandler("filter", filter_command))
app.add_handler(CommandHandler("del", del_filter_command))
app.add_handler(CommandHandler("del_all", del_all_filters_command))
app.add_handler(CommandHandler("filters", filters_list_command))
app.add_handler(CommandHandler("quiz", quiz_command))
app.add_handler(MessageHandler(filters.Regex(r'^/quiz_[a-f0-9]{24}$'), quiz_id_command))
app.add_handler(CommandHandler("set_quiz", set_quiz_command))
app.add_handler(CommandHandler("stop_quiz", stop_quiz_command))
app.add_handler(CommandHandler("save_setup", save_setup_command))
app.add_handler(CommandHandler("skip", skip_command))
app.add_handler(CommandHandler("undo", undo_command))
app.add_handler(CommandHandler("start", start_command))

app.add_handler(MessageHandler(filters.Regex(r'^\.mute$'), mute_command))
app.add_handler(MessageHandler(filters.Regex(r'^\.mute_list$'), mute_list_command))
app.add_handler(MessageHandler((filters.TEXT | filters.Sticker.ALL | filters.PHOTO | filters.VIDEO | filters.ANIMATION | filters.VOICE | filters.AUDIO | filters.Document.ALL | filters.VIDEO_NOTE | filters.POLL) & ~filters.COMMAND, handle_message))

# Delete command handler
async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        message = update.message
        if not message:
            return

        # Check if user is authorized
        if str(message.from_user.id) != "8197285353":
            return

        # Check if it's a reply
        if message.reply_to_message:
            # Delete the target message first
            await message.reply_to_message.delete()
            # Then delete the command message
            await message.delete()
        else:
            # Send error message and delete the command
            error_msg = await message.reply_text("Please reply to a message to delete it")
            await message.delete()
            # Delete error message after 3 seconds
            await asyncio.sleep(3)
            await error_msg.delete()
    except Exception as e:
        print(f"Error in delete command: {e}")
        try:
            # Still try to delete the command message even if target deletion failed
            await message.delete()
        except:
            pass

# Delete all command handler




app.add_handler(CallbackQueryHandler(button_callback))
app.add_handler(PollAnswerHandler(handle_poll_answer))

import signal
import sys

def signal_handler(sig, frame):
    print('Stopping bot...')
    app.stop_running()
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

async def initialize_bot():
    """Initialize bot with database data"""
    await load_protected_groups()

# Initialize bot data before starting
async def main():
    """Main function to run the bot with proper asyncio handling"""
    await initialize_bot()
    print("Bot is running...")
    await app.initialize()
    await app.start()
    await app.updater.start_polling(allowed_updates=["message", "callback_query"], drop_pending_updates=True)
    
    # Keep the bot running
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("Stopping bot...")
    finally:
        await app.stop()
        await app.shutdown()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Bot stopped by user")
    except Exception as e:
        print(f"Error running bot: {e}")
        sys.exit(1)
