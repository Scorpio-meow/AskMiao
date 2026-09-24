from typing import Annotated, List

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from app.core.config import settings

NonEmptyStr = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class SummaryFallbackProfile(BaseModel):
    """文件摘要備援規則（LLM 摘要失敗時的啟發式規則）"""
    model_config = ConfigDict(extra="forbid")

    # 通訊紀錄中被誤認為成員名稱的雜訊詞
    chat_member_noise_words: List[NonEmptyStr]
    # 通訊紀錄摘要要偵測的主題詞
    chat_topic_keywords: List[NonEmptyStr]
    # 以這些字首開頭（不分大小寫）的行視為頁尾、版權等雜訊
    boilerplate_line_prefixes: List[NonEmptyStr]


class DomainProfile(BaseModel):
    """部署領域專屬資料：領域詞、結構化記錄的日期欄位與摘要備援規則"""
    model_config = ConfigDict(extra="forbid")

    # 加入 jieba 詞典的領域詞
    domain_words: List[NonEmptyStr]
    # 結構化記錄中代表發布日期的欄位名稱（內容格式為「欄位: 日期」）
    record_date_fields: List[NonEmptyStr]
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
