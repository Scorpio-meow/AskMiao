"""資源上限的集中定義。

這些是保護單一後端行程可用性與操作者付費用量的安全上限，不是部署偏好設定；
調整時請同步更新 docs/configuration.md 的「資源上限」一節。
"""
from dataclasses import dataclass
from typing import Optional

MIB = 1024 * 1024

# 未帶有效存取權杖的請求、以及一般 API 請求的本文上限
MAX_REQUEST_BODY_BYTES = 1 * MIB

# 聊天訊息與附件
MAX_CHAT_MESSAGE_CHARS = 20_000
MAX_CHAT_ATTACHMENTS = 5
# 單一附件解碼後的大小；前端只把 15 MiB 以下的檔案讀成 data URL
MAX_CHAT_ATTACHMENT_BYTES = 15 * MIB
MAX_CHAT_ATTACHMENTS_TOTAL_BYTES = 20 * MIB
# base64 膨脹 4/3，再加上訊息本文與 JSON 結構的餘裕
MAX_CHAT_REQUEST_BODY_BYTES = (MAX_CHAT_ATTACHMENTS_TOTAL_BYTES * 4) // 3 + 1 * MIB
# 附件抽出的文字放進模型脈絡前的長度上限（每個附件）
MAX_ATTACHMENT_TEXT_CHARS = 50_000
# 每位使用者保存在資料庫的附件總量
MAX_USER_ATTACHMENT_STORAGE_BYTES = 200 * MIB
# 每位使用者同時進行中的聊天串流數
MAX_CONCURRENT_CHAT_STREAMS_PER_USER = 2

# 管理員文件上傳
MAX_FILES_PER_UPLOAD = 10

# 文件解析
MAX_PDF_OCR_PAGES = 20
MAX_OCR_PIXELS = 25_000_000
MAX_OOXML_UNCOMPRESSED_BYTES = 200 * MIB
MAX_OOXML_COMPRESSION_RATIO = 100
# 解壓後超過此大小的單一成員或整個 OOXML 檔案才檢查壓縮比：一般 XML 本來就能壓縮很多倍
OOXML_RATIO_CHECK_MIN_BYTES = 10 * MIB
# OOXML（ZIP）的成員數：python-docx／python-pptx 會替每個可達的部件建立物件與 DOM
MAX_OOXML_MEMBERS = 10_000
MAX_TEXT_CLEANUP_CHARS = 2_000_000

# 聊天附件的解析預算：任何登入的使用者都能送出附件，而附件文字最後只取 MAX_ATTACHMENT_TEXT_CHARS 字
MAX_ATTACHMENT_OOXML_UNCOMPRESSED_BYTES = 64 * MIB
# python-docx／python-pptx 會把 XML 部件整份建成 lxml DOM，記憶體約為 XML 大小的 15～30 倍
MAX_ATTACHMENT_OOXML_XML_BYTES = 8 * MIB
# 交給 json.loads 做結構化降噪的附件文字長度；更長的附件只做線性的雜訊清除
MAX_ATTACHMENT_STRUCTURED_PARSE_CHARS = 2_000_000
# 整個行程同時進行的附件解析數；與上面的單檔預算相乘即為附件解析的記憶體上界
MAX_CONCURRENT_ATTACHMENT_EXTRACTIONS = 2


@dataclass(frozen=True)
class ExtractionLimits:
    """文件文字抽取的資源預算：管理員上傳與聊天附件各用一組"""
    # 最多送 Vision OCR 的 PDF 頁數；None 表示不限
    max_ocr_pages: Optional[int]
    # OOXML 成員宣告的解壓總量與成員數
    max_ooxml_uncompressed_bytes: int
    max_ooxml_members: int
    # docx／pptx 會被整份建成 DOM 的 XML 部件總量（依 [Content_Types].xml 判定，另含 .rels）
    max_ooxml_xml_bytes: int
    # 交給 json.loads 的文字長度；None 表示不限
    max_structured_parse_chars: Optional[int]


# 管理員上傳的知識庫文件：來源可信，維持原本的上限
ADMIN_UPLOAD_EXTRACTION_LIMITS = ExtractionLimits(
    max_ocr_pages=None,
    max_ooxml_uncompressed_bytes=MAX_OOXML_UNCOMPRESSED_BYTES,
    max_ooxml_members=MAX_OOXML_MEMBERS,
    max_ooxml_xml_bytes=MAX_OOXML_UNCOMPRESSED_BYTES,
    max_structured_parse_chars=None,
)
CHAT_ATTACHMENT_EXTRACTION_LIMITS = ExtractionLimits(
    max_ocr_pages=MAX_PDF_OCR_PAGES,
    max_ooxml_uncompressed_bytes=MAX_ATTACHMENT_OOXML_UNCOMPRESSED_BYTES,
    max_ooxml_members=MAX_OOXML_MEMBERS,
    max_ooxml_xml_bytes=MAX_ATTACHMENT_OOXML_XML_BYTES,
    max_structured_parse_chars=MAX_ATTACHMENT_STRUCTURED_PARSE_CHARS,
)

# 工具結果放進模型脈絡前的長度上限（每次工具呼叫）
MAX_TOOL_RESULT_CHARS = 20_000

# 帳號與密碼：Argon2 的成本隨密碼長度成長，登入欄位也會寫進安全日誌
MAX_PASSWORD_CHARS = 256
MAX_LOGIN_IDENTIFIER_CHARS = 254
# 同時進行的 Argon2 雜湊／驗證數
MAX_CONCURRENT_PASSWORD_HASHES = 4
# 登入失敗節流追蹤的登入識別數（來源位址數沿用 MAX_TRACKED_ADDRESSES），最久未活動的先淘汰
MAX_TRACKED_LOGIN_ACCOUNTS = 10_000

# 行程內權杖撤銷名單的條目上限；滿了以後先淘汰最早到期的條目
MAX_REVOKED_TOKENS = 100_000

# 日誌：單一欄位長度、檔案輪替大小與保留份數
MAX_LOG_FIELD_CHARS = 200
LOG_FILE_MAX_BYTES = 10 * MIB
LOG_FILE_BACKUP_COUNT = 5

# 入侵偵測：每個位址保留的事件數與追蹤的位址數
MAX_EVENTS_PER_ADDRESS = 200
MAX_TRACKED_ADDRESSES = 10_000
