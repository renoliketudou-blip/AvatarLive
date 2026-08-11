"""
AvatarLive HTTP API.

Endpoints:
  POST /api/avatar            multipart image upload -> hot-swap the digital
                              human's appearance (all live WebRTC sessions).
  POST /api/speak             server-initiated speech. Two payload styles:
                                JSON   {"text": "..."}          -> edge-tts synth
                                audio  raw WAV bytes (16-bit PCM) -> as-is
                              Audio is broadcast to every connected client so
                              the digital human speaks on all sessions at once.

Both endpoints drive the shared FlashHead engine directly, so no LLM/ASR API
keys are required.
"""
import asyncio
import io
import os
import tempfile
import uuid

import numpy as np
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import JSONResponse
from loguru import logger

# ---------------------------------------------------------------------------
# Audio helpers (edge-tts text -> 16k + 24k PCM; wav decode + resample)
# ---------------------------------------------------------------------------

def _resample(audio: np.ndarray, src_sr: int, dst_sr: int) -> np.ndarray:
    if src_sr == dst_sr:
        return audio
    import librosa
    return librosa.resample(audio, orig_sr=src_sr, target_sr=dst_sr).astype(np.float32)


def edge_tts_synthesize(text: str, voice: str = "zh-CN-XiaoxiaoNeural",
                        output_sr: int = 24000, input_sr: int = 16000):
    """Synthesize text to (16k, 24k) float32 mono arrays via Microsoft edge-tts."""
    import edge_tts

    fd, mp3_path = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)
    try:
        asyncio.run(edge_tts.Communicate(text, voice=voice).save(mp3_path))
        # edge-tts outputs 24 kHz MP3; decode with PyAV (robust mp3 decoder)
        import av
        container = av.open(mp3_path)
        audio_stream = next(s for s in container.streams if s.type == "audio")
        chunks = []
        for frame in container.decode(audio_stream):
            arr = frame.to_ndarray()
            # (channels, samples) -> mono float32 in [-1, 1]
            if arr.ndim == 2:
                mono = arr.mean(axis=0)
            else:
                mono = arr
            chunks.append(mono.astype(np.float32))
        container.close()
        if not chunks:
            raise RuntimeError("edge-tts returned no audio")
        audio_24k = np.concatenate(chunks)
        audio_16k = _resample(audio_24k, output_sr, input_sr)
        return audio_16k, audio_24k
    finally:
        try:
            os.remove(mp3_path)
        except OSError:
            pass


def _decode_mp3_bytes(data: bytes, output_sr: int):
    """Decode MP3 (or other av-supported container) bytes to float32 mono at output_sr."""
    import av
    container = av.open(io.BytesIO(data))
    audio_stream = next(s for s in container.streams if s.type == "audio")
    native_sr = int(audio_stream.rate or 24000)
    chunks = []
    for frame in container.decode(audio_stream):
        arr = frame.to_ndarray()
        mono = arr.mean(axis=0) if arr.ndim == 2 else arr
        chunks.append(mono.astype(np.float32))
    container.close()
    if not chunks:
        raise ValueError("no audio decoded")
    audio = np.concatenate(chunks)
    return _resample(audio, native_sr, output_sr)


def decode_audio_bytes(data: bytes, output_sr: int = 24000, input_sr: int = 16000):
    """Decode uploaded audio (WAV 16-bit PCM or MP3/other via PyAV) to
    (16k, 24k) float32 mono arrays."""
    import wave

    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        with wave.open(io.BytesIO(data), "rb") as wf:
            sr = wf.getframerate()
            channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            n = wf.getnframes()
            raw = wf.readframes(n)
            if sampwidth != 2:
                raise ValueError(f"only 16-bit PCM supported, got {sampwidth * 8}-bit")
            audio = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
            if channels > 1:
                audio = audio.reshape(-1, channels).mean(axis=1)
            audio = _resample(audio, sr, output_sr)
    else:
        # Assume an av-supported container (mp3/ogg/flac...) at any sample rate.
        audio = _decode_mp3_bytes(data, output_sr)
    audio_16k = _resample(audio, output_sr, input_sr)
    return audio_16k, audio


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------

def _get_flashhead_handler(chat_engine):
    """Locate the live HandlerAvatarFlashHead instance inside the engine."""
    try:
        registries = chat_engine.handler_manager.handler_registries
    except Exception:
        return None
    for _name, reg in registries.items():
        handler = getattr(reg, "handler", None)
        if handler is not None and handler.__class__.__name__ == "HandlerAvatarFlashHead":
            return handler
    return None


def register_api(app: FastAPI, chat_engine) -> None:
    """Register /api/avatar and /api/speak on the FastAPI app."""

    @app.post("/api/avatar")
    async def api_avatar(file: UploadFile = File(...)):
        handler = _get_flashhead_handler(chat_engine)
        if handler is None or handler.pipeline is None:
            return JSONResponse({"error": "FlashHead handler not ready yet"},
                                status_code=503)
        data = await file.read()
        if not data:
            return JSONResponse({"error": "empty file"}, status_code=400)

        # Validate it decodes as an image and save as PNG.
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(data))
            img.load()
            img = img.convert("RGB")
        except Exception as e:
            return JSONResponse({"error": f"invalid image: {e}"}, status_code=400)

        project_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        avatar_dir = os.path.join(project_dir, "resource", "avatar", "flashhead")
        os.makedirs(avatar_dir, exist_ok=True)
        save_path = os.path.join(avatar_dir, "uploaded_avatar.png")
        img.save(save_path)

        try:
            applied = handler.update_avatar_image(save_path)
        except Exception as e:
            logger.error(f"/api/avatar hot-swap failed: {e}")
            return JSONResponse({"error": f"hot-swap failed: {e}"}, status_code=500)

        return JSONResponse({
            "status": "ok",
            "avatar": applied,
            "size": list(img.size),
        })

    @app.post("/api/speak")
    async def api_speak(request: Request):
        handler = _get_flashhead_handler(chat_engine)
        if handler is None or handler.pipeline is None:
            return JSONResponse({"error": "FlashHead handler not ready yet"},
                                status_code=503)

        content_type = request.headers.get("content-type", "").lower()

        if "application/json" in content_type or "text" in content_type:
            body = await request.json()
            text = str(body.get("text", "")).strip()
            voice = str(body.get("voice", "zh-CN-XiaoxiaoNeural")).strip()
            if not text:
                return JSONResponse({"error": "missing text"}, status_code=400)
            logger.info(f"/api/speak text ({len(text)} chars, voice={voice}): {text[:60]}")
            try:
                audio_16k, audio_out = await asyncio.to_thread(
                    edge_tts_synthesize, text, voice,
                )
            except Exception as e:
                logger.error(f"/api/speak edge-tts failed: {e}")
                return JSONResponse({"error": f"edge-tts failed: {e}"}, status_code=502)
            src_desc = f"edge-tts({len(audio_16k) / 16000:.1f}s)"
        else:
            # audio bytes: accept WAV (16-bit PCM) or MP3/other (PyAV) payload
            data = await request.body()
            if not data:
                return JSONResponse({"error": "empty audio"}, status_code=400)
            try:
                audio_16k, audio_out = await asyncio.to_thread(
                    decode_audio_bytes, data,
                )
            except Exception as e:
                logger.error(f"/api/speak audio decode failed: {e}")
                return JSONResponse({"error": f"audio decode failed: {e}"}, status_code=400)
            src_desc = f"audio({len(audio_16k) / 16000:.1f}s)"

        if len(audio_16k) < 1600:  # < 100ms
            return JSONResponse({"error": "audio too short"}, status_code=400)

        speech_id = f"api-{uuid.uuid4().hex[:8]}"
        n = handler.broadcast_speak(audio_16k, audio_out, speech_id)
        return JSONResponse({
            "status": "ok",
            "speech_id": speech_id,
            "source": src_desc,
            "broadcast_to_sessions": n,
        })
