import json
from pathlib import Path

import pytest

from app.core.config import settings
from app.core.domain_profile import load_domain_profile


def test_shipped_profile_is_valid_without_duplicate_domain_words():
    profile = load_domain_profile(settings.DOMAIN_PROFILE_PATH)

    assert profile.domain_words
    assert len(profile.domain_words) == len(set(profile.domain_words))
    assert profile.record_date_fields == ["timestamp", "timestampTitle"]
    assert profile.record_label_fields == ["title", "name", "author", "id"]
    assert "embedcode" in profile.record_ignore_fields


def test_profile_with_missing_field_is_rejected(tmp_path):
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({"domain_words": ["特休"], "record_date_fields": ["timestamp"]}), encoding="utf-8")

    with pytest.raises(RuntimeError, match="summary_fallback"):
        load_domain_profile(str(path))


def test_profile_with_unknown_field_is_rejected(tmp_path):
    shipped = json.loads(Path(settings.DOMAIN_PROFILE_PATH).read_text(encoding="utf-8"))
    path = tmp_path / "profile.json"
    path.write_text(json.dumps({**shipped, "faq_keywords": ["特休"]}, ensure_ascii=False), encoding="utf-8")

    with pytest.raises(RuntimeError, match="faq_keywords"):
        load_domain_profile(str(path))


def test_missing_profile_file_is_reported(tmp_path):
    with pytest.raises(RuntimeError, match="DOMAIN_PROFILE_PATH"):
        load_domain_profile(str(tmp_path / "missing.json"))
