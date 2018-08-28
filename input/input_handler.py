import asyncio
import curses
import logging
import re
import time
import discord
import ui.ui as ui
from utils.log import log
from utils.globals import gc, kill
from utils.settings import settings
from commands.text_emoticons import check_emoticons
from commands.sendfile import send_file
from commands.channel_jump import channel_jump
from input.messageEdit import MessageEdit

def key_input():
    # if the next two aren't here, input does not work
    curses.cbreak()
    curses.noecho()
    editWin = gc.ui.editWin
    call = (ui.draw_edit_win, True)
    gc.ui_thread.funcs.append(call)
    while not gc.doExit:
        prompt = gc.client.prompt
        ch = editWin.get_wch()
        if not gc.ui.displayPanel.hidden():
            time.sleep(0.01)
            continue

        if ch != '\n' and len(gc.ui.messageEdit.inputBuffer) > 0 and \
                gc.ui.messageEdit.inputBuffer[0] != '/':
            gc.typingBeingHandled = True
        # prevents crashes when enter is hit and input buf is empty
        if ch == '\n' and not gc.ui.messageEdit.inputBuffer:
            continue
        if ch == curses.KEY_PPAGE:
            gc.ui.channel_log_offset -= settings["scroll_lines"]
            ui.draw_screen()
            continue
        elif ch == curses.KEY_NPAGE:
            gc.ui.channel_log_offset += settings["scroll_lines"]
            ui.draw_screen()
            continue
        elif ch == curses.KEY_RESIZE:
            gc.ui.resize()
            ui.draw_screen()
            continue
        # if ESC is pressed, clear messageEdit buffer
        elif ch == chr(27):
            gc.ui.messageEdit.reset()
            call = (ui.draw_edit_win, True)
            gc.ui_thread.funcs.append(call)
            continue
        ret = gc.ui.messageEdit.addKey(ch)
        if ret is not None:
            input_handler(ret)
            gc.ui.messageEdit.reset()
        call = (ui.draw_edit_win, True)
        gc.ui_thread.funcs.append(call)
    log("key_input finished")
    gc.tasksExited += 1

def typing_handler():
    if not settings["send_is_typing"]: return

    log("typing_handler started")
    while not gc.doExit:
        if gc.typingBeingHandled:
            call = (gc.client.current_channel.trigger_typing,)
            gc.client.async_funcs.append(call)
            while not gc.doExit and (call in gc.client.async_funcs or \
                    call[0].__name__ in gc.client.locks):
                time.sleep(0.1)
            for second in range(50):
                if gc.doExit:
                    break
                time.sleep(0.1)
            gc.typingBeingHandled = False
            if gc.doExit:
                break
        time.sleep(0.1)
    log("typing_handler finished")
    gc.tasksExited += 1

def input_handler(text):
    # Must be a command
    if text.startswith(settings["prefix"]):
        text = text[1:]
        arg = None
        if ' ' in text:
            command,arg = text.split(" ", 1)
        elif not text:
            return
        else:
            command = text
            arg = None
        parseCommand(command, arg)
    # Must be text
    else:
        # Emoji
        if text.count(':')%2 == 0:
            text = parseEmoji(text)
        if '@' in text:
            sects = []
            for sect in text.lower().strip().split('@'):
                sects.append(sect.split(' '))
            mentions = []
            for sect in sects:
                if not sect:
                    continue
                for member in gc.client.current_guild.members:
                    for i in reversed(range(len(sect))):
                        segment = sect[:i+1]
                        if not segment[0]:
                            continue
                        if " ".join(segment).lower() in member.display_name.lower():
                            m = re.search('@'+" ".join(segment), text)
                            if m is None:
                                continue
                            text = text[:m.start()] + '{}' + text[m.end():]
                            mention = "<@!" + member.id + ">"
                            mentions.append(mention)
                            break
            text = text.format(*mentions)
        for i in range(0,3):
            try:
                call = (gc.client.current_channel.send, text)
                gc.client.async_funcs.append(call)
                while call in gc.client.async_funcs and \
                        call[0].__name__ in gc.client.locks:
                    time.sleep(0.1)
                break
            except:
                time.sleep(3)

def parseCommand(command, arg=None):
    if arg is None:
        if command in ("refresh", "update"):
            ui.draw_screen()
            log("Manual update done", logging.info)
        elif command in ("quit", "exit"):
            try: gc.exit_thread.start()
            except SystemExit: pass
            while not gc.doExit:
                time.sleep(0.01)
        elif command in ("help", 'h'): ui.draw_help()
        elif command in ("guilds", "glds", "servers", "servs"): ui.draw_guildlist()
        elif command in ("channels", "chans"): ui.draw_channellist()
        elif command == "emojis": ui.draw_emojilist()
        elif command in ("users", "members"): ui.draw_userlist()
        elif command[0] == 'c':
            try:
                if command[1].isdigit():
                    channel_jump(command)
                    ui.draw_screen()
            except IndexError:
                pass
        return

    if command in ('guild', 'gld', 'server', 's'):
        prev_guild = gc.client.current_guild
        gc.client.set_current_guild(arg)
        if gc.client.current_guild is prev_guild:
            return
        log("changed guild")
        gc.ui.channel_log_offset = -1
        ui.draw_screen()
    elif command in ("channel", 'c'):
        gc.client.current_channel = arg
        gc.ui.channel_log_offset = -1
        ui.draw_screen()
    elif command == "nick":
        try:
            call = (gc.client.current_guild.me.edit, {'nick':arg})
            gc.client.async_funcs.append(call)
            while call in gc.client.async_funcs or \
                    call[0].__name__ in gc.client.locks:
                time.sleep(0.1)
        except:
            pass
        return
    elif command in ("game", "activity"):
        call = (gc.client.set_activity, arg)
        gc.client.async_funcs.append(call)
        while call in gc.client.async_funcs or \
                call[0].__name__ in gc.client.locks:
            time.sleep(0.1)
    elif command == "file":
        send_file(arg)
    elif command == "status":
        status = arg.lower()
        if status in ("away", "afk"):
            status = "idle"
        elif "disturb" in status:
            status = "dnd"

        if status in ("online", "offline", "idle", "dnd"):
            call = (gc.client.set_status, status)
            gc.client.async_funcs.append(call)
            while call in gc.client.async_funcs or \
                    call[0].__name__ in gc.client.locks:
                time.sleep(0.1)

def parseEmoji(text):
    if gc.client.user.premium:
        for emoji in gc.client.emojis:
            short_name = ':' + emoji.name + ':'
            if short_name in text:
                full_name = "<:{}:{}>".format(emoji.name, emoji.id)
                text = text.replace(short_name, full_name)
    elif gc.client.current_guild.emojis is not None and \
            len(gc.client.current_guild.emojis) > 0:
        for emoji in gc.client.current_guild.emojis:
            short_name = ':' + emoji.name + ':'
            if short_name in text:
                full_name = "<:{}:{}>".format(emoji.name, emoji.id)
                text = text.replace(short_name, full_name)

    return text
