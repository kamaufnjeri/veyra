from __future__ import annotations

from typing import List, Tuple, Optional, Dict
import os

import argostranslate.package
import argostranslate.translate


class SubtitlesTranslator:
    """
    Fast subtitle translator using Argos Translate.

    Main optimizations:
        - Loads the translation model only once.
        - Avoids downloading an already-installed model.
        - Uses text caching.
        - Translates multiple subtitle lines in one model call.
        - Preserves subtitle ordering.
        - Preserves blank subtitles.
        - Supports single-text translation for SubtitleService.
        - Supports timed subtitle pairs.

    Expected structures:

        transcripts:
            ["Hello", "How are you?", "I'm fine."]

        timed_subtitles:
            [
                ((0.0, 2.0), "Hello"),
                ((2.0, 4.0), "How are you?"),
            ]
    """

    # Number of subtitle lines combined into one translation request.
    #
    # Larger values reduce Python/model overhead, but extremely large
    # values can make individual translation requests too expensive.
    DEFAULT_BATCH_SIZE = 32

    def __init__(
        self,
        source_language: str,
        target_language: str,
        error_messages_callback=None,
        batch_size: int = DEFAULT_BATCH_SIZE,
        **kwargs,
    ):
        self.source_language = self._normalize_language(source_language)
        self.target_language = self._normalize_language(target_language)

        self.error_messages_callback = error_messages_callback

        self.translation_model = None

        self.batch_size = max(1, int(batch_size))

        # Cache:
        #
        # original text -> translated text
        #
        # This is particularly useful when transcripts contain repeated
        # phrases such as:
        #
        # "Thank you."
        # "Thank you."
        # "Thank you."
        self._translation_cache: Dict[str, str] = {}

        self._initialize_argos_settings()
        self._initialize_translation_model()

    # ==========================================================
    # Language helpers
    # ==========================================================

    @staticmethod
    def _normalize_language(language: Optional[str]) -> str:
        """
        Normalize language codes.

        Examples:
            en-US -> en
            EN_us -> en
            es -> es
        """

        if not language:
            return ""

        return str(language).strip().lower().replace("_", "-").split("-")[0]

    # ==========================================================
    # Argos configuration
    # ==========================================================

    def _initialize_argos_settings(self) -> None:
        """
        Configure Argos for faster translation.

        These are environment variables used by Argos Translate.
        We set them before the translation model is loaded.
        """

        try:
            # Number of batches Argos processes.
            os.environ.setdefault(
                "ARGOS_BATCH_SIZE",
                str(self.batch_size),
            )

            # Let CTranslate2 choose the appropriate CPU thread count.
            os.environ.setdefault(
                "ARGOS_INTRA_THREADS",
                "0",
            )

            # One translator is normally sufficient for this application.
            os.environ.setdefault(
                "ARGOS_INTER_THREADS",
                "1",
            )

            # int8 is generally much faster on CPU with some potential
            # accuracy differences.
            #
            # We do NOT force it if the user already configured another
            # compute type.
            os.environ.setdefault(
                "ARGOS_COMPUTE_TYPE",
                "int8",
            )

        except Exception as exc:
            self._error(
                f"Could not configure Argos performance settings: {exc}"
            )

    # ==========================================================
    # Model initialization
    # ==========================================================

    def _initialize_translation_model(self) -> None:
        """
        Load the required Argos translation model.

        If the model is already installed, we do not download it again.
        """

        if not self.source_language or not self.target_language:
            self._error(
                "Source and target languages are required."
            )
            return

        if self.source_language == self.target_language:
            self._error(
                "Source and target languages are the same. "
                "Translation is unnecessary."
            )
            return

        try:
            # --------------------------------------------------
            # First check installed languages.
            # --------------------------------------------------

            installed_languages = (
                argostranslate.translate.get_installed_languages()
            )

            from_lang = next(
                (
                    language
                    for language in installed_languages
                    if language.code == self.source_language
                ),
                None,
            )

            to_lang = next(
                (
                    language
                    for language in installed_languages
                    if language.code == self.target_language
                ),
                None,
            )

            # --------------------------------------------------
            # Check whether the translation model already exists.
            # --------------------------------------------------

            if from_lang and to_lang:
                existing_translation = from_lang.get_translation(to_lang)

                if existing_translation is not None:
                    self.translation_model = existing_translation
                    return

            # --------------------------------------------------
            # Model is not installed.
            #
            # Only now do we access the package index.
            # --------------------------------------------------

            self._error(
                f"Installing Argos model "
                f"{self.source_language} -> {self.target_language}..."
            )

            argostranslate.package.update_package_index()

            available_packages = (
                argostranslate.package.get_available_packages()
            )

            package_to_install = next(
                (
                    package
                    for package in available_packages
                    if package.from_code == self.source_language
                    and package.to_code == self.target_language
                ),
                None,
            )

            if package_to_install is None:
                self._error(
                    f"No Argos package available for "
                    f"{self.source_language} -> "
                    f"{self.target_language}"
                )
                return

            download_path = package_to_install.download()

            argostranslate.package.install_from_path(
                download_path
            )

            # --------------------------------------------------
            # Reload installed languages after installation.
            # --------------------------------------------------

            installed_languages = (
                argostranslate.translate.get_installed_languages()
            )

            from_lang = next(
                (
                    language
                    for language in installed_languages
                    if language.code == self.source_language
                ),
                None,
            )

            to_lang = next(
                (
                    language
                    for language in installed_languages
                    if language.code == self.target_language
                ),
                None,
            )

            if not from_lang or not to_lang:
                self._error(
                    f"Could not load installed languages for "
                    f"{self.source_language} -> "
                    f"{self.target_language}"
                )
                return

            self.translation_model = (
                from_lang.get_translation(to_lang)
            )

            if self.translation_model is None:
                self._error(
                    f"Could not create translation model for "
                    f"{self.source_language} -> "
                    f"{self.target_language}"
                )

        except Exception as exc:
            self.translation_model = None

            self._error(
                f"Failed to initialize translation model: {exc}"
            )

    # ==========================================================
    # Single translation
    # ==========================================================

    def translate(self, text: str) -> str:
        """
        Translate one piece of text.

        Used by SubtitleService:

            translator.translate(text)
        """

        if text is None:
            return text

        original_text = str(text)

        if not original_text.strip():
            return text

        if self.translation_model is None:
            return text

        # ------------------------------------------------------
        # Cache lookup
        # ------------------------------------------------------

        cached = self._translation_cache.get(original_text)

        if cached is not None:
            return cached

        try:
            translated_text = self.translation_model.translate(
                original_text
            )

            if translated_text is None:
                translated_text = original_text
            else:
                translated_text = str(translated_text).strip()

                if not translated_text:
                    translated_text = original_text

            self._translation_cache[original_text] = translated_text

            return translated_text

        except Exception as exc:
            self._error(
                f"Translation failed for line "
                f"'{original_text}': {exc}"
            )

            return original_text

    # ==========================================================
    # Batch translation
    # ==========================================================

    def _translate_batch(
        self,
        texts: List[str],
    ) -> List[str]:
        """
        Translate a batch of subtitle lines.

        Argos's public translation interface accepts one text at a time,
        so we combine multiple subtitle lines into one translation request
        using newline separators.

        The separator lets us map the translated lines back to the
        original subtitle entries.

        If Argos changes or collapses the separators, we fall back to
        translating each line individually.
        """

        if not texts:
            return []

        if self.translation_model is None:
            return texts

        # ------------------------------------------------------
        # Remove already cached strings from the actual request.
        # ------------------------------------------------------

        results: List[Optional[str]] = [None] * len(texts)

        uncached_indices: List[int] = []
        uncached_texts: List[str] = []

        for index, text in enumerate(texts):
            original = str(text)

            if not original.strip():
                results[index] = original
                continue

            cached = self._translation_cache.get(original)

            if cached is not None:
                results[index] = cached
                continue

            uncached_indices.append(index)
            uncached_texts.append(original)

        if not uncached_texts:
            return [
                result if result is not None else texts[i]
                for i, result in enumerate(results)
            ]

        # ------------------------------------------------------
        # IMPORTANT:
        #
        # Use a separator that is very unlikely to occur naturally.
        #
        # Newlines are understood by Argos's paragraph handling.
        # ------------------------------------------------------

        combined_text = "\n".join(uncached_texts)

        try:
            translated_combined = self.translation_model.translate(
                combined_text
            )

            translated_combined = (
                str(translated_combined)
                if translated_combined is not None
                else ""
            )

            translated_lines = translated_combined.splitlines()

            # --------------------------------------------------
            # The number of output lines must match the input.
            #
            # If it does, map them directly.
            # --------------------------------------------------

            if len(translated_lines) == len(uncached_texts):

                for index, original, translated in zip(
                    uncached_indices,
                    uncached_texts,
                    translated_lines,
                ):
                    translated = translated.strip()

                    if not translated:
                        translated = original

                    self._translation_cache[original] = translated

                    results[index] = translated

                return [
                    result if result is not None else texts[i]
                    for i, result in enumerate(results)
                ]

            # --------------------------------------------------
            # Argos may have changed the paragraph structure.
            #
            # Fall back safely rather than corrupting subtitles.
            # --------------------------------------------------

            self._error(
                "Batch translation returned an unexpected number "
                "of lines. Falling back to individual translation."
            )

        except Exception as exc:
            self._error(
                f"Batch translation failed: {exc}. "
                f"Falling back to individual translation."
            )

        # ------------------------------------------------------
        # Safe fallback
        # ------------------------------------------------------

        for index, original in zip(
            uncached_indices,
            uncached_texts,
        ):
            results[index] = self.translate(original)

        return [
            result if result is not None else texts[i]
            for i, result in enumerate(results)
        ]

    # ==========================================================
    # Translate transcript list
    # ==========================================================

    def __call__(
        self,
        transcripts: List[str],
    ) -> List[str]:
        """
        Translate a list of transcript strings.

        The list length and ordering are preserved.
        """

        if not transcripts:
            return transcripts

        if self.translation_model is None:
            return transcripts

        translated_transcripts: List[str] = []

        # ------------------------------------------------------
        # Process subtitles in batches.
        # ------------------------------------------------------

        total = len(transcripts)

        for start in range(0, total, self.batch_size):
            end = min(
                start + self.batch_size,
                total,
            )

            batch = transcripts[start:end]

            translated_batch = self._translate_batch(
                batch
            )

            translated_transcripts.extend(
                translated_batch
            )

        return translated_transcripts

    # ==========================================================
    # Timed subtitle translation
    # ==========================================================

    def translate_pairs(
        self,
        timed_subtitles: List[
            Tuple[Tuple[float, float], str]
        ],
    ) -> List[
        Tuple[Tuple[float, float], str]
    ]:
        """
        Translate timed subtitles while preserving timestamps.

        Input:

            [
                ((0.0, 2.0), "Hello"),
                ((2.0, 4.0), "How are you?"),
            ]

        Output:

            [
                ((0.0, 2.0), "Hola"),
                ((2.0, 4.0), "¿Cómo estás?"),
            ]
        """

        if not timed_subtitles:
            return timed_subtitles

        if self.translation_model is None:
            return timed_subtitles

        regions = [
            region
            for region, _ in timed_subtitles
        ]

        texts = [
            text
            for _, text in timed_subtitles
        ]

        translated_texts = self(texts)

        return [
            (
                regions[index],
                translated_texts[index],
            )
            for index in range(len(regions))
        ]

    # ==========================================================
    # Cache
    # ==========================================================

    def clear_cache(self) -> None:
        """
        Clear translated text cache.
        """

        self._translation_cache.clear()

    def cache_size(self) -> int:
        """
        Return number of cached translations.
        """

        return len(self._translation_cache)

    # ==========================================================
    # Status
    # ==========================================================

    @property
    def is_available(self) -> bool:
        """
        True when a translation model is ready.
        """

        return self.translation_model is not None

    # ==========================================================
    # Error callback
    # ==========================================================

    def _error(self, error: str) -> None:
        """
        Send errors/warnings to the configured callback.
        """

        if self.error_messages_callback:
            try:
                self.error_messages_callback(error)
                return
            except Exception:
                pass

        print(error)