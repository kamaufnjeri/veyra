from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple

import httpx
import requests


class SubtitlesTranslator:
    """
    Fast subtitle translator using Google's GTX endpoint.

    No CTranslate2.
    No NLLB model.
    No local model files.

    Example:

        translator = SubtitlesTranslator(
            source_language="es",
            target_language="en",
        )

        result = translator([
            "Hola, ¿cómo estás?",
            "Me llamo Carlos.",
        ])
    """

    DEFAULT_TIMEOUT = 30
    DEFAULT_RETRIES = 3
    DEFAULT_BATCH_SIZE = 16

    def __init__(
        self,
        source_language: str,
        target_language: str,
        error_messages_callback=None,
        progress_callback=None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        timeout: int = DEFAULT_TIMEOUT,
        retries: int = DEFAULT_RETRIES,
        patience: int = 1,
    ):
        self.source_language = self._normalize_language(
            source_language
        )

        self.target_language = self._normalize_language(
            target_language
        )

        self.error_messages_callback = (
            error_messages_callback
        )

        self.progress_callback = (
            progress_callback
        )

        self.batch_size = max(
            1,
            int(batch_size),
        )

        self.timeout = max(
            1,
            int(timeout),
        )

        self.retries = max(
            0,
            int(retries),
        )

        self.patience = max(
            0,
            int(patience),
        )

        self._translation_cache: Dict[
            str,
            str,
        ] = {}

        self._session = requests.Session()

        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "(KHTML, like Gecko) "
                    "Chrome/131.0 Safari/537.36"
                ),
                "Referer": (
                    "https://translate.google.com/"
                ),
            }
        )

    # ==========================================================
    # LANGUAGE
    # ==========================================================

    @staticmethod
    def _normalize_language(
        language: Optional[str],
    ) -> str:

        if not language:
            return ""

        return (
            str(language)
            .strip()
            .lower()
            .replace("_", "-")
        )

    # ==========================================================
    # STATUS
    # ==========================================================

    @property
    def is_available(self) -> bool:
        return bool(
            self.source_language
            and self.target_language
        )

    # ==========================================================
    # SINGLE TRANSLATION
    # ==========================================================

    def translate(
        self,
        text: Optional[str],
    ) -> str:

        if text is None:
            return ""

        original = str(text)

        if not original.strip():
            return original

        # ------------------------------------------------------
        # Cache
        # ------------------------------------------------------

        cached = self._translation_cache.get(
            original
        )

        if cached is not None:
            return cached

        if not self.is_available:
            raise RuntimeError(
                "Translator is not configured."
            )

        try:

            translated = self.google_translate(
                text=original,
                source=self.source_language,
                target=self.target_language,
            )

            if not translated:
                return original

            # --------------------------------------------------
            # GTX occasionally returns a trailing newline.
            # Retry if requested.
            # --------------------------------------------------

            attempts = 0

            while (
                translated.endswith("\n")
                and attempts < self.patience
            ):
                attempts += 1

                retry_result = (
                    self.google_translate(
                        text=original,
                        source=self.source_language,
                        target=self.target_language,
                    )
                )

                if not retry_result:
                    break

                translated = retry_result

            translated = translated.strip()

            if not translated:
                translated = original

            self._translation_cache[
                original
            ] = translated

            return translated

        except Exception as exc:

            self._error(
                f"Translation failed: {exc}"
            )

            # Keep subtitle processing alive.
            return original

    # ==========================================================
    # GOOGLE GTX
    # ==========================================================

    def google_translate(
        self,
        text: str,
        source: str,
        target: str,
    ) -> Optional[str]:

        url = (
            "https://translate.googleapis.com/"
            "translate_a/single"
        )

        params = {
            "client": "gtx",
            "sl": source,
            "tl": target,
            "dt": "t",
            "q": text,
        }

        last_error = None

        for attempt in range(
            self.retries + 1
        ):

            try:

                response = self._session.get(
                    url,
                    params=params,
                    timeout=self.timeout,
                )

                response.raise_for_status()

                data = response.json()

                translated = (
                    self._parse_response(data)
                )

                if translated:
                    return translated

                raise RuntimeError(
                    "Google returned an empty translation."
                )

            except requests.exceptions.RequestException as exc:

                last_error = exc

                if attempt < self.retries:
                    time.sleep(
                        min(
                            0.5 * (attempt + 1),
                            2.0,
                        )
                    )

            except Exception as exc:

                last_error = exc

                if attempt < self.retries:
                    time.sleep(0.2)

        # ------------------------------------------------------
        # HTTPX fallback
        # ------------------------------------------------------

        try:

            with httpx.Client(
                timeout=self.timeout,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(Windows NT 10.0; Win64; x64)"
                    ),
                    "Referer": (
                        "https://translate.google.com/"
                    ),
                },
            ) as client:

                response = client.get(
                    url,
                    params=params,
                )

                response.raise_for_status()

                return self._parse_response(
                    response.json()
                )

        except Exception as exc:

            last_error = exc

        if last_error:
            self._error(
                last_error
            )

        return None

    # ==========================================================
    # RESPONSE PARSER
    # ==========================================================

    def _parse_response(
        self,
        response_data: Any,
    ) -> Optional[str]:

        try:

            if not response_data:
                return None

            if not isinstance(
                response_data,
                list,
            ):
                return None

            if not response_data[0]:
                return None

            parts = []

            for item in response_data[0]:

                if not item:
                    continue

                if not isinstance(
                    item,
                    list,
                ):
                    continue

                if len(item) < 1:
                    continue

                translated_text = item[0]

                if translated_text:
                    parts.append(
                        str(translated_text)
                    )

            if not parts:
                return None

            return "".join(parts)

        except (
            IndexError,
            KeyError,
            TypeError,
        ) as exc:

            self._error(exc)

            return None

    # ==========================================================
    # BATCH
    # ==========================================================

    def _translate_batch(
        self,
        texts: List[str],
    ) -> List[str]:

        if not texts:
            return []

        results: List[Optional[str]] = [
            None
        ] * len(texts)

        uncached_indices = []
        uncached_texts = []

        # ------------------------------------------------------
        # Cache lookup
        # ------------------------------------------------------

        for index, text in enumerate(texts):

            text = str(text)

            if not text.strip():
                results[index] = text
                continue

            cached = (
                self._translation_cache.get(
                    text
                )
            )

            if cached is not None:
                results[index] = cached
            else:
                uncached_indices.append(index)
                uncached_texts.append(text)

        # Everything was cached.
        if not uncached_texts:

            return [
                results[index]
                if results[index] is not None
                else str(texts[index])
                for index in range(len(texts))
            ]

        # ------------------------------------------------------
        # Google GTX does not have a reliable official
        # multi-sentence batch API, so translate requests
        # individually.
        #
        # The Session keeps HTTP connections alive, which makes
        # this considerably cheaper than creating a new client
        # for every subtitle.
        # ------------------------------------------------------

        for index, text in zip(
            uncached_indices,
            uncached_texts,
        ):

            translated = self.translate(
                text
            )

            results[index] = translated

        return [
            results[index]
            if results[index] is not None
            else str(texts[index])
            for index in range(len(texts))
        ]

    # ==========================================================
    # LIST TRANSLATION
    # ==========================================================

    def __call__(
        self,
        transcripts: List[str],
    ) -> List[str]:

        if not transcripts:
            return []

        if not self.is_available:
            raise RuntimeError(
                "Translator is not configured."
            )

        translated: List[str] = []

        total = len(transcripts)

        for start in range(
            0,
            total,
            self.batch_size,
        ):

            end = min(
                start + self.batch_size,
                total,
            )

            batch = transcripts[
                start:end
            ]

            translated_batch = (
                self._translate_batch(
                    batch
                )
            )

            translated.extend(
                translated_batch
            )

            self._progress(
                "Translating subtitles",
                int(end * 100 / total),
            )

        return translated

    # ==========================================================
    # TIMED SUBTITLES
    # ==========================================================

    def translate_pairs(
        self,
        timed_subtitles: List[
            Tuple[
                Tuple[float, float],
                str,
            ]
        ],
    ) -> List[
        Tuple[
            Tuple[float, float],
            str,
        ]
    ]:

        if not timed_subtitles:
            return []

        regions = [
            region
            for region, _ in timed_subtitles
        ]

        texts = [
            text
            for _, text in timed_subtitles
        ]

        translated = self(
            texts
        )

        return [
            (
                regions[index],
                translated[index],
            )
            for index in range(
                len(regions)
            )
        ]

    # ==========================================================
    # CACHE
    # ==========================================================

    def clear_cache(self) -> None:
        self._translation_cache.clear()

    def cache_size(self) -> int:
        return len(
            self._translation_cache
        )

    # ==========================================================
    # PROGRESS
    # ==========================================================

    def _progress(
        self,
        message: str,
        percentage: int,
    ) -> None:

        if not self.progress_callback:
            return

        try:
            self.progress_callback(
                message,
                percentage,
            )
        except Exception:
            pass

    # ==========================================================
    # ERROR
    # ==========================================================

    def _error(
        self,
        error: Any,
    ) -> None:

        if self.error_messages_callback:

            try:
                self.error_messages_callback(
                    error
                )
                return
            except Exception:
                pass

        print(
            f"ERROR: {error}"
        )

    # ==========================================================
    # CLEANUP
    # ==========================================================

    def close(self) -> None:

        try:
            self._session.close()
        except Exception:
            pass