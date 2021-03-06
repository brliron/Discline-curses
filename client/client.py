import sys
import asyncio
import logging
import discord
from utils.log import log
from utils.globals import gc, kill
from utils.settings import settings
from input.input_handler import init_channel_messageEdit
from ui.ui_utils import calc_mutations
from ui.formattedText import FormattedText
from ui.ui import init_channel_formattedText

class Found(Exception):
    pass
class NoChannelsFoundException(Exception):
    pass

# inherits from discord.py's Client
class Client(discord.Client):
    def __init__(self, *args, **kwargs):
        self._current_server = None
        self._current_channel = None
        self._prompt = ""
        self._status = None
        self._game = None
        super().__init__(*args, **kwargs)

    @property
    def prompt(self):
        return self._prompt
    @prompt.setter
    def prompt(self, prompt):
        self._prompt = prompt

    @property
    def current_server(self):
        # discord.Server object
        return self._current_server

    def set_current_server(self, server):
        if isinstance(server, str):
            for srv in self.servers:
                if server.lower() in srv.name.lower():
                    self._current_server = srv
                    # find first non-ignored channel, set channel, mark flags as False 
                    def_chan = None
                    lowest = 999
                    for chan in srv.channels:
                        if chan.type is discord.ChannelType.text and \
                                chan.permissions_for(srv.me).read_messages and \
                                chan.position < lowest:
                            try:
                                # Skip over ignored channels
                                for serv_key in settings["channel_ignore_list"]:
                                    if serv_key["server_name"].lower() == srv.name:
                                        for name in serv_key["ignores"]:
                                            if chan.name.lower() == name.lower():
                                                raise Found
                            except Found:
                                continue
                            except:
                                e = sys.exc_info()[0]
                                log("Exception raised during channel ignore list parsing: {}".format(e),
                                        logging.error)
                                return
                            lowest = chan.position
                            def_chan = chan
                        else:
                            continue
                        try:
                            if def_chan is None:
                                raise NoChannelsFoundException
                            self.current_channel = def_chan
                            servlog = self.current_server_log
                            for chanlog in servlog.logs:
                                if chanlog.channel is def_chan:
                                    chanlog.unread = False
                                    chanlog.mentioned_in = False
                                    break
                        except NoChannelsFoundException:
                            log("No channels found.")
                            return
                        except:
                            e = sys.exc_info()[0]
                            log("Error when setting channel flags!: {}".format(e), logging.error)
                            continue
                    return
            return
        self._current_server = server

    @property
    def current_channel(self):
        return self._current_channel
    @current_channel.setter
    def current_channel(self, channel):
        if isinstance(channel, str):
            try:
                svr = self.current_server
                for chl in svr.channels:
                    if channel.lower() in chl.name.lower() and \
                            chl.permissions_for(svr.me).read_messages:
                        self._current_channel = chl
                        self._prompt = chl.name
                        if len(gc.channels_entered) > 0:
                            if chl.id in gc.ui.messageEdit:
                                gc.ui.edit = gc.ui.messageEdit[chl.id]
                            else:
                                init_channel_messageEdit(chl)
                            if chl.id in gc.ui.formattedText:
                                gc.ui.formattedText[chl.id].refresh(
                                        newWidth=gc.ui.chatWin.getmaxyx()[1])
                            else:
                                init_channel_formattedText(chl.id)
                            chanlog = self.current_channel_log
                            chanlog.unread = False
                            chanlog.mentioned_in = False
                            gc.ui.doUpdate = True
                        return
                raise RuntimeError("Could not find channel!")
            except RuntimeError as e:
                log("RuntimeError during channel setting: {}".format(e), logging.error)
                return
            except AttributeError:
                log("Attribute error: chanlog is None", logging.error)
                return
            except:
                e = sys.exc_info()[0]
                log("Unknown exception during channel setting: {}".format(e), logging.error)
                return
        self._current_channel = channel
        self._prompt = channel.name
        if len(gc.channels_entered) > 0:
            if channel.id in gc.ui.messageEdit:
                gc.ui.edit = gc.ui.messageEdit[channel.id]
            else:
                init_channel_messageEdit(channel)
            if channel.id in gc.ui.formattedText:
                gc.ui.formattedText[channel.id].refresh(
                        newWidth=gc.ui.chatWin.getmaxyx()[1])
            else:
                init_channel_formattedText(channel.id)
            chanlog = self.current_channel_log
            chanlog.unread = False
            chanlog.mentioned_in = False

    @property
    def current_server_log(self):
        for slog in gc.server_log_tree:
            if slog.server is self._current_server:
                return slog

    @property
    def current_channel_log(self):
        slog = self.current_server_log
        for idx, clog in enumerate(slog.logs):
            if clog.channel.type is discord.ChannelType.text and \
                    clog.channel.name.lower() == self._current_channel.name.lower() and \
                    clog.channel.permissions_for(slog.server.me).read_messages:
                return clog

    @property
    def online(self):
        online_count = 0
        if not self.current_server == None:
            for member in self.current_server.members:
                if member is None: continue # happens if a member left the server
                if member.status is not discord.Status.offline:
                    online_count +=1
            return online_count

    @property
    def game(self):
        return self._game
    
    async def set_game(self, game):
        self._game = discord.Game(name=game,type=0)
        self._status = discord.Status.online
        # Note: the 'afk' kwarg handles how the client receives messages, (rates, etc)
        # This is meant to be a "nice" feature, but for us it causes more headache
        # than its worth.
        if self._game is not None and self._game != "":
            if self._status is not None and self._status != "":
                try: await self.change_presence(game=self._game, status=self._status, afk=False)
                except: pass
            else:
                try: await self.change_presence(game=self._game, status=discord.Status.online, afk=False)
                except: pass

    @property
    def status(self):
        return self._status
    @status.setter
    async def status(self, status):
        if status == "online":
            self._status = discord.Status.online
        elif status == "offline":
            self._status = discord.Status.offline
        elif status == "idle":
            self._status = discord.Status.idle
        elif status == "dnd":
            self._status = discord.Status.dnd

        if self._game is not None and self._game != "":
            try: await self.change_presence(game=self._game, status=self._status, afk=False)
            except: pass
        else:
            try: await self.change_presence(status=self._status, afk=False)
            except: pass

    async def send_typing(self, channel):
        if channel.permissions_for(self.current_server.me).send_messages:
            await super().send_typing(channel)

    async def init_channel(self, channel=None):
        clog = None
        if channel is None:
            clog = self.current_channel_log
            log("Initializing current channel")
        else:
            log("Initializing channel {}".format(channel.name))
            try:
                for svrlog in gc.server_log_tree:
                    for chllog in svrlog.logs:
                        if chllog.channel == channel:
                            clog = chllog
                            raise Found
            except Found:
                pass
        if clog.channel.type is discord.ChannelType.text and \
                clog.channel.permissions_for(clog.server.me).read_messages:
            async for msg in self.logs_from(clog.channel,
                    limit=settings["max_log_entries"]):
                if msg.edited_timestamp is not None:
                    msg.content += " **(edited)**"
                # needed for modification of past messages
                self.messages.append(msg)
                clog.insert(0, calc_mutations(msg))
            gc.channels_entered.append(clog.channel)
            gc.ui.formattedText[clog.channel.id] = \
                    FormattedText(gc.ui.chatWin.getmaxyx()[1], \
                    settings["max_messages"], gc.ui.colors)
            for msg in clog.logs:
                gc.ui.formattedText[clog.channel.id].addMessage(msg)
