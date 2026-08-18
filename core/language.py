from dataclasses import dataclass
from typing import Callable, List, Optional


@dataclass(frozen=True)
class LanguageInfo:
    """
    Represents one language supported by Veyra.

    code:
        ISO-639-1 / Google Translate / Vosk code.

    name:
        Human-readable language name.

    ffmpeg_code:
        ISO-639-2 code used when working with FFmpeg subtitle metadata.
    """

    code: str
    name: str
    ffmpeg_code: str


class Language:
    """
    Central language registry for Veyra.

    The language definitions are stored only once in `_languages`.
    All lookup dictionaries are generated automatically.
    """

    _languages = (
        LanguageInfo("af", "Afrikaans", "afr"),
        LanguageInfo("sq", "Albanian", "alb"),
        LanguageInfo("am", "Amharic", "amh"),
        LanguageInfo("ar", "Arabic", "ara"),
        LanguageInfo("hy", "Armenian", "hye"),
        LanguageInfo("as", "Assamese", "asm"),
        LanguageInfo("ay", "Aymara", "aym"),
        LanguageInfo("az", "Azerbaijani", "aze"),
        LanguageInfo("bm", "Bambara", "bam"),
        LanguageInfo("eu", "Basque", "eus"),
        LanguageInfo("be", "Belarusian", "bel"),
        LanguageInfo("bn", "Bengali", "ben"),
        LanguageInfo("bho", "Bhojpuri", "bho"),
        LanguageInfo("bs", "Bosnian", "bos"),
        LanguageInfo("bg", "Bulgarian", "bul"),
        LanguageInfo("ca", "Catalan", "cat"),
        LanguageInfo("ceb", "Cebuano", "ceb"),
        LanguageInfo("ny", "Chichewa", "nya"),
        LanguageInfo("zh", "Chinese", "zho"),
        LanguageInfo("zh-CN", "Chinese (Simplified)", "zho-CN"),
        LanguageInfo("zh-TW", "Chinese (Traditional)", "zho-TW"),
        LanguageInfo("co", "Corsican", "cos"),
        LanguageInfo("hr", "Croatian", "hrv"),
        LanguageInfo("cs", "Czech", "ces"),
        LanguageInfo("da", "Danish", "dan"),
        LanguageInfo("dv", "Dhivehi", "div"),
        LanguageInfo("doi", "Dogri", "doi"),
        LanguageInfo("nl", "Dutch", "nld"),
        LanguageInfo("en", "English", "eng"),
        LanguageInfo("eo", "Esperanto", "epo"),
        LanguageInfo("et", "Estonian", "est"),
        LanguageInfo("ee", "Ewe", "ewe"),
        LanguageInfo("fil", "Filipino", "fil"),
        LanguageInfo("fi", "Finnish", "fin"),
        LanguageInfo("fr", "French", "fra"),
        LanguageInfo("fy", "Frisian", "fry"),
        LanguageInfo("gl", "Galician", "glg"),
        LanguageInfo("ka", "Georgian", "kat"),
        LanguageInfo("de", "German", "deu"),
        LanguageInfo("el", "Greek", "ell"),
        LanguageInfo("gn", "Guarani", "grn"),
        LanguageInfo("gu", "Gujarati", "guj"),
        LanguageInfo("ht", "Haitian Creole", "hat"),
        LanguageInfo("ha", "Hausa", "hau"),
        LanguageInfo("haw", "Hawaiian", "haw"),
        LanguageInfo("he", "Hebrew", "heb"),
        LanguageInfo("hi", "Hindi", "hin"),
        LanguageInfo("hmn", "Hmong", "hmn"),
        LanguageInfo("hu", "Hungarian", "hun"),
        LanguageInfo("is", "Icelandic", "isl"),
        LanguageInfo("ig", "Igbo", "ibo"),
        LanguageInfo("ilo", "Ilocano", "ilo"),
        LanguageInfo("id", "Indonesian", "ind"),
        LanguageInfo("ga", "Irish", "gle"),
        LanguageInfo("it", "Italian", "ita"),
        LanguageInfo("ja", "Japanese", "jpn"),
        LanguageInfo("jv", "Javanese", "jav"),
        LanguageInfo("kn", "Kannada", "kan"),
        LanguageInfo("kk", "Kazakh", "kaz"),
        LanguageInfo("km", "Khmer", "khm"),
        LanguageInfo("rw", "Kinyarwanda", "kin"),
        LanguageInfo("gom", "Konkani", "kok"),
        LanguageInfo("ko", "Korean", "kor"),
        LanguageInfo("kri", "Krio", "kri"),
        LanguageInfo("kmr", "Kurdish (Kurmanji)", "kmr"),
        LanguageInfo("ckb", "Kurdish (Sorani)", "ckb"),
        LanguageInfo("ky", "Kyrgyz", "kir"),
        LanguageInfo("lo", "Lao", "lao"),
        LanguageInfo("la", "Latin", "lat"),
        LanguageInfo("lv", "Latvian", "lav"),
        LanguageInfo("ln", "Lingala", "lin"),
        LanguageInfo("lt", "Lithuanian", "lit"),
        LanguageInfo("lg", "Luganda", "lug"),
        LanguageInfo("lb", "Luxembourgish", "ltz"),
        LanguageInfo("mk", "Macedonian", "mkd"),
        LanguageInfo("mg", "Malagasy", "mlg"),
        LanguageInfo("ms", "Malay", "msa"),
        LanguageInfo("ml", "Malayalam", "mal"),
        LanguageInfo("mt", "Maltese", "mlt"),
        LanguageInfo("mi", "Maori", "mri"),
        LanguageInfo("mr", "Marathi", "mar"),
        LanguageInfo("mni-Mtei", "Meiteilon (Manipuri)", "mni-Mtei"),
        LanguageInfo("lus", "Mizo", "lus"),
        LanguageInfo("mn", "Mongolian", "mon"),
        LanguageInfo("my", "Myanmar (Burmese)", "mya"),
        LanguageInfo("ne", "Nepali", "nep"),
        LanguageInfo("no", "Norwegian", "nor"),
        LanguageInfo("or", "Odiya (Oriya)", "ori"),
        LanguageInfo("om", "Oromo", "orm"),
        LanguageInfo("ps", "Pashto", "pus"),
        LanguageInfo("fa", "Persian", "fas"),
        LanguageInfo("pl", "Polish", "pol"),
        LanguageInfo("pt", "Portuguese", "por"),
        LanguageInfo("pa", "Punjabi", "pan"),
        LanguageInfo("qu", "Quechua", "que"),
        LanguageInfo("ro", "Romanian", "ron"),
        LanguageInfo("ru", "Russian", "rus"),
        LanguageInfo("sm", "Samoan", "smo"),
        LanguageInfo("sa", "Sanskrit", "san"),
        LanguageInfo("gd", "Scots Gaelic", "gla"),
        LanguageInfo("nso", "Sepedi", "nso"),
        LanguageInfo("sr", "Serbian", "srp"),
        LanguageInfo("st", "Sesotho", "sot"),
        LanguageInfo("sn", "Shona", "sna"),
        LanguageInfo("sd", "Sindhi", "snd"),
        LanguageInfo("si", "Sinhala", "sin"),
        LanguageInfo("sk", "Slovak", "slk"),
        LanguageInfo("sl", "Slovenian", "slv"),
        LanguageInfo("so", "Somali", "som"),
        LanguageInfo("es", "Spanish", "spa"),
        LanguageInfo("su", "Sundanese", "sun"),
        LanguageInfo("sw", "Swahili", "swa"),
        LanguageInfo("sv", "Swedish", "swe"),
        LanguageInfo("tg", "Tajik", "tgk"),
        LanguageInfo("ta", "Tamil", "tam"),
        LanguageInfo("tt", "Tatar", "tat"),
        LanguageInfo("te", "Telugu", "tel"),
        LanguageInfo("th", "Thai", "tha"),
        LanguageInfo("ti", "Tigrinya", "tir"),
        LanguageInfo("ts", "Tsonga", "tso"),
        LanguageInfo("tr", "Turkish", "tur"),
        LanguageInfo("tk", "Turkmen", "tuk"),
        LanguageInfo("tw", "Twi (Akan)", "twi"),
        LanguageInfo("uk", "Ukrainian", "ukr"),
        LanguageInfo("ur", "Urdu", "urd"),
        LanguageInfo("ug", "Uyghur", "uig"),
        LanguageInfo("uz", "Uzbek", "uzb"),
        LanguageInfo("vi", "Vietnamese", "vie"),
        LanguageInfo("cy", "Welsh", "cym"),
        LanguageInfo("xh", "Xhosa", "xho"),
        LanguageInfo("yi", "Yiddish", "yid"),
        LanguageInfo("yo", "Yoruba", "yor"),
        LanguageInfo("zu", "Zulu", "zul"),
    )

    def __init__(self):
        # ----------------------------------------------------------
        # Main lookup dictionaries
        # ----------------------------------------------------------
        self._by_code = {lang.code: lang for lang in self._languages}
        self._by_name = {lang.name: lang for lang in self._languages}
        self._by_ffmpeg_code = {lang.ffmpeg_code: lang for lang in self._languages}

        # ----------------------------------------------------------
        # Backwards-compatible attributes
        # ----------------------------------------------------------
        self.list_codes = [lang.code for lang in self._languages]
        self.list_names = [lang.name for lang in self._languages]
        self.list_ffmpeg_codes = [lang.ffmpeg_code for lang in self._languages]

        self.code_of_name = {lang.name: lang.code for lang in self._languages}
        self.code_of_ffmpeg_code = {lang.ffmpeg_code: lang.code for lang in self._languages}

        self.name_of_code = {lang.code: lang.name for lang in self._languages}
        self.name_of_ffmpeg_code = {lang.ffmpeg_code: lang.name for lang in self._languages}

        self.ffmpeg_code_of_name = {lang.name: lang.ffmpeg_code for lang in self._languages}
        self.ffmpeg_code_of_code = {lang.code: lang.ffmpeg_code for lang in self._languages}

        # Legacy dictionaries
        self.dict = self.name_of_code.copy()
        self.ffmpeg_dict = self.ffmpeg_code_of_code.copy()

    # ==============================================================
    # LEGACY / BACKWARDS-COMPATIBLE API
    # ==============================================================

    def get_code_of_name(self, name: str) -> str:
        return self.code_of_name[name]

    def get_code_of_ffmpeg_code(self, ffmpeg_code: str) -> str:
        return self.code_of_ffmpeg_code[ffmpeg_code]

    def get_name_of_code(self, code: str) -> str:
        return self.name_of_code[code]

    def get_name_of_ffmpeg_code(self, ffmpeg_code: str) -> str:
        return self.name_of_ffmpeg_code[ffmpeg_code]

    def get_ffmpeg_code_of_name(self, name: str) -> str:
        return self.ffmpeg_code_of_name[name]

    def get_ffmpeg_code_of_code(self, code: str) -> str:
        return self.ffmpeg_code_of_code[code]

    # ==============================================================
    # MODERN API
    # ==============================================================

    def get(self, code: str) -> LanguageInfo:
        """Get complete language information using its language code."""
        return self._by_code[code]

    def get_by_name(self, name: str) -> LanguageInfo:
        """Get complete language information using the language name."""
        return self._by_name[name]

    def get_by_ffmpeg_code(self, ffmpeg_code: str) -> LanguageInfo:
        """Get complete language information using the FFmpeg code."""
        return self._by_ffmpeg_code[ffmpeg_code]

    def exists(self, code: str) -> bool:
        """Check whether a language code exists."""
        return code in self._by_code

    def name_exists(self, name: str) -> bool:
        """Check whether a language name exists."""
        return name in self._by_name

    def ffmpeg_code_exists(self, ffmpeg_code: str) -> bool:
        """Check whether an FFmpeg code exists."""
        return ffmpeg_code in self._by_ffmpeg_code

    def get_all(self) -> List[LanguageInfo]:
        """Return all supported languages."""
        return list(self._languages)

    def get_codes(self) -> List[str]:
        """Return all language codes."""
        return self.list_codes.copy()

    def get_names(self) -> List[str]:
        """Return all language names."""
        return self.list_names.copy()

    def get_ffmpeg_codes(self) -> List[str]:
        """Return all FFmpeg language codes."""
        return self.list_ffmpeg_codes.copy()

    def search(self, query: str) -> List[LanguageInfo]:
        """Search languages by code, name, or FFmpeg code."""
        query = query.strip().lower()
        if not query:
            return []

        return [
            lang
            for lang in self._languages
            if (
                query in lang.code.lower()
                or query in lang.name.lower()
                or query in lang.ffmpeg_code.lower()
            )
        ]

    def __contains__(self, code: str) -> bool:
        return self.exists(code)

    def __len__(self) -> int:
        return len(self._languages)

    def __iter__(self):
        return iter(self._languages)

    def __repr__(self) -> str:
        return f"Language({len(self)} languages)"


def is_same_language(
    src: str, dst: str, error_messages_callback: Optional[Callable[[Exception], None]] = None
) -> bool:
    """
    Checks if source and destination languages share the same primary language code
    (e.g., matching 'zh-CN' and 'zh-TW' as 'zh').
    """
    try:
        if not src or not dst:
            return False
        return src.split("-")[0].lower() == dst.split("-")[0].lower()
    except Exception as e:
        if error_messages_callback:
            error_messages_callback(e)
        else:
            print(f"Error checking language parity: {e}")
        return False