import asyncio
import json
import random
import httpx
from typing import Callable, Awaitable
from deepgram import DeepgramClient, LiveOptions, LiveTranscriptionEvents
from app.core.config import settings

# --- Voice Models ---
MALE_VOICES = [
    "aura-2-odysseus-en", "aura-2-apollo-en", "aura-2-arcas-en", "aura-2-aries-en",
    "aura-2-atlas-en", "aura-2-draco-en", "aura-2-hermes-en", "aura-2-hyperion-en",
    "aura-2-jupiter-en", "aura-2-mars-en", "aura-2-neptune-en", "aura-2-orion-en",
    "aura-2-orpheus-en", "aura-2-pluto-en", "aura-2-saturn-en", "aura-2-zeus-en"
]

FEMALE_VOICES = [
    "aura-2-thalia-en", "aura-2-amalthea-en", "aura-2-andromeda-en", "aura-2-asteria-en",
    "aura-2-athena-en", "aura-2-aurora-en", "aura-2-callista-en", "aura-2-cora-en",
    "aura-2-cordelia-en", "aura-2-delia-en", "aura-2-electra-en", "aura-2-harmonia-en",
    "aura-2-helena-en", "aura-2-hera-en", "aura-2-iris-en", "aura-2-janus-en",
    "aura-2-juno-en", "aura-2-luna-en", "aura-2-minerva-en", "aura-2-ophelia-en",
    "aura-2-pandora-en", "aura-2-phoebe-en", "aura-2-selene-en", "aura-2-theia-en",
    "aura-2-vesta-en"
]

class LiveTranscription:
    """
    Manages a live transcription connection to Deepgram, accumulating the transcript
    until explicitly stopped.
    """
    def __init__(self, deepgram_client: DeepgramClient):
        self.client = deepgram_client
        self.dg_connection = self.client.listen.live.v("1")
        self._is_active = False
        self.full_transcript = ""

    async def start(self):
        options = LiveOptions(
            model="nova-2",
            language="en-US",
            smart_format=True,
            encoding="linear16",
            sample_rate=16000,
        )
        self.dg_connection.on(LiveTranscriptionEvents.Transcript, self._on_transcript) # type: ignore
        self.dg_connection.on(LiveTranscriptionEvents.Error, self._on_error) # type: ignore
        
        try:
            if not self.dg_connection.start(options): # type: ignore
                print("[LiveTranscription] Failed to start connection.")
                return

            self._is_active = True
            self.full_transcript = "" # Reset transcript on start
            print("[LiveTranscription] Connected to Deepgram via SDK.")
        except Exception as e:
            print(f"[LiveTranscription] Failed to connect to Deepgram: {e}")

    async def send(self, audio_chunk: bytes):
        if self._is_active:
            await self.dg_connection.send(audio_chunk) # type: ignore

    def _on_transcript(self, *args, **kwargs):
        result = kwargs.get("result")
        if result and result.channel and result.channel.alternatives:
            transcript = result.channel.alternatives[0].transcript
            if transcript:
                self.full_transcript += transcript + " "

    def _on_error(self, *args, **kwargs):
        error = kwargs.get("error")
        print(f"[LiveTranscription] Deepgram Error: {error}")

    async def stop(self) -> str:
        """Stops the connection and returns the final accumulated transcript."""
        if self._is_active:
            self._is_active = False
            await self.dg_connection.finish() # type: ignore
            print("[LiveTranscription] Connection closed.")
        return self.full_transcript.strip()

class DeepgramService:
    """
    A service to interact with Deepgram's APIs for Text-to-Speech and Speech-to-Text.
    """
    def __init__(self):
        self.client = DeepgramClient(settings.DEEPGRAM_API_KEY)
        self.http_client = httpx.AsyncClient()
        self.tts_url = "https://api.deepgram.com/v1/speak"

    async def text_to_speech_stream(self, text: str, gender: str):
        if gender.lower() == 'male':
            model = random.choice(MALE_VOICES)
        else:
            model = random.choice(FEMALE_VOICES)

        print(f"[DeepgramService] Requesting TTS for: '{text[:60]}...' (model: {model})")

        headers = {
            "Authorization": f"Token {settings.DEEPGRAM_API_KEY}",
            "Content-Type": "application/json"
        }
        
        params = {
            "model": model,
            "encoding": "linear16",
            "sample_rate": 24000
        }
        
        payload = {"text": text}

        try:
            async with self.http_client.stream("POST", self.tts_url, headers=headers, params=params, json=payload, timeout=60) as response:
                if response.is_error:
                    error_body = await response.aread()
                    print(f"[DeepgramService] Error from API: {response.status_code} - {error_body.decode()}")
                    response.raise_for_status()

                print(f"[DeepgramService] Success: {response.status_code}. Streaming audio...")
                async for chunk in response.aiter_bytes():
                    yield chunk
                print("[DeepgramService] Audio stream finished.")

        except httpx.RequestError as e:
            print(f"[DeepgramService] HTTP Request Error: {e}")
        except Exception as e:
            print(f"[DeepgramService] An unexpected error occurred: {e}")
        finally:
            print(f"[DeepgramService] TTS function finished for: '{text[:60]}...'")

    def get_live_transcriber(self) -> "LiveTranscription":
        """
        Returns an instance of the asynchronous LiveTranscription manager.
        """
        return LiveTranscription(self.client)

# Singleton instance for easy access
deepgram_service = DeepgramService()