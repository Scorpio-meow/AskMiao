from typing import Dict, Optional, Sequence
import hashlib
import logging
import os
import re
from app.core.config import settings
logger = logging.getLogger(__name__)
JIEBA_CACHE_DIR = os.path.join(settings.DATA_DIR, "jieba_cache")
try:
    from whoosh.analysis import StandardAnalyzer, Analyzer, Tokenizer, Token
    HAS_WHOOSH = True
except ImportError:
    HAS_WHOOSH = False
    Analyzer = object
    Tokenizer = object
    Token = None
    StandardAnalyzer = None
try:
    import jieba
    HAS_JIEBA = True
except Exception:
    HAS_JIEBA = False
TOKENIZER_RULES_VERSION = 3
HAN_RUN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]+")
_jieba_tokenizer = None
_configured_with = None
_signature: Optional[Dict[str, object]] = None
def configure_tokenizer(dictionary_path: Optional[str], domain_words: Sequence[str]) -> None:
    global _jieba_tokenizer, _configured_with, _signature
    words = list(dict.fromkeys(domain_words))
    if _configured_with == (dictionary_path, tuple(words)):
        return
    if not HAS_JIEBA:
        _signature = {"rules_version": TOKENIZER_RULES_VERSION, "analyzer": "standard"}
        _configured_with = (dictionary_path, tuple(words))
        return
    if dictionary_path is not None and not os.path.isfile(dictionary_path):
        raise FileNotFoundError(f"找不到 JIEBA_DICTIONARY 指定的詞典檔：{dictionary_path}")
    tokenizer = jieba.Tokenizer(dictionary_path) if dictionary_path else jieba.Tokenizer()
    os.makedirs(JIEBA_CACHE_DIR, mode=0o700, exist_ok=True)
    tokenizer.tmp_dir = JIEBA_CACHE_DIR
    tokenizer.initialize()
    for word in words:
        tokenizer.add_word(word)
    with tokenizer.get_dict_file() as f:
        dictionary_sha256 = hashlib.sha256(f.read()).hexdigest()
    _jieba_tokenizer = tokenizer
    _configured_with = (dictionary_path, tuple(words))
    _signature = {
        "rules_version": TOKENIZER_RULES_VERSION,
        "analyzer": "jieba",
        "dictionary_sha256": dictionary_sha256,
        "domain_words_sha256": hashlib.sha256("\n".join(words).encode("utf-8")).hexdigest(),
    }
    logger.info(f"jieba 斷詞器已設定：主詞典 {dictionary_path or 'jieba 內建詞典'}，領域詞 {len(words)} 個")
def tokenizer_signature() -> Dict[str, object]:
    if _signature is None:
        raise RuntimeError("斷詞器尚未設定，請先呼叫 configure_tokenizer")
    return _signature
def _cut(text: str):
    if _jieba_tokenizer is None:
        raise RuntimeError("斷詞器尚未設定，請先呼叫 configure_tokenizer")
    return _jieba_tokenizer.cut(text, cut_all=False)
if HAS_WHOOSH and HAS_JIEBA:
    class JiebaTokenizer(Tokenizer):
        def __call__(
            self,
            value,
            positions=False,
            chars=False,
            keeporiginal=False,
            removestops=False,
            start_pos=0,
            start_char=0,
            tokenize=True,
            mode="default",
            **kwargs
        ):
            t = Token(positions, chars, removestops=removestops)
            if not tokenize:
                return
            if isinstance(value, bytes):
                try:
                    value = value.decode("utf-8", "ignore")
                except Exception:
                    value = value.decode(errors="ignore")
            pos = start_pos
            char_pos = start_char
            for w in _cut(value):
                w = w.strip()
                if not any(ch.isalnum() for ch in w):
                    continue
                t.original = w
                t.text = w.lower()
                t.boost = 1.0
                if positions:
                    t.pos = pos
                    pos += 1
                if chars:
                    idx = value.find(w, char_pos)
                    if idx < 0:
                        idx = char_pos
                    t.startchar = idx
                    t.endchar = idx + len(w)
                    char_pos = t.endchar
                yield t
    class JiebaAnalyzer(Analyzer):
        def __init__(self):
            self._tokenizer = JiebaTokenizer()
        def __call__(self, value, **kwargs):
            return self._tokenizer(value, **kwargs)
else:
    JiebaTokenizer = None
    JiebaAnalyzer = None
if HAS_WHOOSH:
    class HanNgramTokenizer(Tokenizer):
        def __init__(self, size: int):
            self.size = size
        def __call__(
            self,
            value,
            positions=False,
            chars=False,
            keeporiginal=False,
            removestops=False,
            start_pos=0,
            start_char=0,
            tokenize=True,
            mode="default",
            **kwargs
        ):
            t = Token(positions, chars, removestops=removestops)
            if not tokenize:
                return
            if isinstance(value, bytes):
                value = value.decode("utf-8", "ignore")
            pos = start_pos
            for run in HAN_RUN.finditer(value):
                for start in range(run.start(), run.end() - self.size + 1):
                    t.original = t.text = value[start:start + self.size]
                    t.boost = 1.0
                    if positions:
                        t.pos = pos
                        pos += 1
                    if chars:
                        t.startchar = start_char + start
                        t.endchar = start_char + start + self.size
                    yield t
    class HanNgramAnalyzer(Analyzer):
        def __init__(self, size: int):
            self._tokenizer = HanNgramTokenizer(size)
        def __call__(self, value, **kwargs):
            return self._tokenizer(value, **kwargs)
else:
    HanNgramTokenizer = None
    HanNgramAnalyzer = None
def get_chinese_analyzer():
    if not HAS_WHOOSH:
        return None
    if HAS_JIEBA:
        return JiebaAnalyzer()
    return StandardAnalyzer()
def get_han_ngram_analyzer(size: int):
    if not HAS_WHOOSH:
        return None
    return HanNgramAnalyzer(size)