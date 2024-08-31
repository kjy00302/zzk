from dataclasses import dataclass
import asyncio
import aiohttp
import random
import json


CHAT_SERVERS = [
    "kr-ss1.chat.naver.com",
    "kr-ss2.chat.naver.com",
    "kr-ss3.chat.naver.com",
    "kr-ss4.chat.naver.com",
    "kr-ss5.chat.naver.com",
    "kr-ss6.chat.naver.com",
    "kr-ss7.chat.naver.com",
    "kr-ss8.chat.naver.com",
    "kr-ss9.chat.naver.com",
    "kr-ss10.chat.naver.com"
]


@dataclass
class ZzkProfile:
    hash: str
    nickname: str
    profile_img_url: str
    role: str
    badge: dict
    title: dict
    verified: bool
    activity_badges: list
    streaming_property: dict

    @classmethod
    def from_json(cls, data):
        return cls(
            hash=data['userIdHash'],
            nickname=data['nickname'],
            profile_img_url=data['profileImageUrl'],
            role=data['userRoleCode'],
            badge=data['badge'],
            title=data['title'],
            verified=data['verifiedMark'],
            activity_badges=data['activityBadges'],
            streaming_property=data['streamingProperty']
        )


@dataclass
class ZzkMessage:
    user_id: str
    message: str
    time: int
    extras: dict
    profile: ZzkProfile


@dataclass
class ZzkBlind:
    user_id: str
    time: int
    type: str


@dataclass
class ZzkRaw:
    command: int
    service_id: str
    channel_id: str
    body: dict
    transaction_id: int
    version: str

    @classmethod
    def from_json(cls, data):
        return cls(
            command=data['cmd'],
            service_id=data['sid'],
            channel_id=data['cid'],
            body=data['bdy'],
            transaction_id=data['tid'],
            version=data['ver']
        )


class Zzk:
    """
    Zzk (지직)

    Experimental aiohttp based chat client library for Chzzk
    """

    async def _get_channel_id(self, sess, channel_id):
        resp = await sess.get(
            f'https://api.chzzk.naver.com/polling/v2/channels/{channel_id}/live-status')
        body = await resp.json()
        return body['content']['chatChannelId']

    async def _get_token(self, sess, chat_channel_id):
        resp = await sess.get(
            'https://comm-api.game.naver.com/nng_main/v1/chats/access-token',
            params={'channelId': chat_channel_id, 'chatType': 'STREAMING'})
        body = await resp.json()
        return body['content']['accessToken']

    async def run(self, channel_id, enable_raw_message=False):
        """
        Start client
        This should not return!
        """
        chat_server = 'wss://' + random.choice(CHAT_SERVERS) + '/chat'
        async with aiohttp.ClientSession() as session:
            cid = await self._get_channel_id(session, channel_id)
            assert cid is not None, "Cannot get chatroom id. Is it age-restricted?"
            accTkn = await self._get_token(session, cid)
            async with session.ws_connect(chat_server) as ws:
                await ws.send_json({
                    'ver': '2',
                    'cmd': 100,
                    'svcid': 'game',
                    'cid': cid,  # get from live-status
                    'bdy': {
                        'uid': None,
                        'devType': 2001,
                        'accTkn': accTkn,  # get from chats/access-token
                        'auth': 'READ'
                        },
                    'tid': 1
                })
                login = await ws.receive_json()
                await ws.send_json({
                    "ver": "2",
                    "cmd": 5101,
                    "svcid": "game",
                    "cid": cid,
                    "sid": login['bdy']['sid'],  # get from login
                    "bdy": {
                        "recentMessageCount": 0  # 50
                        },
                    "tid": 2
                })

                async def keepalive():
                    # original implementation sends 20s after last message sent
                    while True:
                        await asyncio.sleep(40)
                        await ws.send_json({'ver': '2', 'cmd': 0})
                keepalive_task = asyncio.create_task(keepalive())
                async for msg in ws:
                    data = msg.json()
                    if enable_raw_message:
                        await self.on_raw_message(session, ws, ZzkRaw.from_json(data))
                    match data['cmd']:
                        case 0:  # keepalive response
                            await ws.send_json({'ver': '2', 'cmd': 10000})
                            print("ping")
                        case 10000:  # keepalive response
                            pass
                        case 15101:  # previous chats
                            pass
                        # case 93006:  # system
                        #     pass
                        case 93101:  # chat
                            for msg in data['bdy']:
                                profile = msg.get('profile')
                                extras = msg.get('extras')
                                await self.on_chat(session, ws, ZzkMessage(
                                    user_id=msg['uid'],
                                    message=msg['msg'],
                                    time=msg['msgTime'],
                                    profile=ZzkProfile.from_json(json.loads(profile)) if profile else None,
                                    extras=json.loads(extras) if extras else None
                                    ))
                        case 93102:  # rich chat
                            for msg in data['bdy']:
                                profile = msg.get('profile')
                                extras = msg.get('extras')
                                match msg['msgTypeCode']:
                                    case 10:
                                        await self.on_donation(session, ws, ZzkMessage(
                                            user_id=msg['uid'],
                                            message=msg['msg'],
                                            time=msg['msgTime'],
                                            profile=ZzkProfile.from_json(json.loads(profile)) if profile else None,
                                            extras=json.loads(extras) if extras else None
                                        ))
                                    case 11:
                                        await self.on_subscribe(session, ws, ZzkMessage(
                                            user_id=msg['uid'],
                                            message=msg['msg'],
                                            time=msg['msgTime'],
                                            profile=ZzkProfile.from_json(json.loads(profile)) if profile else None,
                                            extras=json.loads(extras) if extras else None
                                        ))
                                    case 30:
                                        await self.on_system_message(session, ws, ZzkMessage(
                                            user_id=msg['uid'],
                                            message=msg['msg'],
                                            time=msg['msgTime'],
                                            profile=None,
                                            extras=json.loads(extras) if extras else None
                                        ))
                                    case _:
                                        await self.on_unknown_message(session, ws, ZzkRaw(
                                            command=data['cmd'],
                                            service_id=data['svcid'],
                                            channel_id=data['cid'],
                                            body=data['bdy'],
                                            transaction_id=data['tid'],
                                            version=data['ver']
                                        ))
                        case 94008:
                            await self.on_blind(session, ws, ZzkBlind(
                                user_id=data['bdy']['userId'],
                                time=data['bdy']['messageTime'],
                                type=data['bdy']['blindType']
                            ))
                        case _:
                            await self.on_unknown_message(session, ws, ZzkRaw(
                                command=data['cmd'],
                                service_id=data['svcid'],
                                channel_id=data['cid'],
                                body=data['bdy'],
                                transaction_id=data['tid'],
                                version=data['ver']
                            ))
                keepalive_task.cancel()
                print("!!!!!!event loop broked!!!!!!")

    async def on_raw_message(self, sess: aiohttp.ClientSession, ws: aiohttp.ClientWebSocketResponse, raw: ZzkRaw):
        """
        Called when any message received

        Requires enable_raw_message=True
        Not recommended for normal usage
        """
        pass

    async def on_chat(self, sess: aiohttp.ClientSession, ws: aiohttp.ClientWebSocketResponse, msg: ZzkMessage):
        """
        Called when normal chat message received
        """
        pass

    async def on_donation(self, sess: aiohttp.ClientSession, ws: aiohttp.ClientWebSocketResponse, msg: ZzkMessage):
        """
        Called when donation message received
        """
        pass

    async def on_subscribe(self, sess: aiohttp.ClientSession, ws: aiohttp.ClientWebSocketResponse, msg: ZzkMessage):
        """
        Called when subscribe message received
        """
        pass

    async def on_blind(self, sess: aiohttp.ClientSession, ws: aiohttp.ClientWebSocketResponse, blind: ZzkBlind):
        """
        Called when chat blinding received (automated or manual moderation)
        """
        pass

    async def on_system_message(self, sess: aiohttp.ClientSession, ws: aiohttp.ClientWebSocketResponse, msg: ZzkMessage):
        """
        Called when system message received
        """
        pass

    async def on_unknown_message(self, sess: aiohttp.ClientSession, ws: aiohttp.ClientWebSocketResponse, raw: ZzkRaw):
        """
        Called when unknown message received

        Not recommended for normal usage
        """
        pass
