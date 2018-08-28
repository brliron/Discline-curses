#!/usr/bin/env python3.7
# ------------------------------------------------------- #
#                                                         #
# Discline-curses                                         #
#                                                         #
# http://github.com/NatTupper/Discline-curses             #
#                                                         #
# Licensed under GNU GPLv3                                #
#                                                         #
# ------------------------------------------------------- #

import sys
import asyncio
import curses
import os
import threading
from discord import TextChannel, MessageType
from input.input_handler import key_input, typing_handler
from ui.ui import draw_screen, draw_help
from utils.globals import *
from utils.settings import copy_skeleton, settings
from utils.updates import check_for_updates
from utils.threads import WorkerThread
from utils.token_utils import get_token, store_token
from utils.log import log, startLogging, msglog
from client.guildlog import PrivateGuild, GuildLog
from client.channellog import PrivateChannel, ChannelLog
from client.on_message import on_incoming_message
from client.client import Client

init_complete = False

# Set terminal X11 window title
print('\33]0;Discline\a', end='', flush=True)
# Set the timeout for the ESC key to 25ms
os.environ.setdefault('ESCDELAY', '25')

gc.initClient()

@gc.client.event
async def on_ready():
    # these values are set in settings.yaml
    if settings["default_prompt"] is not None:
        gc.client.prompt = settings["default_prompt"].lower()
    else:
        gc.client.prompt = '~'

    if settings["default_activity"] is not None:
        await gc.client.set_activity(settings["default_activity"])

    privateGuild = PrivateGuild()
    channels = []
    channel_logs = []
    for idx,channel in enumerate(gc.client.private_channels):
        chl = PrivateChannel(channel, privateGuild, idx)
        channels.append(chl)
        channel_logs.append(ChannelLog(chl, []))
    privateGuild.set_channels(channels)
    gc.guild_log_tree.append(GuildLog(privateGuild, channel_logs))

    for guild in gc.client.guilds:
        # Null check to check guild availability
        if guild is None:
            continue
        serv_logs = []
        for channel in guild.channels:
            # Null checks to test for bugged out channels
            #if channel is None or channel.type is None:
            #    continue
            # Null checks for bugged out members
            if guild.me is None or guild.me.id is None \
                    or channel.permissions_for(guild.me) is None:
                continue
            if isinstance(channel, TextChannel):
                    if channel.permissions_for(guild.me).read_messages:
                        try: # try/except in order to 'continue' out of multiple for loops
                            for serv_key in settings["channel_ignore_list"]:
                                if serv_key["guild_name"].lower() == guild.name.lower():
                                    for name in serv_key["ignores"]:
                                        if channel.name.lower() == name.lower():
                                            raise Found
                            serv_logs.append(ChannelLog(channel, []))
                        except:
                            continue

        # add the channellog to the tree
        gc.guild_log_tree.append(GuildLog(guild, serv_logs))

    if settings["default_guild"] is not None:
        gc.client.set_current_guild(settings["default_guild"])
        if gc.client.current_guild is None:
            print("ERROR: default_guild not found!")
            raise KeyboardInterrupt
            return
        if settings["default_channel"] is not None:
            gc.client.current_channel = settings["default_channel"].lower()
            gc.client.prompt = settings["default_channel"].lower()

    # start our own coroutines
    gc.client.loop.create_task(gc.client.run_calls())
    gc.ui_thread.start()
    while not gc.ui.isInitialized:
        await asyncio.sleep(0.1)

    await gc.client.init_channel()
    draw_screen()

    gc.key_input_thread = WorkerThread(gc, key_input)
    gc.typing_handler_thread = WorkerThread(gc, typing_handler)
    gc.exit_thread = WorkerThread(gc, kill)

    gc.key_input_thread.start()
    gc.typing_handler_thread.start()

    global init_complete
    init_complete = True

# called whenever the client receives a message (from anywhere)
@gc.client.event
async def on_message(message):
    await gc.client.wait_until_ready()
    if init_complete:
        msglog(message)
        await on_incoming_message(message)

@gc.client.event
async def on_message_edit(msg_old, msg_new):
    await gc.client.wait_until_ready()
    if msg_old.clean_content == msg_new.clean_content:
        return
    clog = gc.client.current_channel
    if clog is None:
        return
    ft = gc.ui.views[str(clog.id)].formattedText
    msg_new.content = msg_new.content + " **(edited)**"
    idx = 0
    while True:
        if len(ft.messages) >= idx:
            break
        if ft.messages[idx].id == msg_old.id:
            ft.messages[idx].content = msg_new.content
            break
        idx += 1
    ft.refresh()

    if init_complete and msg_old.channel is gc.client.current_channel:
        draw_screen()

@gc.client.event
async def on_message_delete(msg):
    log("Attempting to delete")
    await gc.client.wait_until_ready()
    # TODO: PM's have 'None' as a guild -- fix this later
    if msg.guild is None: return

    try:
        for guildlog in gc.guild_log_tree:
            if guildlog.guild == msg.guild:
                for channellog in guildlog.logs:
                    if channellog.channel == msg.channel:
                        ft = gc.ui.views[str(channellog.channel.id)].formattedText
                        channellog.logs.remove(msg)
                        ft.messages.remove(msg)
                        ft.refresh()
                        log("Deleted, updating")
                        if msg.channel is gc.client.current_channel:
                            draw_screen()
                        return
    except:
        # if the message cannot be found, an exception will be raised
        # this could be #1: if the message was already deleted,
        # (happens when multiple calls get excecuted within the same time)
        # or the user was banned, (in which case all their msgs disappear)
        pass
    log("Could not delete message: {}".format(msg.clean_content))

async def runSimpleHelp():
    curses.wrapper(gc.ui.run)
    draw_help(terminateAfter=True)

def terminate_curses():
    curses.nocbreak()
    gc.ui.screen.keypad(False)
    curses.echo()
    curses.endwin()

def main():
    # start the client coroutine
    if settings and settings["debug"]:
        startLogging()
    token = None
    try:
        if sys.argv[1] == "--help" or sys.argv[1] == "-h":
            try:
                asyncio.get_event_loop().run_until_complete(runSimpleHelp())
            except SystemExit:
                pass
            terminate_curses()
            quit()
        elif sys.argv[1] == "--token" or sys.argv[1] == "--store-token":
            store_token()
            quit()
        elif len(sys.argv) == 3 and sys.argv[1] == "--token-path":
            try:
                with open(sys.argv[2]) as f:
                    token = f.read()
            except:
                print("Error: Cannot read token from path")
                quit()
        elif sys.argv[1] == "--skeleton" or sys.argv[1] == "--copy-skeleton":
            # -- now handled in utils.settings.py --- #
            pass
        elif sys.argv[1] == "--config":
            # -- now handled in utils.settings.py --- #
            pass
        else:
            print(gc.term.red("Error: Unknown command."))
            print(gc.term.yellow("See --help for options."))
            quit()
    except IndexError:
        pass

    check_for_updates()
    if token is None:
        token = get_token()

    print(gc.term.yellow("Starting..."))

    # start the client
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(gc.client.run(token, bot=False))
    except:
        loop.close()

    if gc.ui.isInitialized:
        terminate_curses()

if __name__ == "__main__": main()
