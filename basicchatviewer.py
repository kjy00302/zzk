import zzk
import asyncio
import sys
import string
import base64
import re


class BasicChatViewer(zzk.Zzk):
    """
    Example of using Zzk library to implement basic chat viewer
    """

    EMOTE_REGEX = re.compile(r'{:(\w+):}')

    def __init__(self, use_iterm_emote):
        self._emote_cache = {}
        self._use_iterm_emote = use_iterm_emote

    @classmethod
    def _img_to_iterm2(cls, imgdata):
        size = len(imgdata)
        data = base64.b64encode(imgdata).decode()
        return f"\x1b]1337;File=inline=1;height=1;width=2;size={size}:{data}\a"

    @classmethod
    def _profile_to_displayname(cls, profile: zzk.ZzkProfile):
        if profile:
            return f"{profile.nickname}({profile.hash[:6]})"
        else:
            return "Anonymous"

    async def _fetch_emote(self, sess, url):
        async with sess.get(url) as resp:
            return BasicChatViewer._img_to_iterm2(await resp.read())

    async def on_chat(self, sess, ws, msg: zzk.ZzkMessage):
        user = BasicChatViewer._profile_to_displayname(msg.profile)
        message = msg.message.strip()
        if self._use_iterm_emote:
            if emotes := msg.extras.get('emotes'):
                for k, v in emotes.items():
                    if not self._emote_cache.get(k):
                        self._emote_cache[k] = await self._fetch_emote(sess, v)
            message = BasicChatViewer.EMOTE_REGEX.sub(
                lambda x: self._emote_cache.get(x.group(1)),
                msg.message
            )
        print(f"{user}: {message}")

    async def on_donation(self, sess, ws, msg: zzk.ZzkMessage):
        user = BasicChatViewer._profile_to_displayname(msg.profile)
        icon = "🎬" if msg.extras['donationType'] == "VIDEO" else "🧀"
        message = msg.message.strip()
        amount = msg.extras['payAmount']
        print(f"[{amount}{icon}] {user}: {message}")

    async def on_subscribe(self, sess, ws, msg: zzk.ZzkMessage):
        user = BasicChatViewer._profile_to_displayname(msg.profile)
        message = msg.message.strip() if msg.message else "<No message>"
        month = msg.extras['month']
        tiername = msg.extras['tierName']
        print(f"[🗓️{month}M {tiername}] {user}: {message}")


if __name__ == '__main__':
    USE_ITERM_EMOTE = True

    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <channel_id>")
        quit()
    if len(sys.argv[1]) != 32 or set(sys.argv[1]) - set(string.hexdigits):
        print("invalid channel id")
        quit()
    client = BasicChatViewer(USE_ITERM_EMOTE)
    asyncio.run(client.run(sys.argv[1]))
