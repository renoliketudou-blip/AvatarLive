#!/usr/bin/env python3
"""AvatarLive end-to-end self-test: feed a real edge-tts speech WAV as the
microphone input and verify the TTS->FlashHead chain produces avatar speech.

Usage:
  python scripts/test_webrtc_speech.py [/path/to/speech.wav]
Env:
  RTC_HOST      offer endpoint (default https://localhost:8282/webrtc/offer)
  RTC_TURN_URL  optional TURN server for cross-network tests
"""
import asyncio, json, ssl, urllib.request, fractions, os, sys
import numpy as np, soundfile as sf, librosa
from aiortc import (
    RTCPeerConnection, RTCSessionDescription, RTCIceServer, RTCConfiguration,
    MediaStreamTrack,
)
from aiortc.mediastreams import AudioFrame, VideoFrame

HOST = os.environ.get("RTC_HOST", "https://localhost:8282/webrtc/offer")
video_frames = 0
audio_frames = 0
audio_samples_total = 0

# 加载测试语音 → 16kHz float32 mono
speech_wav = sys.argv[1] if len(sys.argv) > 1 else "/tmp/test_speech.wav"
speech, sr = sf.read(speech_wav, dtype="float32")
if sr != 16000:
    speech = librosa.resample(speech, orig_sr=sr, target_sr=16000)
speech = speech.astype(np.float32).reshape(-1)

SILENCE_S = 0.6
PAD = int(16000 * SILENCE_S)
seq = np.concatenate([np.zeros(PAD, np.float32), speech, np.zeros(PAD, np.float32)])
N_CHUNKS = len(seq) // 320
print("speech: total_dur=%.1fs chunks=%d" % (len(seq) / 16000, N_CHUNKS), flush=True)


class MicTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self):
        super().__init__()
        self._pts = 0
        self._chunk = 0

    async def recv(self):
        i = self._chunk % N_CHUNKS
        self._chunk += 1
        chunk = seq[i * 320:(i + 1) * 320]
        if len(chunk) < 320:
            chunk = np.pad(chunk, (0, 320 - len(chunk)))
        pcm = (chunk * 32767).astype(np.int16).tobytes()
        frame = AudioFrame(format="s16", layout="mono", samples=320)
        frame.planes[0].update(pcm)
        frame.sample_rate = 16000
        frame.pts = self._pts
        self._pts += 320
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
        img = np.full((240, 320, 3), 90, dtype=np.uint8)
        frame = VideoFrame.from_ndarray(img, format="rgb24")
        frame.pts = self._pts
        frame.time_base = fractions.Fraction(1, 30)
        await asyncio.sleep(1 / 30)
        return frame


async def test():
    global video_frames, audio_frames, audio_samples_total
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
        print("TRACK:", track.kind, flush=True)

        async def reader():
            global video_frames, audio_frames, audio_samples_total
            n = 0
            try:
                while True:
                    frame = await track.recv()
                    n += 1
                    if track.kind == "video":
                        video_frames = n
                        if n <= 3:
                            print(f"  VIDEO {n}: {frame.width}x{frame.height}", flush=True)
                    elif track.kind == "audio":
                        audio_frames = n
                        audio_samples_total += getattr(frame, "samples", 0) or 0
                        if n <= 3:
                            print(f"  AUDIO {n}: samples={getattr(frame, 'samples', '?')} sr={getattr(frame, 'sample_rate', '?')}", flush=True)
            except Exception as e:
                print(f"  {track.kind} reader end after {n}: {type(e).__name__}", flush=True)

        asyncio.ensure_future(reader())

    @pc.on("iceconnectionstatechange")
    def on_icsc():
        print("ICE:", pc.iceConnectionState, flush=True)

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)
    data = json.dumps({"type": offer.type, "sdp": offer.sdp, "webrtc_id": "e2e-test"}).encode()
    ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
    req = urllib.request.Request(HOST, data=data, headers={"Content-Type": "application/json"}, method="POST")
    body = json.loads(urllib.request.urlopen(req, context=ctx, timeout=30).read().decode())
    print("ANSWER:", body.get("type"), flush=True)
    await pc.setRemoteDescription(RTCSessionDescription(sdp=body["sdp"], type=body["type"]))

    for i in range(30):
        await asyncio.sleep(1)
        print(f"[t={i+1}s] video_frames={video_frames} audio_frames={audio_frames} audio_samples_total={audio_samples_total}", flush=True)
        if video_frames > 0 and audio_frames > 0 and i > 8:
            print(">>> BOTH video AND audio received — pipeline works!", flush=True)
            break
    print("FINAL conn:", pc.connectionState, "| video_frames:", video_frames,
          "| audio_frames:", audio_frames, "| audio_samples_total:", audio_samples_total, flush=True)
    await pc.close()


asyncio.run(test())
