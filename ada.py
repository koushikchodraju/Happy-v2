"""
ada.py — HAPPY V2 AudioLoop
Persistent Gemini Live WebSocket session using google-genai SDK 1.64+
  - Native PCM audio I/O via sounddevice (16kHz in / 24kHz out)
  - RMS-based Voice Activity Detection
  - Software echo cancellation (600 ms tail suppression)
  - Immediate interrupt handling
  - Bounded playback queue (maxsize=50, drop-oldest) [Improvement #1]
  - Per-task exception shielding via _shielded() [Improvement #2]
  - Graceful shutdown — hardware + session [Improvement #3]
  - Mic backpressure — drop chunk if queue full [Improvement #4]
  - Explicit state flags [Improvement #5]
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable, Coroutine

import cv2
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
from google import genai
from google.genai import types

from project_manager import ProjectManager
from tools import TOOL_DECLARATIONS, dispatch

load_dotenv()

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Audio constants
# ---------------------------------------------------------------------------
SEND_SAMPLE_RATE = 16_000        # Hz — mic → Gemini
RECV_SAMPLE_RATE = 24_000        # Hz — Gemini → speaker
CHUNK_FRAMES     = 1_024         # frames per read/write
CHANNELS         = 1
DTYPE            = "int16"

# VAD
VAD_RMS_THRESHOLD  = 200         # 16-bit amplitude units (low to capture all speech)
VAD_SILENCE_SECS   = 0.5

# Echo cancellation
ECHO_TAIL_SECS = 0.6             # mic suppression after playback stops

# Gemini
MODEL       = "gemini-2.5-flash-native-audio-preview-12-2025"
API_VERSION = "v1alpha"
VOICE_NAME  = "Kore"

# Queue bounds
PLAYBACK_MAXSIZE    = 50
MIC_SEND_MAXSIZE    = 20

# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------
_PROMPT_PATH = Path(__file__).parent / "HAPPY_Academic_Master_Prompt.txt"


def _load_system_prompt() -> str:
    if _PROMPT_PATH.exists():
        return _PROMPT_PATH.read_text(encoding="utf-8")
    return "You are HAPPY — a real-time multimodal AI assistant. Respond concisely."


# ---------------------------------------------------------------------------
# AudioLoop
# ---------------------------------------------------------------------------

class AudioLoop:
    """
    Full HAPPY V2 session manager.

    State flags (Improvement #5):
        _ada_playing    True while Gemini audio plays through speakers
        _user_speaking  True while VAD detects live user speech
        _connected      True while the Gemini Live WebSocket is open
    """

    def __init__(
        self,
        project_name: str = "default",
        ui_broadcast: Callable[[dict], Coroutine[Any, Any, None]] | None = None,
    ) -> None:
        self.project      = ProjectManager(project_name)
        self.ui_broadcast = ui_broadcast

        # Improvement #5 — explicit state flags
        self._ada_playing:   bool = False
        self._user_speaking: bool = False
        self._connected:     bool = False

        # Improvement #1 — bounded queues
        self.playback_queue:    asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=PLAYBACK_MAXSIZE)
        self._mic_send_queue:   asyncio.Queue[bytes | None] = asyncio.Queue(maxsize=MIC_SEND_MAXSIZE)

        # Hardware
        self._mic_stream:     sd.InputStream | None  = None
        self._camera:         cv2.VideoCapture | None = None

        # Gemini session
        self._session: Any = None
        self._tasks:   list[asyncio.Task] = []

        # Timing
        self._last_speech_time:   float = 0.0
        self._echo_suppress_until: float = 0.0

    # ------------------------------------------------------------------
    # Public lifecycle
    # ------------------------------------------------------------------

    async def run(self) -> None:
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError("GEMINI_API_KEY is not set.")

        client = genai.Client(api_key=api_key, http_options={"api_version": API_VERSION})
        self._open_hardware()
        config = self._build_config()

        logger.info("Connecting to Gemini Live (%s)…", MODEL)
        async with client.aio.live.connect(model=MODEL, config=config) as session:
            self._session  = session
            self._connected = True
            logger.info("Gemini Live session established.")
            await self._broadcast({"type": "status", "status": "connected"})

            # Inject last 10 project history entries
            await self._inject_history()

            # Improvement #2 — all four tasks individually shielded
            self._tasks = [
                asyncio.create_task(self._shielded(self._listen_mic(),    "listen_mic")),
                asyncio.create_task(self._shielded(self._receive_loop(),  "receive_audio")),
                asyncio.create_task(self._shielded(self._play_audio(),    "play_audio")),
                asyncio.create_task(self._shielded(self._keepalive_ui(),  "send_to_ui")),
            ]
            try:
                await asyncio.gather(*self._tasks)
            except asyncio.CancelledError:
                logger.info("Tasks cancelled — shutting down.")
            finally:
                self._connected = False
                await self._broadcast({"type": "status", "status": "disconnected"})

        await self._cleanup_hardware()

    async def stop(self) -> None:
        """Improvement #3 — graceful shutdown."""
        logger.info("HAPPY stop() called — shutting down gracefully.")
        self._connected = False
        try:
            self.playback_queue.put_nowait(None)   # sentinel to unblock play_audio
        except asyncio.QueueFull:
            pass
        for t in self._tasks:
            t.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
        await self._cleanup_hardware()

    # ------------------------------------------------------------------
    # Task 1 — Mic capture → Gemini
    # ------------------------------------------------------------------

    async def _listen_mic(self) -> None:
        loop = asyncio.get_event_loop()
        chunks_sent = 0
        log_every   = 50   # log once every N chunks

        logger.info("[listen_mic] task started")
        while self._connected:
            # Blocking mic read
            try:
                frames, overflowed = await loop.run_in_executor(
                    None, lambda: self._mic_stream.read(CHUNK_FRAMES)
                )
                if overflowed:
                    logger.debug("[listen_mic] mic overflow")
            except Exception as exc:
                logger.warning("[listen_mic] read error: %s", exc)
                await asyncio.sleep(0.01)
                continue

            chunk: bytes = frames.astype("int16").tobytes()

            now = time.monotonic()

            # Echo cancel
            if self._ada_playing or now < self._echo_suppress_until:
                continue

            # VAD
            samples = frames.flatten().astype(np.float32)
            rms = float(np.sqrt(np.mean(samples ** 2))) if len(samples) > 0 else 0.0

            chunks_sent += 1
            if chunks_sent % log_every == 1:
                logger.info("[listen_mic] alive — rms=%.0f, sent=%d", rms, chunks_sent)

            if rms > VAD_RMS_THRESHOLD:
                if not self._user_speaking:
                    self._user_speaking = True
                    logger.info("[listen_mic] speech DETECTED rms=%.0f", rms)
                    asyncio.create_task(self._send_webcam_frame())
                self._last_speech_time = now
            else:
                if self._user_speaking and (now - self._last_speech_time) > VAD_SILENCE_SECS:
                    self._user_speaking = False
                    logger.info("[listen_mic] speech ended")

            # Backpressure
            if self._mic_send_queue.full():
                continue
            self._mic_send_queue.put_nowait(chunk)

            # Send to Gemini
            try:
                await self._session.send_realtime_input(
                    audio=types.Blob(
                        data=chunk,
                        mime_type=f"audio/pcm;rate={SEND_SAMPLE_RATE}",
                    )
                )
                if chunks_sent % log_every == 1:
                    logger.info("[listen_mic] sent chunk #%d to Gemini", chunks_sent)
            except Exception as exc:
                logger.warning("[listen_mic] send_realtime_input error: %s", exc)

    # ------------------------------------------------------------------
    # Task 2 — Receive from Gemini
    # ------------------------------------------------------------------

    async def _receive_loop(self) -> None:
        logger.info("[receive_loop] task started")
        turn_n = 0
        while self._connected:
            turn_n += 1
            logger.info("[receive_loop] waiting for turn #%d from Gemini", turn_n)
            msg_n = 0
            try:
                async for msg in self._session.receive():
                    if not self._connected:
                        return
                    msg_n += 1
                    logger.info("[receive_loop] turn=%d msg=%d  data=%s text=%s sc=%s",
                        turn_n, msg_n,
                        f"bytes[{len(msg.data)}]" if msg.data else None,
                        repr(msg.text)[:60] if msg.text else None,
                        "yes" if msg.server_content else None,
                    )

                    # Audio data
                    if msg.data:
                        if self._user_speaking:
                            await self._clear_playback_queue()
                            continue
                        if self.playback_queue.full():
                            try:
                                self.playback_queue.get_nowait()
                            except asyncio.QueueEmpty:
                                pass
                        await self.playback_queue.put(msg.data)
                        logger.info("[receive_loop] queued audio bytes=%d", len(msg.data))

                    # Transcriptions
                    if msg.server_content:
                        sc = msg.server_content
                        if (
                            hasattr(sc, "input_transcription")
                            and sc.input_transcription
                            and sc.input_transcription.text
                        ):
                            text = sc.input_transcription.text.strip()
                            if text:
                                logger.info("USER: %s", text)
                                self.project.add_entry("user", text)
                                await self._broadcast({"type": "transcript", "role": "user", "text": text})
                                if self._ada_playing:
                                    await self._clear_playback_queue()

                        if (
                            hasattr(sc, "output_transcription")
                            and sc.output_transcription
                            and sc.output_transcription.text
                        ):
                            text = sc.output_transcription.text.strip()
                            if text:
                                logger.info("HAPPY: %s", text)
                                self.project.add_entry("assistant", text)
                                await self._broadcast({"type": "transcript", "role": "assistant", "text": text})

                        if msg.text:
                            text = msg.text.strip()
                            if text:
                                logger.info("HAPPY (text): %.100s", text)
                                self.project.add_entry("assistant", text)
                                await self._broadcast({"type": "transcript", "role": "assistant", "text": text})

                    # Tool calls
                    if msg.tool_call:
                        for fn_call in msg.tool_call.function_calls:
                            await self._handle_tool_call(fn_call)

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("[receive_loop] error: %s", exc)
                await asyncio.sleep(0.5)

    # ------------------------------------------------------------------
    # Task 3 — Speaker playback
    # ------------------------------------------------------------------

    async def _play_audio(self) -> None:
        """Drain playback queue. sd.play() is used for thread-safe playback."""
        loop = asyncio.get_event_loop()

        while self._connected:
            chunk = await self.playback_queue.get()
            if chunk is None:
                break  # sentinel from stop()

            self._ada_playing = True
            try:
                audio_array = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                # sd.play() + sd.wait() is thread-safe and handles device internally
                await loop.run_in_executor(
                    None,
                    lambda a=audio_array: (
                        sd.play(a, samplerate=RECV_SAMPLE_RATE, blocking=True)
                    ),
                )
            except Exception as exc:
                logger.warning("Speaker playback error: %s", exc)

            if self.playback_queue.empty():
                self._ada_playing = False
                self._echo_suppress_until = time.monotonic() + ECHO_TAIL_SECS

    # ------------------------------------------------------------------
    # Task 4 — UI keepalive
    # ------------------------------------------------------------------

    async def _keepalive_ui(self) -> None:
        while self._connected:
            await asyncio.sleep(0.1)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    async def _shielded(coro: Coroutine, name: str) -> None:
        """Improvement #2 — per-task exception shielding."""
        try:
            await coro
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("Task '%s' raised: %s", name, exc)

    async def _broadcast(self, message: dict) -> None:
        if self.ui_broadcast:
            try:
                await self.ui_broadcast(message)
            except Exception as exc:
                logger.warning("UI broadcast error: %s", exc)

    async def _clear_playback_queue(self) -> None:
        cleared = 0
        while not self.playback_queue.empty():
            try:
                self.playback_queue.get_nowait()
                cleared += 1
            except asyncio.QueueEmpty:
                break
        if cleared:
            logger.debug("Cleared %d audio chunks (interrupt)", cleared)
        self._ada_playing = False

    async def _send_webcam_frame(self) -> None:
        if self._camera is None or not self._camera.isOpened():
            return
        try:
            from PIL import Image
            ret, frame = self._camera.read()
            if not ret:
                return
            frame = cv2.resize(frame, (640, 360))
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            img = Image.fromarray(frame_rgb)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=70)
            img_bytes = buf.getvalue()
            await self._session.send_realtime_input(
                video=types.Blob(data=img_bytes, mime_type="image/jpeg")
            )
            logger.debug("Webcam frame sent (%d bytes)", len(img_bytes))
        except Exception as exc:
            logger.warning("Webcam frame error: %s", exc)

    async def _handle_tool_call(self, fn_call: Any) -> None:
        tool_name = fn_call.name
        tool_args = dict(fn_call.args) if fn_call.args else {}
        call_id   = fn_call.id

        logger.info("Tool call: %s(%s)", tool_name, tool_args)
        await self._broadcast({"type": "tool_call", "tool": tool_name, "args": tool_args})

        result = await asyncio.get_event_loop().run_in_executor(
            None, dispatch, tool_name, tool_args
        )
        logger.info("Tool result [%s]: %.200s", tool_name, result)
        await self._broadcast({"type": "tool_result", "tool": tool_name, "result": result})

        # Use SDK 1.64 correct API for tool responses
        try:
            await self._session.send_tool_response(
                function_responses=types.FunctionResponse(
                    name=tool_name,
                    id=call_id,
                    response={"result": result},
                )
            )
        except Exception as exc:
            logger.warning("send_tool_response failed: %s", exc)

    async def _inject_history(self) -> None:
        """Inject last 10 project history entries using send_client_content."""
        history = self.project.get_history(n=10)
        if not history:
            return
        try:
            turns = [
                types.Content(
                    role="user" if e["role"] == "user" else "model",
                    parts=[types.Part(text=e["text"])],
                )
                for e in history
            ]
            await self._session.send_client_content(turns=turns, turn_complete=False)
            logger.info("Injected %d history entries.", len(history))
        except Exception as exc:
            logger.warning("History injection failed: %s", exc)

    def _build_config(self) -> types.LiveConnectConfig:
        system_prompt = _load_system_prompt()
        tool_list = types.Tool(
            function_declarations=[
                types.FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters=t["parameters"],
                )
                for t in TOOL_DECLARATIONS
            ]
        )
        return types.LiveConnectConfig(
            system_instruction=system_prompt,
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_NAME)
                )
            ),
            tools=[tool_list],
        )

    def _open_hardware(self) -> None:
        self._mic_stream = sd.InputStream(
            samplerate=SEND_SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_FRAMES,
        )
        self._mic_stream.start()

        # Speaker output is handled by sd.play() — no persistent stream needed

        self._camera = cv2.VideoCapture(0)
        if not self._camera.isOpened():
            logger.warning("No webcam found — vision disabled.")
            self._camera = None

        logger.info("Hardware opened (mic=%dHz, speaker=sd.play@%dHz).", SEND_SAMPLE_RATE, RECV_SAMPLE_RATE)

    async def _cleanup_hardware(self) -> None:
        """Improvement #3 — release all hardware on shutdown."""
        logger.info("Releasing hardware resources...")
        try:
            if self._mic_stream:
                self._mic_stream.stop()
                self._mic_stream.close()
        except Exception as exc:
            logger.warning("Error closing mic: %s", exc)

        try:
            sd.stop()  # stop any sd.play() in progress
        except Exception as exc:
            logger.warning("Error stopping sd.play: %s", exc)

        try:
            if self._camera and self._camera.isOpened():
                self._camera.release()
        except Exception as exc:
            logger.warning("Error releasing webcam: %s", exc)

        self._mic_stream = None
        self._camera = None
        logger.info("Hardware resources released.")


# ---------------------------------------------------------------------------
# Standalone entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
        datefmt="%H:%M:%S",
    )
    project  = os.getenv("PROJECT_NAME", "default")
    loop_obj = AudioLoop(project_name=project)
    try:
        asyncio.run(loop_obj.run())
    except KeyboardInterrupt:
        print("\nHAPPY stopped.")
