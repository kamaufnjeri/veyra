from __future__ import annotations

from typing import Optional

import httpx
import requests


class SentenceTranslator:
    """
    Translate subtitle sentences using Google's GTX translation endpoint.

    This replaces the translation functionality that originally lived
    inside the monolithic pyautosrt.py file.
    """

    def __init__(
        self,
        source_language: str,
        target_language: str,
        patience: int = -1,
        timeout: int = 30,
        error_messages_callback=None,
    ):
        self.source_language = source_language
        self.target_language = target_language
        self.patience = patience
        self.timeout = timeout
        self.error_messages_callback = error_messages_callback

    def __call__(
        self,
        sentence: Optional[str],
    ) -> Optional[str]:

        try:
            if not sentence:
                return None

            sentence = str(sentence).strip()

            if not sentence:
                return None

            translated = self.google_translate(
                text=sentence,
                source=self.source_language,
                target=self.target_language,
            )

            if translated is None:
                return None

            attempts = 0

            while (
                translated.endswith("\n")
                and (
                    self.patience == -1
                    or attempts < self.patience
                )
            ):
                attempts += 1

                retry_result = self.google_translate(
                    text=sentence,
                    source=self.source_language,
                    target=self.target_language,
                )

                if retry_result is None:
                    break

                translated = retry_result

                if not translated.endswith("\n"):
                    break

            return translated.strip()

        except KeyboardInterrupt:
            self._error("Cancelling all tasks")
            return None

        except Exception as exc:
            self._error(exc)
            return None

    # ----------------------------------------------------------
    # Google Translate
    # ----------------------------------------------------------

    def google_translate(
        self,
        text: str,
        source: str,
        target: str,
    ) -> Optional[str]:

        url = "https://translate.googleapis.com/translate_a/single"

        params = {
            "client": "gtx",
            "sl": source,
            "tl": target,
            "dt": "t",
            "q": text,
        }

        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64)"
            ),
            "Referer": "https://translate.google.com/",
        }

        try:
            response = requests.get(
                url,
                params=params,
                headers=headers,
                timeout=self.timeout,
            )

            response.raise_for_status()

            return self._parse_response(
                response.json()
            )

        except requests.exceptions.ConnectionError:

            try:
                with httpx.Client(
                    timeout=self.timeout
                ) as client:

                    response = client.get(
                        url,
                        params=params,
                        headers=headers,
                    )

                response.raise_for_status()

                return self._parse_response(
                    response.json()
                )

            except httpx.HTTPError as exc:
                self._error(exc)
                return None

        except requests.exceptions.RequestException as exc:
            self._error(exc)
            return None

        except KeyboardInterrupt:
            self._error("Cancelling all tasks")
            return None

        except Exception as exc:
            self._error(exc)
            return None

    # ----------------------------------------------------------
    # Response parser
    # ----------------------------------------------------------

    def _parse_response(
        self,
        response_data,
    ) -> Optional[str]:

        try:
            if not response_data:
                return None

            translation_parts = []

            for item in response_data[0]:

                if not item:
                    continue

                translated_text = item[0]

                if translated_text:
                    translation_parts.append(
                        translated_text
                    )

            if not translation_parts:
                return None

            return "".join(
                translation_parts
            )

        except (
            IndexError,
            KeyError,
            TypeError,
        ) as exc:

            self._error(exc)
            return None

    # ----------------------------------------------------------
    # Error callback
    # ----------------------------------------------------------

    def _error(self, error):

        if self.error_messages_callback:
            self.error_messages_callback(error)
        else:
            print(error)