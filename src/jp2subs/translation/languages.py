"""Target languages, with the code each engine expects.

Keys are the codes jp2subs uses in ``Segment.translations`` and in output file
names (``subs_pt-BR.srt``). NLLB uses FLORES-200 codes; DeepL uses its own.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    #: FLORES-200 code used by the offline NLLB model.
    nllb: str
    #: DeepL target code, empty when DeepL does not offer the language.
    deepl: str = ""

    @property
    def label(self) -> str:
        return f"{self.name} ({self.code})"


SOURCE = Language(code="ja", name="Japanese", nllb="jpn_Jpan", deepl="JA")

LANGUAGES: tuple[Language, ...] = (
    Language("en", "English", "eng_Latn", "EN-US"),
    Language("pt-BR", "Portuguese (Brazil)", "por_Latn", "PT-BR"),
    Language("pt", "Portuguese (Europe)", "por_Latn", "PT-PT"),
    Language("es", "Spanish", "spa_Latn", "ES"),
    Language("fr", "French", "fra_Latn", "FR"),
    Language("de", "German", "deu_Latn", "DE"),
    Language("it", "Italian", "ita_Latn", "IT"),
    Language("nl", "Dutch", "nld_Latn", "NL"),
    Language("pl", "Polish", "pol_Latn", "PL"),
    Language("ru", "Russian", "rus_Cyrl", "RU"),
    Language("uk", "Ukrainian", "ukr_Cyrl", "UK"),
    Language("cs", "Czech", "ces_Latn", "CS"),
    Language("sv", "Swedish", "swe_Latn", "SV"),
    Language("da", "Danish", "dan_Latn", "DA"),
    Language("fi", "Finnish", "fin_Latn", "FI"),
    Language("nb", "Norwegian", "nob_Latn", "NB"),
    Language("el", "Greek", "ell_Grek", "EL"),
    Language("hu", "Hungarian", "hun_Latn", "HU"),
    Language("ro", "Romanian", "ron_Latn", "RO"),
    Language("tr", "Turkish", "tur_Latn", "TR"),
    Language("ar", "Arabic", "arb_Arab", "AR"),
    Language("he", "Hebrew", "heb_Hebr", ""),
    Language("hi", "Hindi", "hin_Deva", ""),
    Language("th", "Thai", "tha_Thai", ""),
    Language("vi", "Vietnamese", "vie_Latn", ""),
    Language("id", "Indonesian", "ind_Latn", "ID"),
    Language("ms", "Malay", "zsm_Latn", ""),
    Language("fil", "Filipino", "tgl_Latn", ""),
    Language("ko", "Korean", "kor_Hang", "KO"),
    Language("zh-Hans", "Chinese (Simplified)", "zho_Hans", "ZH"),
    Language("zh-Hant", "Chinese (Traditional)", "zho_Hant", ""),
    Language("ja", "Japanese", "jpn_Jpan", "JA"),
)

_BY_CODE = {item.code.lower(): item for item in LANGUAGES}


def get(code: str) -> Language | None:
    """Look a language up by code, tolerating case and underscores."""

    if not code:
        return None
    normalized = code.strip().lower().replace("_", "-")
    found = _BY_CODE.get(normalized)
    if found:
        return found
    # Accept a bare 'zh' or 'pt' style code by falling back to the first variant.
    base = normalized.split("-", 1)[0]
    for item in LANGUAGES:
        if item.code.lower().split("-", 1)[0] == base:
            return item
    return None


def resolve_many(codes) -> list[Language]:
    """Map a list of codes to languages, skipping anything unrecognised."""

    resolved: list[Language] = []
    for code in codes or []:
        language = get(str(code))
        if language and language.code not in {item.code for item in resolved}:
            resolved.append(language)
    return resolved


def deepl_supported() -> tuple[Language, ...]:
    return tuple(item for item in LANGUAGES if item.deepl)
