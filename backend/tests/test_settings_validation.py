from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import BACKEND_DIR, Settings


def test_relative_paths_resolve_against_backend_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    configured = Settings(
        DATA_DIR="data",
        UPLOAD_DIR="data/uploads",
        FAISS_INDEX_PATH="data/faiss_index.bin",
        HF_HOME="./data/hf_home",
        DOMAIN_PROFILE_PATH="config/domain_profile.json",
        JIEBA_DICTIONARY="data/jieba/dict.txt.big",
    )

    assert configured.DATA_DIR == str(BACKEND_DIR / "data")
    assert configured.UPLOAD_DIR == str(BACKEND_DIR / "data" / "uploads")
    assert configured.FAISS_INDEX_PATH == str(BACKEND_DIR / "data" / "faiss_index.bin")
    assert configured.HF_HOME == str(BACKEND_DIR / "data" / "hf_home")
    assert configured.DOMAIN_PROFILE_PATH == str(BACKEND_DIR / "config" / "domain_profile.json")
    assert configured.JIEBA_DICTIONARY == str(BACKEND_DIR / "data" / "jieba" / "dict.txt.big")


def test_absolute_paths_and_unset_optional_paths_are_kept(tmp_path):
    configured = Settings(DATA_DIR=str(tmp_path), JIEBA_DICTIONARY=None)

    assert Path(configured.DATA_DIR) == tmp_path
    assert configured.JIEBA_DICTIONARY is None


def test_web_fetch_allowed_domains_are_normalized():
    configured = Settings(WEB_FETCH_ALLOWED_DOMAINS=" Example.com , docs.gov.tw ")

    assert configured.web_fetch_allowed_domains == ["example.com", "docs.gov.tw"]


@pytest.mark.parametrize("value", ["", " , ", "*,example.com", "https://example.com", "example.com/path"])
def test_web_fetch_allowed_domains_rejects_ambiguous_values(value):
    with pytest.raises(ValidationError, match="WEB_FETCH_ALLOWED_DOMAINS"):
        Settings(WEB_FETCH_ALLOWED_DOMAINS=value)
