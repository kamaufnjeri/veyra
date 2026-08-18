from __future__ import annotations

import json
import os

import httpx
import requests
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class SpeechRecognizer:

    def __init__(
        self,
        language: str = "en",
        rate: int = 48000,
        retries: int = 3,
        api_key: str | None = None,
        timeout: int = 30,
        error_messages_callback=None,
    ):

        self.language = language
        self.rate = rate
        self.retries = retries
        self.timeout = timeout

        self.api_key = (
            api_key
            or os.getenv(
                "GOOGLE_SPEECH_API_KEY"
            )
        )

        self.error_messages_callback = (
            error_messages_callback
        )

    def __call__(self, data):

        try:

            if not data:
                return None

            for _ in range(self.retries):

                url = (
                    "http://www.google.com/"
                    "speech-api/v2/recognize"
                    "?client=chromium"
                    f"&lang={self.language}"
                )

                if self.api_key:
                    url += (
                        f"&key={self.api_key}"
                    )

                headers = {
                    "Content-Type": (
                        f"audio/x-flac;"
                        f" rate={self.rate}"
                    )
                }

                response = None

                try:

                    response = requests.post(
                        url,
                        data=data,
                        headers=headers,
                        timeout=self.timeout,
                    )

                except requests.exceptions.ConnectionError:

                    try:

                        response = httpx.post(
                            url,
                            content=data,
                            headers=headers,
                            timeout=self.timeout,
                        )

                    except httpx.HTTPError as err:
                        self._error(f"HTTP Connection Error: {err}")
                        continue

                if response is None:
                    self._error("No response received from speech API.")
                    continue

                if response.status_code != 200:
                    # Prints the exact HTTP error code and reason returned by Google
                    self._error(f"API Error [{response.status_code}]: {response.text}")
                    continue

                for line in (
                    response.content
                    .decode(
                        "utf-8",
                        errors="replace",
                    )
                    .split("\n")
                ):

                    if not line.strip():
                        continue

                    try:

                        parsed = json.loads(
                            line
                        )

                        results = parsed.get(
                            "result",
                            [],
                        )

                        if not results:
                            continue

                        alternatives = results[0].get(
                            "alternative",
                            [],
                        )

                        if not alternatives:
                            continue

                        transcript = alternatives[0].get(
                            "transcript"
                        )

                        if not transcript:
                            continue

                        transcript = transcript.strip()

                        return (
                            transcript[:1].upper()
                            + transcript[1:]
                        )

                    except (
                        json.JSONDecodeError,
                        KeyError,
                        IndexError,
                        TypeError,
                    ):
                        continue

            return None

        except KeyboardInterrupt:

            self._error(
                "Cancelling all tasks"
            )

            return None

        except Exception as exc:

            self._error(exc)

            return None

    # ----------------------------------------------------------
    # Error
    # ----------------------------------------------------------

    def _error(self, error):

        if self.error_messages_callback:
            self.error_messages_callback(error)
        else:
            print(error)