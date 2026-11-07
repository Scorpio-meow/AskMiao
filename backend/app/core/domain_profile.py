from typing import Annotated, List
from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError
from app.core.config import settings
NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
class SummaryFallbackProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chat_member_noise_words: List[NonEmptyStr]
    chat_topic_keywords: List[NonEmptyStr]
    boilerplate_line_prefixes: List[NonEmptyStr]
class DomainProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    domain_words: List[NonEmptyStr]
    record_date_fields: List[NonEmptyStr]
    record_label_fields: List[NonEmptyStr]
    record_ignore_fields: List[NonEmptyStr]
    summary_fallback: SummaryFallbackProfile
def load_domain_profile(path: str) -> DomainProfile:
    try:
        with open(path, encoding="utf-8") as f:
            return DomainProfile.model_validate_json(f.read())
    except FileNotFoundError as e:
        raise RuntimeError(f"找不到 DOMAIN_PROFILE_PATH 指定的領域設定檔：{path}") from e
    except ValidationError as e:
        raise RuntimeError(f"領域設定檔 {path} 格式錯誤：{e}") from e
domain_profile = load_domain_profile(settings.DOMAIN_PROFILE_PATH)