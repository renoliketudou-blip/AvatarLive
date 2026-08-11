#!/usr/bin/env python3
"""AvatarLive self-test: connect to the WebRTC service, send fake audio+video
tracks, and verify the digital human's video frames arrive at the client.

Usage:
  python scripts/test_webrtc_client.py
Env:
  RTC_HOST      offer endpoint (default https://localhost:8282/webrtc/offer)
  RTC_TURN_URL  optional TURN server for cross-network tests, e.g.
                turn:IP:3478?transport=tcp (with RTC_TURN_USER/PASS)
"""
import asyncio, json, ssl, urllib.request, fractions, os
import numpy as np
from aiortc import (
    RTCPeerConnection, RTCSessionDescription, RTCIceServer, RTCConfiguration,
    MediaStreamTrack,
)
from aiortc.mediastreams import AudioFrame, VideoFrame

HOST = os.environ.get("RTC_HOST", "https://localhost:8282/webrtc/offer")
video_frames = 0


class MicTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self._pts = 0

    async def recv(self):
        self._pts += 320
        pcm = bytes((i * 7) % 256 for i in range(640))
        frame = AudioFrame(format="s16", layout="mono", samples=320)
        frame.planes[0].update(pcm)
        frame.sample_rate = 16000
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, 16000)
        await asyncio.sleep(0.02)
        return frame


class CamTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self):
        super().__init__()
        self._pts = 0

    async def recv(self):
        self._pts += 1
        img = np.full((240, 320, 3), (self._pts * 20) % 255, dtype=np.uint8)
        frame = VideoFrame.from_ndarray(img, format="rgb24")
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, 30)
        await asyncio.sleep(1 / 30)
        return frame


async def test():
    ice_servers = [RTCIceServer(urls="stun:stun.l.google.com:19302")]
    turn_url = os.environ.get("RTC_TURN_URL", "")
    if turn_url:
        ice_servers.append(RTCIceServer(
            urls=turn_url,
            username=os.environ.get("RTC_TURN_USER", "username"),
            credential=os.environ.get("RTC_TURN_PASS", "password"),
        ))
    ice = RTCConfiguration(iceServers=ice_servers)
    pc = RTCPeerConnection(configuration=ice)
    pc.addTrack(MicTrack())
    pc.addTrack(CamTrack())
    pc.createDataChannel("chat")

    @pc.on("track")
    def on_track(track):
        print("TRACK:", track.kind)

        async def reader():
            global video_frames
            n = 0
            try:
                while True:
                    frame = await track.recv()
                    n += 1
                    if track.kind == "video" and n <= 3:
                        print(f"  VIDEO frame {n}: {getattr(frame, 'width', '?')}x{getattr(frame, 'height', '?')}")
                    if track.kind == "video":
                        video_frames = n
            except Exception as e:
                print(f"  {track.kind} reader end after {n}: {type(e).__name__}")

        asyncio.ensure_future(reader())

    @pc.on("connectionstatechange")
    def on_csc():
        print("CONNECTION STATE:", pc.connectionState)

    @pc.on("iceconnectionstatechange")
    def on_icsc():
        print("ICE STATE:", pc.iceConnectionState)

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    data = json.dumps({"type": offer.type, "sdp": offer.sdp, "webrtc_id": "av-test"}).encode()
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(HOST, data=data, headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, context=ctx, timeout=30)
    body = json.loads(resp.read().decode())
    print("ANSWER:", body.get("type"))
    await pc.setRemoteDescription(RTCSessionDescription(sdp=body["sdp"], type=body["type"]))

    for i in range(30):
        await asyncio.sleep(1)
        if pc.iceConnectionState in ("connected", "completed"):
            print("CONNECTED after", i + 1, "s")
            break

    for i in range(30):
        await asyncio.sleep(1)
        if video_frames > 0:
            print(f"[t={i+1}s] VIDEO RECEIVED, frames so far: {video_frames}")
            break
    print("FINAL conn:", pc.connectionState, "| video_frames:", video_frames)
    await pc.close()


asyncio.run(test())
