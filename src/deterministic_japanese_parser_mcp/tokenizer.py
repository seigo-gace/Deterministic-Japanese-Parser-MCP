import re

from .config import SETTINGS
from .models import Token
from .normalizer import span_to_original
from .open_lexicon_runtime import get_default_open_lexicon

try:
    from sudachipy import dictionary, tokenizer as sudachi_tokenizer
except ImportError:  # development fallback; production package installs SudachiPy
    dictionary = None
    sudachi_tokenizer = None


class JapaneseTokenizer:
    def __init__(self, open_lexicon=None):
        self.backend = "fallback"
        self._tok = None
        self._mode = None
        self.open_lexicon = open_lexicon or get_default_open_lexicon()
        if dictionary is not None:
            self._tok = dictionary.Dictionary(dict="core").create()
            self._mode = sudachi_tokenizer.Tokenizer.SplitMode.C
            self.backend = "sudachi-core"

    def _annotate(self, tokens: list[Token]) -> list[Token]:
        return self.open_lexicon.annotate_tokens(
            tokens,
            max_candidates=SETTINGS.max_candidates,
        )

    def tokenize(self, normalized: str, mapping, original: str) -> list[Token]:
        result: list[Token] = []
        if self._tok is not None:
            cursor = 0
            for morpheme in self._tok.tokenize(normalized, self._mode):
                surface = morpheme.surface()
                try:
                    start = morpheme.begin()
                    end = morpheme.end()
                except AttributeError:  # pragma: no cover - pinned Sudachi has offsets
                    start = normalized.find(surface, cursor)
                    if start < 0:
                        start = cursor
                    end = start + len(surface)
                cursor = end
                reading = morpheme.reading_form()
                result.append(Token(
                    surface=surface,
                    normalized=morpheme.normalized_form(),
                    reading=reading or None,
                    pos=list(morpheme.part_of_speech()),
                    span=span_to_original(start, end, mapping, original),
                ))
            return self._annotate(result)

        # Deterministic fallback for environments where the optional native
        # tokenizer is not installed. It does not claim morphological accuracy.
        for match in re.finditer(r"[一-龥々〆ヵヶぁ-んァ-ヶーA-Za-z0-9_]+|[^\s]", normalized):
            result.append(Token(
                surface=match.group(0),
                normalized=match.group(0),
                reading=None,
                pos=["unknown"],
                span=span_to_original(match.start(), match.end(), mapping, original),
            ))
        return self._annotate(result)
