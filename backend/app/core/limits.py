"""資源上限的集中定義。

這些是保護單一後端行程可用性與操作者付費用量的安全上限，不是部署偏好設定；
調整時請同步更新 docs/configuration.md 的「資源上限」一節。
"""

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
MAX_TEXT_CLEANUP_CHARS = 2_000_000

# 工具結果放進模型脈絡前的長度上限（每次工具呼叫）
MAX_TOOL_RESULT_CHARS = 20_000

# 帳號與密碼：Argon2 的成本隨密碼長度成長，登入欄位也會寫進安全日誌
MAX_PASSWORD_CHARS = 256
MAX_LOGIN_IDENTIFIER_CHARS = 254
# 同時進行的 Argon2 雜湊／驗證數
MAX_CONCURRENT_PASSWORD_HASHES = 4

# 行程內權杖撤銷名單的條目上限；滿了以後先淘汰最早到期的條目
MAX_REVOKED_TOKENS = 100_000

# 日誌：單一欄位長度、檔案輪替大小與保留份數
MAX_LOG_FIELD_CHARS = 200
LOG_FILE_MAX_BYTES = 10 * MIB
LOG_FILE_BACKUP_COUNT = 5

# 入侵偵測：每個位址保留的事件數與追蹤的位址數
MAX_EVENTS_PER_ADDRESS = 200
MAX_TRACKED_ADDRESSES = 10_000
