# DISCLAIMER
# All right reserved, no responsibility taken. Don't judge the code too harshly, I am not a pro.

# FEATURES
# - Description to users about how to use this feature
# - Update automatically whenever the stockpiles are updated by officers
# - Listing of all the stockpiles by location, in a single post.
# - Listing of who/when someone have updated a stockpile location, and how much time remains until it goes public.
# - User manages stockpiles in a simple post, runtime storage, nothing complex, dbs, etc 
# - Pushing ping notification to users when conditions (update, edit, low time occures) met
# - Modestly customisable
# - Handles the adding of any regional indicator character, and removes the unusued one related data from runtime storage
#   Only works with regional characters as emotes. Look the matter up for more info if needed.
# - Adds the available reactions automatically to the post

# NOTE
# - Send (edit) message is limited to 2000 characters, that is why the message was separated to multiple parts (desc + list)
# - Currently updating the list does not resets the timer. I guess this is correct behaviour, but the user better update said site's timers.
# - Before Python 3.12 time now was checkd as
#        datetime.datetime.utcnow().timestamp()
#   however they modified it afterward to 
#        datetime.datetime.now(datetime.timezone.utc).timestamp()
#   When deploying to PYthon 3.12 or older environment this could be an issue
# - OAuth2 was something like bot/application.commands , with perms:
#   read-send-manage messages/ add reactions / maybe something else, idk, I dont remember fully

# Import and stuffs
import discord                              # install as discord.py
from discord.ext import tasks, commands
import datetime

##############################################
########## EDIT BETWEEN THESE LINES ##########
##############################################
TOKEN = "YOUR_DC_BOT_TOKEN_COMES_HERE"      # As String, BOT TOKEN comes here
CHANNEL_ID = 111111111111111111            # As Integer, The channel ID that the bot will use to create, manage and remove post within.
SOURCE_CHANNEL_ID = 22222222222222222     # As Integer, The channel ID that holds the human edited source datas, including stockpiles and desc.
SOURCE_MESSAGE_ID = 33333333333333333     # As Integer, The post that has the stockpile related informations.
DESK_MESSAGE_ID = 44444444444444444       # As Integer, The post that has the header/description related information.
DEFAULT_TIMESTAMP_ERROR_MESSAGE = "Hátralévő idő: ismeretlen"   # Default message when the stockpile related data is not presen/available.
USER_GROUPS_TO_BE_NOTIFIED_MSG_TEXT = "@everyone"       # Notification will be sent to these everyone/users/roles. 
                                                        # Multiple can be listed in the same string, it should be fine. Could other text as well
STOCKPILE_EXPIRATION_TIME = 50                          # The number of horus it is needed for the reserved stockpile to expire. In hours.
ISDEBUG = False                      # Turns ON-OFF the print messages.
##############################################
##############################################

# Other variables and stuffs
MESSAGE_ID = None                   # Keep as None, The main message ID that will be edited by the bot, and stores storage stuffs. Will be set later.
HEADER_MESSAGE_ID = None            # Keep as None, The header message ID that will be edited by the bot, and stores description stuffs. Will be set later.
#NOTIFICATION_MESSAGE_ID = None      # The notification message ID that will be used to send notifications to people in case of need. Will be set later.
notif_wait_until_ready = False      # kinda uselss, keeping it for now anyway
status_data = {}                    # stores in runtime all the stockpile time related information

intents = discord.Intents.default()
intents.message_content = True
intents.messages = True             # added afterward
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Event that checks when a post, specifically the stockpile one has been edited, and fires an update
# TODO maybe the two message function is not needed
@bot.event
async def on_raw_message_edit(payload):
    if payload.message_id != SOURCE_MESSAGE_ID:
        return
        
    print ("Stockpile list's post has been edited ...")

    _message = (await (await bot.fetch_channel(CHANNEL_ID)).fetch_message(MESSAGE_ID)) 
    await update_status_message_new(_message) 
    await add_reaction_options(_message)
    await updates_desc_text()

# Event that does the initialisation, clears the channel, sets up the messages, and starts the loop. Only started once per runtime
@bot.event
async def on_ready():
    print ("Initiation stockpile timer bot ...")
    print(f"Logged in as {bot.user}")

    channel = bot.get_channel(CHANNEL_ID)
    await clear_channel(CHANNEL_ID)

    global HEADER_MESSAGE_ID
    global MESSAGE_ID

    if HEADER_MESSAGE_ID is None:
        msg = await channel.send("Initiating header message ...")
        HEADER_MESSAGE_ID = msg.id
        await updates_desc_text()

    if MESSAGE_ID is None:
        msg = await channel.send("Initiating stockpile status message ...")
        MESSAGE_ID = msg.id

    hourly_check.start()
    
    global notif_wait_until_ready
    notif_wait_until_ready = True

    await add_reaction_options((await (await bot.fetch_channel(CHANNEL_ID)).fetch_message(MESSAGE_ID)) )

# Event for the reaction handling, and storing stockpile location related data
@bot.event
async def on_reaction_add(reaction, user):
    if user.bot:
        return

    if reaction.message.id != MESSAGE_ID:
        return

    now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())

    status_data[str(reaction.emoji)] = {
        "user": user.id,
        "timestamp_checked": now,
        "timestamp_expires": now + (STOCKPILE_EXPIRATION_TIME * 60 * 60)
    }

    await update_status_message_new(reaction.message)
    await reaction.remove(user)

# Handlers the description post's updates
async def updates_desc_text():
    print ("Updating description post ...")

    msg = (await bot.get_channel(CHANNEL_ID).fetch_message(HEADER_MESSAGE_ID))

    if msg == None:
        return

    cont = (await bot.get_channel(SOURCE_CHANNEL_ID).fetch_message(DESK_MESSAGE_ID)).content
    cont = cont + "\n\n" + "**Stockpile kódok utoljára módosítvalettek: [" + f"<t:{(int((await (await bot.fetch_channel(SOURCE_CHANNEL_ID)).fetch_message(SOURCE_MESSAGE_ID)).edited_at.timestamp()))}:F>" + "]**"
    await msg.edit(content=cont)

    await send_and_delete_notification_message()

# Checks if a line's first character is a regional indicator or not.
def starts_with_regional_indicator(line: str):
    if not line:
        return False

    codepoint = ord(line[0])
    return 0x1F1E6 <= codepoint <= 0x1F1FF

# Checks if data for said location exists or not.
async def check_status_entry(status_data: dict, key: str):
    data = status_data.get(key)

    if data is None:
        return False
    else:
        return True

# Fetches the data of a said location
async def get_status_entry(status_data: dict, key: str):
    data = status_data.get(key)
    if (ISDEBUG):
        print (["--Status_data and key--", status_data, key])
        print (["--Actual data under key from above--",data])

    return (
        data.get("user"),
        data.get("timestamp_checked"),
        data.get("timestamp_expires")
    )

# It parses trough the strockpile source post and returns the list
def parse_to_list(msg_src: str):
    result = []
    temp_line = ""
    followup_content = False
    for raw_line in msg_src.splitlines():
        line = raw_line.rstrip()
        
        if (ISDEBUG):
            print (starts_with_regional_indicator(line))

        if (followup_content):
            temp_line = temp_line + line + "\n"
        else:
            temp_line = ""

        # handles starting emoji if its a regional indicator
        if (starts_with_regional_indicator(line)):
            result.append(line)
            followup_content = True

        # Checks for when code content ends 
        if (line[-1:] == "`"):
            temp_line = temp_line[:-1]
            result.append(temp_line)
            temp_line = ""
            followup_content = False
            continue

    return result

# Compares the currently runtime stored stockpile data (source_data), and the current stockpile msg, and remvoes the ones that are no longer in the current one
async def manage_storage_data(data, source_current_members):
    for key in list(data.keys()): 
        if key not in source_current_members:
            del data[key]

# Add available reactions to the stockpile message, so the user can interact with them more easily. Also calls manage_stockpile_data for cleanup
async def add_reaction_options(message):
    msg_src = await bot.get_channel(SOURCE_CHANNEL_ID).fetch_message(SOURCE_MESSAGE_ID)
    msg_src_cont = parse_to_list(msg_src.content)
    b_spacer = 0
    all_available_reaction = []

    for _element in msg_src_cont: 
        b_spacer = b_spacer + 1
        if (b_spacer == 1):
            if (starts_with_regional_indicator(_element)):
                all_available_reaction.append(_element[0])
        if (b_spacer == 2):
            b_spacer = 0

    await message.clear_reactions()
    for emoji in all_available_reaction:
        await message.add_reaction(emoji)

    await manage_storage_data(status_data, all_available_reaction)

# Handles editing, managing, updating the stockpile post
async def update_status_message_new(message):
    print ("Updating status message ...")
    msg_src = await bot.get_channel(SOURCE_CHANNEL_ID).fetch_message(SOURCE_MESSAGE_ID)
    if (ISDEBUG):
        print ("---Message source as raw---")
        print (msg_src.content)
        print ("--------------------------")

    msg_src_cont = parse_to_list(msg_src.content)
    if (ISDEBUG):
        print ("---Parsed input message---")
        print (msg_src_cont)
        print ("--------------------------")

    new_content = ""
    b_spacer = 0
    b_send_alert = False

    for _element in msg_src_cont: 
        b_spacer = b_spacer + 1
        if (b_spacer == 1):
            if (await check_status_entry(status_data,_element[0])):
                _fetched_dat = await get_status_entry(status_data,_element[0])
                _fetched_text = ""
                _fetched_text = f"<@{_fetched_dat[0]}> frissítette <t:{_fetched_dat[1]}:R> ami lejár <t:{_fetched_dat[2]}:R> "
                _now = int(datetime.datetime.now(datetime.timezone.utc).timestamp())
                _time_expires = _fetched_dat[2]
                _seconds_left = _time_expires - _now
                _fetched_text_extra = ""

                if _seconds_left < 0:
                    _fetched_text_extra = "LEJÁRT"

                if ((_seconds_left // 3600) > 30):
                    _fetched_text_extra = _fetched_text_extra + " 🟢"
                else:
                    if ((_seconds_left // 3600) > 15):
                        _fetched_text_extra = _fetched_text_extra + " 🟡🟡"
                    else:
                        _fetched_text_extra = _fetched_text_extra + " 🔴🔴🔴"
                        b_send_alert = True
                new_content = new_content + _element + " | " + _fetched_text + "**" + _fetched_text_extra + "**\n"
                
            else:
                new_content = new_content + _element + " | " + DEFAULT_TIMESTAMP_ERROR_MESSAGE + "\n"
                b_send_alert = True

        if (b_spacer == 2):
            new_content = new_content + _element +  "\n"
            b_spacer = 0

    if (b_send_alert):
        new_content = new_content + "\n" + ":warning:FRISSÍTÉSI FIGYELMEZTETÉS:warning:" + "\n" + USER_GROUPS_TO_BE_NOTIFIED_MSG_TEXT
        await send_and_delete_notification_message()

    if (ISDEBUG):
        print ("---Currently stored stockpile data---")
        for emoji, data in status_data.items():
            user_id = data["user"]
            timestamp_checked = data["timestamp_checked"]
            timestamp_expires = data["timestamp_expires"]

            print(emoji, user_id, timestamp_checked, timestamp_expires)
        print ("-------------------------------------")

    await message.edit(content=new_content)

# Used when bot initialises
async def clear_channel(channel_id):
    channel = await bot.fetch_channel(CHANNEL_ID)
    await channel.purge(limit=None)

# Handles sending notification to set users. Craetes and deletes message.
async def send_and_delete_notification_message():
    if (notif_wait_until_ready):
        print ("Notification is about to be sent, msg to be created and deleted ...")
        message = await (bot.get_channel(CHANNEL_ID)).send(
            USER_GROUPS_TO_BE_NOTIFIED_MSG_TEXT,
            allowed_mentions=discord.AllowedMentions(everyone=True, users=True, roles=True)
        )

        # delete
        await message.delete()

# This is an hourly update loop
@tasks.loop(hours=1)
async def hourly_check():
    channel = bot.get_channel(CHANNEL_ID)
    message = await channel.fetch_message(MESSAGE_ID)
    await message.clear_reactions()
    await update_status_message_new(message)

bot.run(TOKEN)
