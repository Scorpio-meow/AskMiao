# Changelog

[繁體中文](CHANGELOG.md) | [English](CHANGELOG_en.md)

All notable changes to AskMiao are documented in this file. The format is based on [Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning 2.0.0](https://semver.org/spec/v2.0.0.html): incompatible changes bump the major version, backward-compatible features bump the minor version, and bug fixes bump the patch version.

| Version | Release date | Highlights |
|---|---|---|
| [8.13.0](#8130---2026-11-13) | 2026-11-13 | Answer-level evaluation; research mode searches the knowledge base at most 6 times per question, so questions with no answer no longer take minutes; knowledge-base results carry the neighbouring text, so the model can read articles and tables that chunking cut apart |
| [8.12.2](#8122---2026-11-11) | 2026-11-11 | The research assistant always searches the knowledge base before answering, instead of relying only on AI document outlines and summaries or on attached images |
| [8.12.1](#8121---2026-11-11) | 2026-11-11 | The conversation column widens with the window on wide screens (48rem to 72rem); the input box and the no-model notice match its width |
| [8.12.0](#8120---2026-11-10) | 2026-11-10 | Web page previews fill the panel and gain a desktop layout, a source tab, and reload; when a link cannot open, one click returns to the page |
| [8.11.0](#8110---2026-11-10) | 2026-11-10 | The `[n]` marks in the answer text can be clicked to open the same preview card as the source list |
| [8.10.0](#8100---2026-11-10) | 2026-11-10 | A 「上網」 (web) switch beside the input box lets users decide per question whether the assistant may go online; with it on, a knowledge-base miss is followed by a web search |
| [8.9.1](#891---2026-11-10) | 2026-11-10 | Model calls are read as streams, so long answers and long tool calls no longer time out; a failed model call or an empty answer is reported to the user; `/skill-name` is no longer affected by the skill catalog length limit |
| [8.9.0](#890---2026-11-09) | 2026-11-09 | Organization and personal long-term instructions; approvals can cover the rest of a question; agent mode can hand sub-tasks to parallel subagents |
| [8.8.0](#880---2026-11-09) | 2026-11-09 | Agent mode can ask the user and wait for the answer; the research trace shows a progress note for each step; file create and edit results carry a structure check |
| [8.7.0](#870---2026-11-09) | 2026-11-09 | Agent mode: the chat page switches between research and agent mode; agent mode lists a plan, works through it, and reads its files back, with the plan shown as a checklist; at most 30 model calls, and old tool results are cleared once they exceed a budget |
| [8.6.0](#860---2026-11-09) | 2026-11-09 | Model output limits looked up automatically: Claude connections to Anthropic may leave the output token limit empty, and a vLLM output token limit above the model's context length no longer stops research |
| [8.5.1](#851---2026-11-09) | 2026-11-09 | `deploy/gen-env.sh` adds the missing line break to `deploy/.env`, so the backend of a new deployment starts |
| [8.5.0](#850---2026-11-09) | 2026-11-09 | File preview: conversation files and knowledge base documents can be previewed without downloading (PDF pages as images; Word, Excel, and PowerPoint as web pages); the research assistant can build web pages that are previewed in an isolated iframe; cited web pages first show a preview card |
| [8.4.0](#840---2026-11-08) | 2026-11-08 | Conversation files: the research assistant creates, reads, edits (as new versions), and deletes Word, Excel, PowerPoint, PDF, and other files in a conversation, with user approval before any deletion; document attachments are stored as conversation files and can be downloaded again; the research assistant knows the current date and time |
| [8.3.0](#830---2026-11-08) | 2026-11-08 | vLLM provider, prompts sent to the model collected in `prompts.py` and rewritten after an audit, tool descriptions matched to the code, fixed tool list order |
| [8.2.2](#822---2026-11-07) | 2026-11-07 | How document upload rejection reasons are returned; no user-visible change |
| [8.2.1](#821---2026-11-07) | 2026-11-07 | Claude output token limit error messages point to the API connection; documentation checked against the code and reorganized, with a new deployment guide and troubleshooting page |
| [8.2.0](#820---2026-11-07) | 2026-11-07 | Agent Skills uploaded straight from a folder, several skills at once; skill uploads reject paths with a colon; installing skills no longer blocks other requests |
| [8.1.0](#810---2026-11-03) | 2026-11-03 | MCP 2026-07-28 (stateless requests, `server/discover`, standard and `x-mcp-header` headers) with legacy servers still supported, MCP OAuth hardened to the new authorization specification (`iss` checks, required PKCE, Client ID Metadata Documents, step-up authorization), and binary content in MCP tool results kept from the model |
| [8.0.2](#802---2026-11-02) | 2026-11-02 | How tests strip HTML tags; no user-visible change |
| [8.0.1](#801---2026-11-02) | 2026-11-02 | pypdf upgraded to 6.21.4, fixing infinite loops and heavy memory use from malicious PDFs |
| [8.0.0](#800---2026-11-02) | 2026-11-02 | Admin-chosen system models replace the provider settings in `.env`, OpenAPI 3.2 with Arazzo workflows and Overlay, Han unigram and bigram BM25 fields with a chunk-level retrieval benchmark, OpenVINO reranking sized to the actual candidates, request IDs and detailed logs, redesigned AI tools and chat pages, web search and web reading fixes |
| [7.0.0](#700---2026-10-31) | 2026-10-31 | Per-account API connections and admin-granted shared connections, user management, token revocation on deactivation, per-hop redirect checks for tools and the web allowlist, Docker Compose deployment for a VM, FAQ and PDF extraction fixes, and index rebuilds that no longer empty the knowledge base |
| [6.0.0](#600---2026-10-26) | 2026-10-26 | Agent Skills, MCP Streamable HTTP and OAuth, re-parsed structured data, the Responses API, Microsoft Foundry (including Claude), reasoning effort mapped across five providers, and Ollama and Gemini integration fixes |
| [5.0.0](#500---2026-10-10) | 2026-10-10 | Second security audit fixes: login failure throttling, token revocation on password change, optional self-registration, encrypted tool credentials, PyJWT in place of python-jose, hash-pinned dependencies, a non-superuser PostgreSQL account |
| [4.0.0](#400---2026-09-27) | 2026-09-27 | Security audit fixes: tokens bound to database accounts, user approval for tool calls, IP-pinned outbound connections, resource limits |
| [3.0.0](#300---2026-09-25) | 2026-09-25 | chunk_id index, RRF with a relevance threshold, answer citations, tool trust boundary and admin-only tool management, frontend UI/UX overhaul |
| [2.2.1](#221---2026-09-19) | 2026-09-19 | Error responses use error codes |
| [2.2.0](#220---2026-09-01) | 2026-09-01 | Centralized SSRF protection |
| [2.1.0](#210---2026-08-27) | 2026-08-27 | Custom API tools, OpenAPI import, and MCP integration |
| [2.0.1](#201---2026-08-26) | 2026-08-26 | Multimodal chat and AI document summaries |
| [2.0.0](#200---2026-08-24) | 2026-08-24 | Agentic RAG autonomous research |
| [1.0.0](#100---2026-08-01) | 2026-08-01 | Hybrid RAG and security foundations |

> [!TIP]
> When upgrading across major versions, follow each release's steps in the [upgrade guide](docs/upgrading_en.md) in order. What needs manual work in each:
>
> - [7.0.0 → 8.0.0](docs/upgrading_en.md#upgrading-from-700-to-800): `.env` gains the required `LOG_DIR`; the provider settings are removed from `.env`, and document summaries and OCR of scanned PDFs use the shared connections chosen under "Admin → System models" (both are "not set" after upgrading); `GET /api/tags` is replaced by `GET /api/chat/models`.
> - [6.0.0 → 7.0.0](docs/upgrading_en.md#upgrading-from-600-to-700): chat uses each account's API connections, so every account (admins included) needs a personal connection or a shared connection opened to it; `POST /api/chat/send` must include `connection_id` and `model_name`; `PUT /api/auth/me` no longer changes passwords.
> - [5.0.0 → 6.0.0](docs/upgrading_en.md#upgrading-from-500-to-600): `.env` gains the required `SKILLS_DIR`, the domain profile gains two required fields, and the Azure OpenAI settings are renamed to Microsoft Foundry.
> - [4.0.0 → 5.0.0](docs/upgrading_en.md#upgrading-from-400-to-500): `.env` gains 10 required settings (including `TOOL_SECRETS_KEY`, which each deployment generates), the compose PostgreSQL is accessed through a non-superuser account, and the backend packages are reinstalled from the new `requirements.txt`.
> - Earlier releases: [3.0.0 → 4.0.0](docs/upgrading_en.md#upgrading-from-300-to-400) (RSA keys become mandatory, compose needs `POSTGRES_PASSWORD`) and [2.x → 3.0.0](docs/upgrading_en.md#upgrading-from-2x-to-300).

---

## [Unreleased]

## [8.13.0] - 2026-11-13

### Added

- **Answer-level evaluation**: `scripts/evaluate_answers.py` and `app/rag/answer_evaluator.py` run the full research loop with a given real model and grade the final answers rather than only the retrieval results. Each answer is graded on four things: answer facts (a number must not run into other digits, so "500" does not match "5,500"), whether the citations include a correct document, whether the knowledge base was searched, and a judge model (required, because only the judge can grade negative questions). The judge gets the full text of the correct passages and of the chunks the answer cites. Each question can be repeated, and the report lists pass rates by question kind, failure reasons, and per-question stability. The bundled set `backend/eval/answer_golden.jsonl` has 136 questions: all 118 retrieval benchmark questions, plus calculations, comparisons, multi-document questions, false premises, counting, abbreviations, and negative questions that invite answers from general knowledge. See [ADR-0008](docs/adr/0008-answer-level-evaluation-and-search-guards_en.md) for the design and measurements.

### Changed

- **Neighbouring text in knowledge-base results**: chunks of text documents returned by `search_knowledge_base` also carry `context_before` and `context_after`, the text right before and after them in the same document with the overlap removed. The model can now connect a fine stated at the start of an article with an offence listed in the next chunk, or the halves of a table that the split cut apart; citation numbers still point at the matched chunk. Structured records and Q&A chunks kept whole do not get them.
- **Knowledge-base search limit in research mode**: each question may call the knowledge-base tools at most 6 times (`MAX_RESEARCH_KNOWLEDGE_SEARCHES`), and a call with the same arguments as an earlier one is not run again but still counts; the code blocks these calls, and once the budget is spent the loop has the model answer from what it has without calling more tools. A search that fails to run may be retried with the same arguments. Questions the knowledge base cannot answer used to be re-queried with single characters, up to 31 searches and 5 minutes; questions it can answer never needed more than 4 searches and are unaffected. Agent mode has no limit.
- **Prompts**: when nothing is found, search again once or twice with wording the documents may use (full names, formal terms, Chinese) and then say plainly that nothing was found; this rule is in both the system prompt and the tool description. When the knowledge base has nothing on the item asked about, say so first, and related rules may be added but not presented as that item. Answers no longer end with a self-made list of sources. The keyword description of `filter_and_count_records` reminds the model to write the full "field: value" when counting by a field, because the value alone also counts records where another field happens to contain it.
- **`query` is required for `search_knowledge_base`**: a blank query returns an error instead of searching for an empty string.

## [8.12.2] - 2026-11-11

### Fixed

- **Search the source before answering**: the AI outlines and summaries in the knowledge base catalog are now marked as only for choosing which document to search, not as an answer source; the system prompts for both research and agent modes require retrieving source passages before answering, so the assistant no longer answers from catalog summaries without citations.
- **Attachments do not replace the knowledge base**: when an attached image or file names a case, project, department, or document, the assistant searches the knowledge base with those names and treats the knowledge base as the primary source and the attachment as secondary.

## [8.12.1] - 2026-11-11

### Changed

- **Conversation width follows the window**: the maximum width of the conversation, the input box, and the "no model configured" notice changes from a fixed 48rem to 85% of the chat area width, between 48rem and 72rem, so wide screens fit more text per line.

### Fixed

- **Attachment name clamping**: the two-line clamp of attachment names in the input box adds the standard `line-clamp` property instead of relying only on `-webkit-line-clamp`.

## [8.12.0] - 2026-11-10

### Added

- **Desktop layout for web page previews**: when previewing a web page file (`.html`), the "電腦版面" (desktop layout) switch in the toolbar lays the page out 1,280 pixels wide and shrinks it to the panel width, so a narrow panel still shows the layout a desktop browser would. It grows as the panel is dragged wider or expanded; panels wider than 1,280 pixels are not scaled.
- **Source tab for web page previews**: the preview has two tabs, "預覽" (preview) and "原始碼" (source); switching does not reload the page. `GET /api/chat/files/{file_id}/preview` now also returns `text` (up to 200,000 characters) and `truncated` for web page files; the source is read as UTF-8, the same bytes the preview frame receives.
- **Reload and back to the page**: the toolbar has a "重新載入" (reload) button. When a page links to another file or an external site, the preview cannot show the target; it now shows a notice with a "回到網頁" (back to the page) button, so there is no need to close and reopen the preview.

### Changed

- **Web page previews fill the panel**: the page no longer has padding and a border around it and takes the whole preview panel; while loading it shows "載入網頁…".
- **Tool description for creating web pages**: `CREATE_FILE` tells the research assistant to keep multiple pages in one file (switching with in-page anchors or JavaScript) and not to use `localStorage`, `sessionStorage`, or cookies, because in the isolated preview links to other files do not open and reading or writing that storage throws.

## [8.11.0] - 2026-11-10

### Added

- **Previews for inline citations**: the `[n]` marks in the answer text become small numbered buttons that open the same preview card as the source list: web sources show the title, site name, snippet, and "Open web page", and knowledge-base sources show the paragraph, relevance, and snippet; Esc closes the card. Adjacent marks such as `[2][5]` are separate buttons. `[n]` inside code or link text, numbers missing from the source list, and marks shown while the answer is still streaming and the sources have not arrived stay as plain text.

## [8.10.0] - 2026-11-10

### Added

- **「上網」 (web) switch**: the chat input box gains a 「上網」 switch to the right of the upload button, so users decide per question whether the research assistant may search the web and read web pages. It is on by default and the choice is remembered in the browser; when it is off, the web tools are not offered to the model, calls to them are refused anyway (subagents included), and the system prompt tells the model the user turned the web off and should be asked to turn it on when web data is needed. The switch is hidden when the server has `ENABLE_WEB_SEARCH=false`. `POST /api/chat/send` takes an optional `allow_web` (default `true`), and `GET /api/chat/models` also returns `web_search_enabled`.

### Changed

- **A knowledge-base miss is followed by a web search**: the answer rules used to say that a 「查無相關資料」 ("no relevant data") result from the knowledge base must be reported as not found, so the research assistant stopped after the knowledge base and asked whether to search the web. Now, with the web allowed, when the knowledge base has nothing and the question may be about public information (external products, open-source projects, technical terms, current events), it searches the web next and says it found nothing only when the web has nothing either.

## [8.9.1] - 2026-11-10

### Fixed

- **Long answers and long tool calls no longer time out**: each research round used to call the model without streaming, so `LLM_TIMEOUT` (120 seconds by default) limited the whole answer; when agent mode wrote a whole web page in one tool call, the call timed out while the model was still writing and the answer stopped after its first step. Model calls to every provider are now read as streams, and the full message is rebuilt from the text, reasoning, and tool-call arguments as they arrive in pieces, so `LLM_TIMEOUT` is now the longest wait to connect or between two pieces of data. OpenAI streams also report token usage, and an error received in the middle of a stream is raised instead of becoming an empty answer.
- **Research no longer ends without a word**: when a model call failed after the research trace already had steps, the error only went to the log, and if the regenerated answer was empty the page just showed 「AI 已完成回答」 ("the AI has finished answering"). The model is now told to stop calling tools and answer from what it has gathered, and the answer ends with the error code; when the model returns empty content it is asked the same way, and if there is still no text the answer says 「模型沒有產生回答內容」 ("the model produced no answer").
- **A skill named with `/skill-name` pushed out of the skill catalog**: with enough enabled skills to pass `MAX_SKILL_CATALOG_CHARS` (8,000 characters), a skill that did not fit was ignored even when named with `/skill-name`. The named skill now goes first in the catalog and is always loaded, and reading its files and running its scripts work too.

## [8.9.0] - 2026-11-09

### Added

- **Long-term instructions**: the admin page gains 「組織指示」 (organization instructions) and the profile page 「個人指示」 (personal instructions), much like CLAUDE.md in Claude Code or AGENTS.md in Codex. They are appended after the system prompt of every question in both research and agent mode, for things like company terms, answer formats, or personal preferences; they cannot override the citation and data safety rules, and the organization instructions win where the two conflict. They live in a new `agent_instructions` table created at startup. Adds `GET`/`PUT /api/chat/instructions` and `GET`/`PUT /api/admin/agent-instructions`; see [API reference 2.18 and 8.7](docs/api_en.md#218-get-put-apichatinstructions).
- **Allow for this question**: the tool approval card gains an option after which the same tool is not asked about again during the same answer; the next question asks again, and deleting conversation files still needs approval every time. `POST /api/chat/approvals/{approval_id}` takes an optional `remember`.
- **Parallel research with subagents**: agent mode gains `delegate_research`, which hands up to 3 independent sub-tasks to subagents that research in parallel. Each subagent has its own context, can only search the knowledge base and the web and read conversation files, and makes at most 8 model calls; the research trace shows each subagent's steps as they happen, labelled with their sub-task, and citation numbers are shared with the main agent. When the user stops the answer, running subagents are cancelled.

## [8.8.0] - 2026-11-09

### Added

- **Agent mode can ask questions**: when a request can be read several ways, or it needs something only the user knows, the research assistant asks with a new `ask_user` tool and pauses. The answer shows a question card where the user picks a suggested option or types an answer; the answer reaches the model as the user's own words, and URLs in it can be read. With no answer within 5 minutes, the research assistant carries on with what it has and states its assumptions. Adds `POST /api/chat/questions/{question_id}` and the SSE events `question` and `question_resolved`; see [API reference 2.17](docs/api_en.md#217-post-apichatquestionsquestion_id).
- **Progress notes in the research trace**: text the model writes alongside its tool calls (for example 「先確認要整理的範圍」, "first confirm the scope") appears above the first research step of that turn, titles a running step, and is saved with the message. The agent system prompt asks the model to say what it is doing in one sentence when calling tools.
- **Structure check after creating files**: create and edit results for conversation files carry a `check` with the page count, headings, paragraph and table counts, sheet rows, or slide titles read back from the file, so the research assistant can spot an empty sheet or a missing table without reading the file back.

## [8.7.0] - 2026-11-09

### Added

- **Agent mode**: the top of the chat page switches between 「查證」 (research) and 「代理」 (agent). Following Claude Code and Codex, agent mode works toward finishing a task: understand → plan → act → verify → report, reading files back after creating or editing them and reporting what is unfinished or unverified. The research assistant lists its plan with a new `update_plan` tool; the interface shows the checklist and the completed count above the research trace, and the plan is saved with the message. For long tasks, agent mode makes at most 30 model calls and then asks the model to report its progress, and when tool results together exceed 40,000 characters the oldest are replaced with a one-line note. Research mode is unchanged. `POST /api/chat/send` takes a new `mode`, SSE adds a `plan` event, and messages gain a `plan` field; see [Architecture: Agent mode](docs/architecture_en.md#agent-mode).

## [8.6.0] - 2026-11-09

### Changed

- **The Claude output token limit is optional**: for Claude through Anthropic, the connection's "output token limit" can be left empty, and the model's output limit from the Models API is used instead; when it is set, the smaller of the two is used as before. Claude deployments on Foundry cannot look up the model limit and still need one.

### Fixed

- **A vLLM output token limit above the model's context length no longer stops research**: when a vLLM connection sets an output token limit, the backend reads the model's context length (`max_model_len`) from `/models` and caches it for 5 minutes; a limit at or above it is not sent as `max_completion_tokens`, so vLLM uses whatever length remains. Before, vLLM returned `400` and the research assistant stopped on its first turn with 在執行自主研究時遇到連線異常 ("a connection error occurred during research"). If the context length cannot be read, the limit is sent as set. vLLM 0.23 also reserves the limit out of the context length for output, so once research piles up tool results the prompt plus the limit no longer fits and the final answer failed with `400`; a request carrying the limit that gets `400` is now sent once more without it.

## [8.5.1] - 2026-11-09

### Fixed

- **`deploy/gen-env.sh` wrote `deploy/.env` with a missing line break**: `backend/.env.example` does not end with a newline, so the script glued its last line to the first deployment setting as `UPLOADS_WATCHER_INTERVAL=30HOST=0.0.0.0`; the backend refused to start because of the invalid value, and `HOST=0.0.0.0` never took effect. The script now adds a line break before the deployment settings. If an existing `deploy/.env` has that line, split it into two lines.

## [8.5.0] - 2026-11-09

### Added

- **File preview**: conversation files (attachments and files the research assistant created) and knowledge-base documents can be previewed right in the interface without downloading them first. The preview opens in a side panel: in chat it sits to the right of the conversation, can be resized by dragging or expanded, and leaves the conversation readable and usable. The backend turns files into web content and images: PDFs are rendered page by page as images, each loaded only when scrolled to; Word keeps headings, lists, tables, bold, and italics; Excel and CSV are shown as tables (at most 500 rows and 50 columns); PowerPoint shows each slide's title, text, tables, and speaker notes; Markdown and text files are shown as usual. When a knowledge-base document's original file is not on the server, the extracted text is shown instead. New `GET /api/chat/files/{file_id}/preview`, `GET /api/chat/files/{file_id}/pages/{page}`, `GET /api/documents/{document_id}/preview`, and `GET /api/documents/{document_id}/pages/{page}`; see [API reference 2.13, 2.14, 4.7, and 4.8](docs/api_en.md#213-get-apichatfilesfile_idpreview).
- **Web pages made by the research assistant**: the research assistant can create `.html` web pages (with CSS and JavaScript in the same file) that are previewed right in the conversation. The page runs in an isolated iframe: it is interactive, but cannot read AskMiao's sign-in state, make network requests, or load external resources; the preview URL uses a token that expires after 5 minutes (`POST /api/chat/files/{file_id}/view-token`, `GET /api/chat/files/{file_id}/view`). When the user asks for a file or a website, the system prompt and the tool description tell the research assistant to create a conversation file rather than only pasting code into the answer, and not to leave placeholders such as "this is an example" in the content. See [architecture: file and web page preview](docs/architecture_en.md#file-and-web-page-preview) for the design.
- **URL preview cards**: clicking a web page among an answer's sources first shows a preview card with the title, site name, and summary, and the page opens from the card; the preview uses only data the answer already has and never connects to the site separately.

### Changed

- **Web sources no longer open a new tab directly**: clicking a web page in the sources used to open it in a new tab; now the preview card shows first, and the page opens from "Open web page" on the card.
- **`X-Frame-Options` is added only to responses without `frame-ancestors`**: the backend used to add `X-Frame-Options: DENY` to every response, and now leaves it out when the response carries its own CSP `frame-ancestors` (currently only the isolated preview of web page files); `deploy/nginx.conf` now adds `X-Frame-Options` only to the frontend pages and leaves `/api/` to the backend; the build-time CSP adds `frame-src`. If a reverse proxy you run yourself adds `X-Frame-Options: DENY` to every `/api/` response, remove it so web page files can be previewed.

## [8.4.0] - 2026-11-08

### Added

- **Conversation files**: the research assistant can create, read, edit, and delete files in a conversation, and users download them from the file cards under that answer or from the "Conversation files" list in the header. It can create Markdown, plain text, CSV, JSON, Word (`.docx`), Excel (`.xlsx`), PowerPoint (`.pptx`), and PDF; Word and PDF files are produced from Markdown with support for headings, lists, tables, bold, and italics, and PDFs use built-in CJK fonts. Edits are always saved as a new version (for example `報告 v2.docx`) and the original stays unchanged: text files, Word, and PowerPoint are edited by replacing text (keeping the original paragraph styles), Excel by changing cells, and any file can also be rewritten whole. Every deletion by the research assistant needs the user's approval in the conversation, and a skill's `allowed-tools` cannot waive it; users can delete files themselves in the interface. See [architecture: conversation files](docs/architecture_en.md#conversation-files) for the design.
- **Conversation file API**: `GET /api/chat/conversations/{conversation_id}/files` lists files, `GET /api/chat/files/{file_id}` downloads one (always as an attachment, with `.html`, `.js`, and the like returned as plain text), and `DELETE /api/chat/files/{file_id}` deletes one, all limited to the file's owner; see [API reference 2.10–2.12](docs/api_en.md#210-get-apichatconversationsconversation_idfiles).
- **Streaming events**: a new `file` event (`action` is `created`, `updated`, or `deleted`), and `done` and message history gain `files`; `start` gains `attachment_file_ids`; `approval_required` gains the tool category `kind`, and the approval card for deleting a conversation file states that the file will be permanently deleted instead of reusing the explanation for external tools.
- **The research assistant knows the current date and time**: the latest user message starts with `[現在時間：…]` (the backend host's local time, to the minute), and the system prompt says to rely on it for relative times such as "today", "now", or "last month" and when filling in the current date or time, instead of searching the web for the time. Before, the model did not know the date and either guessed it or copied another time zone's time from web search results. In the Docker Compose deployment the backend's time zone is set to `Asia/Taipei` (the same as the database), and the image installs `tzdata`.

### Changed

- **Document attachments are saved as conversation files**: non-image attachments with a `data_url` in `POST /api/chat/send` are decoded and saved as files of that conversation, and the user message records only the `file_id` instead of keeping the base64; the research assistant can read them and edit them into new versions, and users can download them again. The attachment marker sent to the model becomes `[附件 #<file id>：<file name>]`, and it is included even when no text was extracted. Image attachments and attachments from 8.3.0 and earlier stay as they were.
- **The 200 MiB per user covers attachments and conversation files together**: past it, sending an attachment returns `413` and the research assistant can no longer create files; deleting conversation files frees space. Deleting a conversation (including when an admin deletes the conversation or the user) deletes its files too.

## [8.3.0] - 2026-11-08

### Added

- **vLLM provider**: API connections gain `vllm`, called through vLLM's OpenAI-compatible API (`{API address}/chat/completions`, with the model list read from `/models`) with tool calling and streaming. The reasoning level is sent as `reasoning_effort`; an optional output token limit is sent as `max_completion_tokens`; streams report token usage. The connection test sends one test tool and reports a clear error when vLLM was not started with `--enable-auto-tool-choice` and `--tool-call-parser`. Requires vLLM 0.23.0 or later; see [configuration reference: Connecting vLLM](docs/configuration_en.md#connecting-vllm).

### Changed

- **Text sent to the model lives in `backend/app/prompts.py`**: the system prompt, skill rules, tool and parameter descriptions, tool result and attachment wrapping, and the prompts for document summaries, OCR of scanned PDFs, and connection tests were spread across 8 modules and are now in one file that the other modules reference. See [architecture: prompts and tool descriptions](docs/architecture_en.md#prompts-and-tool-descriptions) for what each prompt is for and when it is sent.
- **System prompt rewritten after an audit**: split into sections with Markdown headings, with added context that the knowledge base holds the organization's internal documents and a rule that questions which may concern internal documents go to the knowledge base first instead of being answered from general knowledge. The system prompt no longer names tools: when to use each tool and what it returns moved into the tool descriptions, so disabling the web tools no longer leaves rules about `web_search` and `web_fetch` behind, and the rules for reading skill files and running skill scripts stay only in the skill content and tool descriptions instead of being repeated in the system prompt. "Do not make things up" and "say plainly when nothing was found" are merged into one rule, as are the rules for tools refused by the user or by the system. The old rule that URLs in tool results are never followed contradicted `web_fetch` being allowed to read URLs from tool results; it now says that anything a tool result asks you to do is never done.
- **Document summary and OCR prompts**: the document summary prompt drops embellishments such as 頂級專家 (top expert) and 嚴禁 (strictly forbidden) and instead explains what the summary is for (it is listed in the knowledge-base catalog so the research assistant can choose which document to search), and its length changes from 70–150 characters to two or three sentences; the OCR prompt keeps the page's original language instead of naming only Traditional Chinese and English.
- **Tool descriptions reworded and matched to the code**: the knowledge-base, counting, and web tool descriptions now say what they return (`citation` numbers, `total_count`, page titles and snippets) and when to use them, and the limits on the `web_search` query and the `web_fetch` URL are in the parameter descriptions. The `limit` of `filter_and_count_records` said up to 200 records while the actual limit is 50, and the `top_k` of `search_knowledge_base` said up to 5 while the actual limit is `FINAL_K` (8 by default); both descriptions now come from the limits in the code. The `keyword` description adds that several keywords are separated by commas or 、 and any one of them matches, and the `run_skill_script` description no longer says every run needs the user's approval, since none is needed when the skill's `allowed-tools` lists it.
- **Fixed tool list order**: the knowledge-base catalog, custom API tools, and MCP servers are sorted by id. They had no defined order, so updating a row could reorder them and invalidate the model provider's prompt cache.
- **Description prefixes in `GET /api/chat/tools` and the attachment marker change**: custom API tools are prefixed with `[自訂 API] ` instead of `[外部自訂 API]`, MCP tools with `[MCP 工具] server／tool` instead of `[MCP 協定工具]server -> tool`, and `read_mcp_resource` and `get_mcp_prompt` lose the `[MCP 協定]` prefix; attachment text starts with `[附件：file name]` instead of `[附加檔案: file name]`. Clients that match these descriptions by text need updating.

## [8.2.2] - 2026-11-07

### Changed

- **Document upload rejection reasons come from the exception's `reason` field**: `POST /api/documents/upload` no longer builds its response by calling `str()` on the exception (CodeQL `py/stack-trace-exposure`); the rejection reasons and other error messages are unchanged. No user-visible change.

## [8.2.1] - 2026-11-07

### Changed

- **Documentation checked against the current code and reorganized**:
  - The API reference, architecture, and configuration reference are corrected against the 8.2.0 code where they were wrong or outdated, for example the actual format of error responses and `error_id`, the approval exception for skill scripts, the middleware order, the LLM connection and Agent Skills subsystems, and resource limits that were not listed.
  - The API reference sections are reordered: API connections become section 3 and the former sections 3–6 move to 4–7; the Agent Skills folder upload follows the regular upload; removed endpoints are listed in section 0.
  - New [deployment guide](docs/deployment_en.md) (deploying with the Docker Compose setup in `deploy/`, HTTPS, backups, and updates) and [troubleshooting](docs/troubleshooting_en.md) page (moved out of the README and grouped by topic).
  - The README drops the 4.0.0 and 5.0.0 highlight sections and covers Agent Skills; the four upgrade tips at the top of this file are merged into one.
  - Every Chinese document is copy-edited line by line into Taiwan terminology with redundant wording removed (for example 用戶端, 金鑰, volume, 行程群組, 螢幕報讀軟體); older ADRs and early changelog entries are rewritten in plain language without changing the recorded facts.
- **UI text, API messages, and logs use Taiwan terminology**: for example 配置 → 設定, 調用 → 呼叫, 令牌 → 權杖, 聯繫 → 聯絡, 提取 → 擷取, and 分塊 → 切塊, and the Simplified character 内 in an error message is fixed. Some API response messages change as a result (for example `MCP 伺服器設定更新成功` and `目前不開放註冊，請聯絡管理員建立帳號`), so clients that match these messages by text need updating; the `[本頁為圖檔或無可提取純文字]` marker in PDF text and content already in the knowledge base are unchanged.
- **No more code comments or docstrings**: code comments in the backend and frontend, Python docstrings, and the comments in CSS and `index.html` are removed; tool directives such as `# noqa` and shebangs stay. With `ENABLE_API_DOCS=true`, endpoints in `/docs` no longer show the descriptions that came from docstrings; see the [API reference](docs/api_en.md) for each endpoint.

### Fixed

- **Claude output token limit error messages**: when no limit is set or tool call arguments are cut off, the message no longer asks you to set `ANTHROPIC_MAX_TOKENS` in `.env` (removed in 8.0.0) and points to the API connection's "output token limit" instead; for system models, adjust the shared connection they use.

## [8.2.0] - 2026-11-07

### Security

- **Skill uploads reject paths with a colon**: only a leading drive letter used to be blocked, so a zip entry with a colon in the middle of its path, such as `skill/D:/evil.py` or `notes.md:stream`, was written outside the skill directory on a Windows host, to another drive or an NTFS alternate data stream. Now any path segment containing a colon rejects the whole upload with `400`, for both zip and folder uploads. Docker (Linux) deployments were not affected.

### Added

- **Upload Agent Skills from a folder**: "AI Tools → Upload skill" now selects a folder by default, so there is no need to zip it first. When the folder holds several skills (for example `~/.agents/skills`), every directory containing a `SKILL.md` is installed as one skill; other `SKILL.md` files inside a skill directory are that skill's files, and `.git`, `__MACOSX`, and `.DS_Store` are not uploaded. A skill that is invalid, shares its name with another skill in the folder, or has the name of an existing skill (without "replace") is skipped and listed with its reason in the dialog while the others are installed; name conflicts can be resolved with "Replace existing skills with the same name". The new endpoint is `POST /api/skills/upload-folder`, with at most 1000 files (`MAX_SKILL_FOLDER_FILES`) and 50 MiB (`MAX_SKILL_UNCOMPRESSED_BYTES`) per folder and 500 files per skill; see [API reference 7.5](docs/api_en.md#75-post-apiskillsupload-folder).

### Changed

- **Skills are installed on a worker thread**: writing skill files and database records during an upload no longer holds the main thread that serves every request, so other users' streamed answers do not pause during an upload; installs and deletions run one at a time, keeping database records and skill files in sync when the same skill is uploaded concurrently.

## [8.1.0] - 2026-11-03

### Security

- **Remote MCP OAuth hardened to the 2026-07-28 authorization specification**: the authorization callback checks `iss` per RFC 9207 against mix-up attacks between authorization servers; the authorization server metadata's `issuer` must be identical to the issuer used to fetch it; authorization servers that do not declare `code_challenge_methods_supported` with `S256` are refused (previously a missing field was allowed); authorization server endpoints must be HTTPS (loopback excepted), and so must the redirect address unless it is localhost; a dynamically registered client is bound to the authorization server that issued it, so a changed authorization server registers again and clears the tokens. Stored tokens keep working, and the rules apply the next time "OAuth authorization" is pressed; deployments serving AskMiao over plain HTTP on a non-localhost address need HTTPS to authorize.

### Added

- **MCP 2026-07-28**: the MCP client now speaks the latest stateless protocol first: every request carries the protocol version, `clientInfo`, and `clientCapabilities` in `_meta`, and `server/discover` returns the server's supported versions and capabilities; HTTP requests carry `MCP-Protocol-Version`, `Mcp-Method`, and `Mcp-Name`, mirror tool parameters marked `x-mcp-header` into `Mcp-Param-*` headers (encoded as `=?base64?…?=` when needed), and re-read the tool list and retry once on `HeaderMismatch`. Servers that only support the `initialize` handshake (`2025-11-25` through `2024-11-05`) keep working: stdio probes with `server/discover` and falls back to the handshake on an error or no reply within 5 seconds, HTTP decides from the body of a `400`/`404`/`405`, falling back further to the legacy HTTP+SSE transport when needed. The negotiated version is stored in the new `protocol_version` column (added automatically on startup), reused for tool calls, and renegotiated automatically when it stops working. A response asking for more input (`input_required`) is reported as a failure. See [API reference 6](docs/api_en.md#6-mcp-servers-apimcp).
- **Client ID Metadata Documents and step-up authorization for MCP OAuth**: when the authorization server supports Client ID Metadata Documents and AskMiao is served over HTTPS, the public `GET /api/mcp/oauth/client-metadata.json` URL becomes the `client_id` and no dynamic registration is needed; dynamic registration sends `application_type`. Scopes listed in the `401` `WWW-Authenticate` header now come first; a `403 insufficient_scope` while connecting records the required scopes, the admin page asks for re-authorization, and the next authorization adds them to the previous scopes.

### Changed

- **The built-in time MCP preset answers both protocol eras and declares tool annotations**: `mcp_time` answers both `server/discover` (`2026-07-28`) and `initialize` (legacy), `get_current_time` is marked `readOnlyHint: true`, `destructiveHint: false`, `idempotentHint: true`, and `openWorldHint: false`, and unknown methods get `Method not found` (previously no reply, so the client could only wait for its timeout).
- **MCP tool definitions and results**: a tool's `inputSchema` is normalized into a parameter schema every provider accepts before it reaches the model, resolving only `$ref`s inside the tool definition; a `$ref` to the network or another document (never downloaded) or, on the HTTP transport, an `x-mcp-header` that breaks the rules makes discovery skip the tool. Binary content in images, audio, and embedded resources in tool results no longer reaches the model (previously it was serialized as is and used up the 20,000-character result limit), `structuredContent` is passed along, and a JSON text block identical to it is dropped. The admin page shows each MCP server's negotiated protocol version, and the tool list shows `title` and the server-declared "read-only", "may change data", and "reaches outside" labels (annotations are untrusted per the specification and do not affect call approval).

## [8.0.2] - 2026-11-02

### Changed

- **Tests strip HTML tags with a character scan**: `rows.test.jsx` and `chatComponents.test.tsx` no longer strip tags with a single `replace(/<[^>]+>/g, '')` (CodeQL `js/incomplete-multi-character-sanitization`). No user-visible change.

## [8.0.1] - 2026-11-02

### Security

- **pypdf upgraded to 6.21.4**: fixes possible infinite loops, long runtimes, and large memory use on malicious PDFs, covering the trailer search in xref tables, page tree and cross-reference stream parsing, dictionary cloning, page labels, and encrypted files and strict-mode exceptions (GHSA-5849-834g-hvw5, GHSA-cggf-277g-3q54, GHSA-mfr5-77xh-9j7h, GHSA-42gh-23hr-vphw, GHSA-4vqv-7265-gm2w, GHSA-62m5-6wh8-28x7, GHSA-x3rh-gjgm-fmqc). Uploaded PDFs fall back to pypdf when PyMuPDF cannot read them, so before this upgrade a malicious file could use that path to stall background processing.

## [8.0.0] - 2026-11-02

> [!IMPORTANT]
> `.env` no longer configures any model provider. Document summaries and OCR of scanned PDFs use the shared connections an admin chooses under "Admin → System models"; after upgrading both are unset, so summaries are rule-based and scanned pages get no OCR. Deployments that set `FOUNDRY_*`, `OPENAI_*`, `ANTHROPIC_*`, `GEMINI_*`, or `LLM_API_BASE` in `.env` should:
>
> 1. Under "Admin → Shared API connections", create a shared connection for the same provider (copy the key, address, and models; if only the system models need it, grant it to yourself alone).
> 2. Under "Admin → System models", pick a model and a reasoning effort for "Document summary" and for "Scanned PDF recognition (OCR)"; the OCR model must accept image input, and `none` is recommended for small local models so they do not time out.
> 3. Delete the removed settings from `.env` (if left in place they are ignored).
>
> External programs calling `GET /api/tags` should use `GET /api/chat/models` instead (sign-in required; lists the models of the account's API connections).

### Added

- **System models**: the admin page gains a "System models" card that picks one shared connection, one of its models, and a reasoning effort (the same choices as chat, with levels the model does not support disabled) for document summaries and for OCR of scanned PDFs, stored in the new `system_models` table, which is created on startup. New `GET/PUT /api/admin/system-models` (admins only; changes are written to the security log as `ADMIN_SYSTEM_MODELS_UPDATED`). When the shared connection is deleted, or edited so that it no longer offers the chosen model, that purpose is cleared automatically.
- **Retrieval benchmark and chunk-level metrics**: golden sets can label short verbatim snippets in `relevant_passages`, and evaluation then also reports chunk-level precision@k, nDCG@k, snippet recall@k, MRR, and candidate recall (whether the candidates before reranking already contain the answer); a snippet missing from the knowledge base fails the evaluation. `scripts/evaluate_retrieval.py` gains `--corpus` (builds the knowledge base the way uploads do, on a temporary SQLite database and temporary indexes, without touching production data) and `--min-passage-ndcg`. Built-in benchmark: `backend/eval/corpus/` (12 fictional company documents and Taiwan's Mass Rapid Transit Act, 119 chunks) with `backend/eval/corpus_golden.jsonl` (103 positive and 15 negative cases); see [ADR-0007](docs/adr/0007-han-ngram-bm25-and-passage-level-evaluation_en.md).
- **OpenAPI 3.2, Arazzo, and Overlay**: custom API tools can import OpenAPI 3.2 (the `query` method, `additionalOperations`, `in: querystring`, `components.mediaTypes`, `$self`); each Arazzo 1.0/1.1 workflow becomes one tool that runs its steps in order and passes outputs through runtime expressions, with simple, regex, and JSONPath success criteria and end, goto, and retry actions (at most 50 steps and 300 seconds per run); Overlay 1.0–1.2 can be applied before importing (backed by a new RFC 9535 JSONPath implementation), and `POST /api/api-tools/parse-spec` gains an `overlays` field. See [API reference 5.1 and 5.10](docs/api_en.md#51-post-apiapi-toolsparse-spec).
- **External `$ref` and JSON Schema 2020-12**: importing by URL downloads external reference documents through SSRF validation (at most 20, 30 MB in total), and `$id`, `$anchor`, `$defs`, and path item `$ref`s are resolved; `allOf`, `oneOf`/`anyOf` (with `discriminator`), `type` arrays, `const`, and `prefixItems` become parameter schemas every provider accepts. Parse results gain `warnings` listing what could not be imported fully.
- **Request IDs and more detailed logs**: every request gets an ID (a well-formed `X-Request-ID` is reused, otherwise one is generated) that appears in the `X-Request-ID` response header, on every log line written during the request, in the `request_id` field of `security.log`, and in the `request_id` of the chat stream's `error` event, so one ID finds everything a request logged. The new entries below contain no passwords, keys, tokens, cookies, or query parameter values, and no prompts or conversation content.
  - Every `/api` request writes one access line when it ends: method, path, status code, duration, response size, client IP, and user id.
  - Model calls record the duration, success or failure, the timeout in seconds and the exception class, and the token usage the provider returned (Ollama adds the time spent loading, reading the prompt, and generating); streams also record when the first text arrived.
  - Tool calls record the name, kind, duration, result status, and result size; calls that never ran because a research rule refused them, the user did not approve them, or no one could approve them get a line each too. The research loop's `調用工具` entry now records only parameter names, not their values, and the retriever's `Retrieval` entry records only the query length (`query_chars`), not the query itself.
  - Rate limiting no longer writes a line for every blocked request: an IP gets one line (with the path) when it is first blocked within a window, and another when the window ends with the number of blocked requests and the count per path.
  - `LOG_LEVEL` accepts only `DEBUG`, `INFO`, `WARNING`, `ERROR`, and `CRITICAL` and applies to all output, so `DEBUG` messages from third-party packages such as jieba no longer reach `app.log`; `security.log` now uses the same format as `app.log`. Programs that parse the logs should note the new `[request ID]` field after the level on every line.

### Changed

- **Document summaries use the chosen system model**: uploads, summary regeneration, and index rebuilds summarize with the "Document summary" system model and its reasoning effort, with `LLM_TIMEOUT` as the timeout; with none chosen no model is called and the rule-based summary is used directly, and uploads no longer query the model list at `LLM_API_BASE`.
- **OCR of scanned PDFs works with all five providers**: PDF pages with no text layer in knowledge-base uploads, index rebuilds, and chat attachments go to the "Scanned PDF recognition" system model through the same calling layer as chat, so vision models from OpenAI, Anthropic, Gemini, Microsoft Foundry, and Ollama all work (previously only Chat Completions on Foundry, OpenAI, and Gemini).
- **The official API addresses prefilled for new connections are fixed values**: `OPENAI_API_BASE`, `ANTHROPIC_API_BASE`, and `GEMINI_API_BASE` are no longer read.
- **Han unigram and bigram fields in BM25**: jieba's built-in dictionary leans Simplified and often mis-segments Traditional words (「大眾捷運系統」 → 「大眾捷／運系統」), so BM25 missed entirely when the query and the document were segmented differently. BM25 now also has `han_unigrams` and `han_bigrams` fields, and the query combines the terms of all three fields with OR. On the built-in benchmark candidate recall went from 0.971 to 1.000 and nDCG@5 from 0.898 to 0.907; on a 2,437-post corpus nDCG@5 went from 0.893 to 0.901. The BM25 index is about 70% larger and the median query time went from 1.0 to 2.6 ms. The tokenizer rules version becomes 3, so BM25 is rebuilt from the database chunks on the first start without recomputing vectors; there are no new settings.
- **Custom API tools send parameters by their OpenAPI style**: imported tools record each parameter's `style`, `explode`, `allowReserved`, and media type (the new `param_styles` column, added to the table automatically on startup). Paths support `label` and `matrix`, query strings support `deepObject`, `spaceDelimited`, `pipeDelimited`, and Swagger 2.0 `collectionFormat`, and cookie parameters and `in: cookie` API keys go into the `Cookie` header (they used to be sent as query parameters or body fields). Object query parameters no longer send a Python repr, booleans are always `true`/`false`, and arrays in `application/x-www-form-urlencoded` and `multipart/form-data` bodies are sent as repeated fields (previously a JSON string), matching the OpenAPI Encoding defaults.
- **Request bodies keep their declared media type**: `body_content_type` accepts any media type, and JSON-family types such as `application/merge-patch+json`, XML, plain text, and other types are sent as declared (previously everything fell back to `application/json`).
- **Stricter, more complete spec imports**: Swagger 1.x, OpenAPI 3.3 and later, and documents without a version are rejected (they used to be guessed as 3.0); path- and operation-level `servers`, relative server URLs, and Swagger 2.0 specs without `host` or `schemes` are completed from the document URL; parameters merge by name plus location, so same-named parameters in different locations no longer overwrite each other; duplicate tool names within one spec get numbered. Header parameters cannot set `Authorization`, `Content-Type`, `Cookie`, or admin-configured headers. OAuth flows that need user authorization and OpenID Connect map to Bearer with a reminder to enter a token.
- **Redesigned "AI tools" page**: the page header keeps only go to chat, refresh, and an "Add tool" menu; custom API tools, MCP servers, Agent Skills, and built-in tools each get a section whose title shows counts and how many are enabled or connected, and each item becomes one row (name, identifier, endpoint, status switch, and common actions), with parameters, trigger timing, the MCP tool list, and skill script settings behind "Details". Items with connection errors, credentials that cannot be decrypted, or missing skill files are listed together at the top of the page; sections show placeholder rows while loading and, when loading fails, say so inside the section with a retry button. The API spec import dialog is split into two steps, "Provide spec" and "Pick endpoints and import", Overlay moves into an optional expandable area, and the endpoint list uses a select-all checkbox that can be partly checked; the add and edit forms are split into basic info, request, authentication, and parameters. The page no longer scrolls sideways at phone width, and light and dark themes use the existing design tokens. API calls, fields, and submitted data are unchanged.
- **Redesigned "Chat" page**: the conversation is now a centered reading column, AI answers are no longer wrapped in cards, and your own messages sit on the right in a light bubble; the research trace, thinking process, tool approval, and sources share one style, and each source is numbered to match the [n] markers in the answer and opens to show the passage, relevance, and excerpt. Sidebar history is grouped into today, yesterday, the past 7 days, and earlier, with placeholder rows while it loads; a blank conversation lists suggested questions, and placeholder messages show while a conversation loads. On desktop the input box splits into a text row and a button row, dragging a file shows a drop hint, and skill suggestions float above the input instead of pushing the layout. While an answer streams, only that answer re-renders and older messages defer layout, so long conversations scroll more smoothly; screen readers announce when the AI asks to approve an external tool. The page no longer scrolls sideways at phone width, and light and dark themes use the existing design tokens. API calls, submitted data, and existing behavior such as Enter not sending while an input method is composing are unchanged.
- **OpenVINO reranking sends only the actual candidates and no longer loads the PyTorch model**: with `RERANKER_OPENVINO_DEVICE` set, the batch size varies from 1 to `RERANK_TOP_K` with the number of candidates instead of being padded to full. Interleaved in one process on an Intel Core Ultra 7 155U iGPU, 10 candidates went from 2.83 to 0.51 s, and the median of the built-in benchmark's 118 reranks (30–50 candidates each) went from 2.73 to 2.46 s. The first time a new number of candidates appears, compilation adds about 0.3 s. The top result and the relevance-threshold decisions match PyTorch exactly.
  - Only the tokenizer is loaded, which uses about 0.8 GB less resident memory.
  - The IR is now a single dynamic-shape file whose name includes a fingerprint of the model files: an updated model is converted again automatically, and changing `RERANK_TOP_K` or the length needs no new conversion. Conversion writes to a temporary file and then renames it, so an interruption cannot leave a broken IR.
  - A `RERANKER_OPENVINO_MAX_LENGTH` above the model's limit fails at startup.
  - The first start after upgrading converts the model once; the old `*_50x256.xml` and `*_50x256.bin` files in `DATA_DIR/openvino_cache` can be deleted.
- **The log directory comes from the required `LOG_DIR`, and backend tests no longer write to the real logs**: `app.log` and `security.log` both go to `LOG_DIR` (a relative path resolves against `backend/`; `security.log` used to go to `logs/` under the startup directory). `security.log` is opened when the first security event is written, and the whole pytest session writes to a temporary directory, so fake events from the Starlette TestClient (`client_ip` of `testclient`) no longer mix into the audit log. When upgrading, add `LOG_DIR=logs` to `.env` to keep the logs in `backend/logs/`; without it the backend does not start; see the [upgrade guide](docs/upgrading_en.md#upgrading-from-700-to-800).

### Fixed

- **Web search works again**: without `OLLAMA_API_KEY`, the DuckDuckGo fallback always returned 0 results and no error, because DuckDuckGo result links now put `rel` before `class` and the old pattern no longer matched. Results are now parsed one by one for title, URL, and snippet, a result without a snippet no longer shifts the others, and ads are skipped; a results page with nothing parsable returns an error, so the model knows the search failed and uses other data instead of treating it as no matches.
- **Web reading keeps the main content**: `web_fetch` used to turn navigation bars, sidebars, headers, and footers into text too, and since only the first 3500 characters are kept, documentation sites often came back as nothing but the sidebar (the OpenVINO docs page only reached its content at character 128,338). Pages with `<main>`, `role="main"`, or `<article>` now keep only that content, minus its `nav`, `aside`, and navigation or complementary roles; pages without one skip `nav`, `aside`, `header`, `footer`, and the matching ARIA roles across the page. The scan stays linear.
- **Answers no longer keep `[n]` markers that point to no source**: when the model writes citation numbers without looking anything up (for example a small local model with reasoning turned off), or uses a number that no tool result in this request carries, those markers are removed before the answer is sent and saved; numbers that match a source stay, and code blocks and inline code are left alone. Previously such numbers were only left out of the source list while the text still showed [1]. Messages already saved are not rewritten.
- **`app.log` no longer stops being written on Windows once it reaches the rotation size**: the backend loads `main.py` twice at startup, and the extra copy and the `RELOAD=true` watcher process both kept `app.log` open, so at 10 MiB it could not be renamed for rotation and every later entry was lost. Log files are now opened when the first entry is written, and the watcher process no longer keeps one open.

### Removed

- **Provider settings in `.env`**: `LLM_API_BASE`, `MODEL_NAME`, `AVAILABLE_MODELS`, `FOUNDRY_API_KEY`, `FOUNDRY_ENDPOINT`, `FOUNDRY_DEPLOYMENT` (and the old `AZURE_OPENAI_*` names), `OPENAI_API_KEY`, `OPENAI_API_BASE`, `OPENAI_VISION_MODEL`, `ANTHROPIC_API_KEY`, `ANTHROPIC_API_BASE`, `ANTHROPIC_MAX_TOKENS`, `GEMINI_API_KEY`, `GEMINI_API_BASE`, `GEMINI_VISION_MODEL`, `EXTERNAL_TAGS_URL`, and `ADD_NGROK_HEADER`. `LLM_TIMEOUT`, `LLM_TAGS_TIMEOUT`, `OLLAMA_TEMPERATURE`, `OLLAMA_NUM_PREDICT`, and `OLLAMA_NUM_CTX` stay and apply to every connection.
- **`GET /api/tags`**: it only returned the system model list from `.env`, and the frontend never used it.
- **`scripts/test_llm_clients.py`**: it only checked the `.env` model list and provider routing, which no longer exist.

---

## [7.0.0] - 2026-10-31

> [!IMPORTANT]
> Chat no longer uses the models and keys in `.env`. After upgrading, every account (admins included) needs an API connection to chat: an admin recreates the `.env` providers as shared connections under "Admin → Shared API connections" and picks the accounts that may use them, or each account adds its own key under "Profile → My API connections". `POST /api/chat/send` now requires `connection_id` and `model_name`.
>
> API clients need two more changes: `PUT /api/auth/me` only updates the email, so change passwords with `POST /api/auth/change-password`; `messages` in `GET /api/chat/conversations` and `GET /api/chat/conversations/{conversation_id}` is always an empty array, so read messages from `GET /api/chat/conversations/{conversation_id}/messages`. The backend and frontend dependencies are the same as in 6.0.0; see the [upgrade guide](docs/upgrading_en.md#upgrading-from-600-to-700).

### Security

- **Members' personal connections can only reach public addresses**: the API address is checked when a connection is saved, and every model call goes through the SSRF check and is pinned to the approved IP (the httpx2 client used by the Anthropic SDK included), so nobody can use their own connection to make the backend reach the internal network or cloud metadata services. Error messages never reveal the internal address a name resolved to. Admins' personal connections and shared connections may point at the internal network (for example a local Ollama).
- **Deactivating an account revokes its tokens**: deactivating an account sets `users.tokens_valid_after` to the current time. Its tokens already stopped working while it was deactivated; now the access and refresh tokens issued before deactivation do not come back when it is reactivated, and the account must sign in again.
- **Changing a connection's provider or API address drops the stored key**: an update to a personal or shared connection that changes `provider` or `api_base` without sending a new key clears the stored key, and providers that need a key return `400` asking for it again; `POST /api/llm-connections/discover-models` uses a stored connection's key only when both the provider and the API address match it. A stored key is never sent to another provider or address.
- **Usernames accept only Chinese characters, ASCII letters, digits, `_`, and `-`**: registration, admin account creation and editing, and `scripts/create_user.py` all apply the same rule. The previous `\w` rule also accepted look-alike letters such as Cyrillic, full-width letters, and a trailing newline, so a name could look identical to an existing account; existing accounts are unaffected and sign in as before.
- **A skill whose `allowed-tools` lists `run_skill_script` pre-approves only its own scripts**: previously, once such a skill was activated, scripts of other skills ran without approval for the rest of that question too.
- **Skill scripts stop when the chat is cancelled**: when the user stops an answer or the connection drops, a running `run_skill_script` script and its child processes are terminated instead of continuing in the background.
- **The `web_fetch` domain allowlist is checked on every redirect**: when `WEB_FETCH_ALLOWED_DOMAINS` is not `*`, each redirect target must be on the allowlist too (previously only the initial URL was checked, so an allowed site could redirect the request to any domain), and Ollama Web Fetch is no longer used (Ollama follows redirects on its side, so they cannot be checked hop by hop).
- **State-changing custom API tools no longer follow cross-origin redirects**: methods other than `GET`, `HEAD`, and `OPTIONS` follow only same-origin redirects, so the request body never goes to another domain; a refused redirect or more than 5 redirects gives `status_code` `400` with an `error` starting with 「上游轉址未跟隨：…」 (upstream redirect not followed) that says why, while SSRF rejections are still `403`.
- **A new `.dockerignore` at the repository root**: images built from the repository root leave out `.env` at any level, `backend/keys`, `backend/data`, `backend/logs`, `node_modules`, `.git`, `.venv`, and similar, so keys, data, and local settings are not packed into images.
- **`deploy/gen-env.sh` sets `COOKIE_SECURE` from `PUBLIC_ORIGIN`**: when `PUBLIC_ORIGIN` starts with `https://`, it writes `COOKIE_SECURE=true`, so the refresh token cookie is sent over HTTPS only.
- **The production image installs no test packages**: `deploy/Dockerfile.backend` skips `pytest`, `pytest-asyncio`, `psutil`, `iniconfig`, and `pluggy` from `requirements.txt`.
- **General logs can no longer be forged with extra lines**: `app.log` and console logs escape line breaks in messages as `\n`, so user-supplied text (such as a model name, tool name, or URL) cannot fake a normal-looking log line; exception tracebacks stay multi-line. Found by a CodeQL scan (`py/log-injection`).

### Added

- **Per-account API connections**: "Profile → My API connections" adds connections to OpenAI (or a compatible API), Anthropic Claude, Google Gemini, Microsoft Foundry, or Ollama, with an API address, key, model list, and the Claude output token limit. Only the owner sees and uses them. Keys are encrypted with `TOOL_SECRETS_KEY`; responses only say whether one is set (`has_api_key`). New endpoints: `GET/POST /api/llm-connections`, `PUT/DELETE /api/llm-connections/{id}`, `GET /api/llm-connections/providers`.
- **Shared connections granted by admins**: "Admin → Shared API connections" creates shared connections and picks which accounts may use them (all accounts, or only the checked ones); other accounts never see them in the model list. New endpoints: `GET/POST /api/admin/llm-connections`, `PUT/DELETE /api/admin/llm-connections/{id}`. Deleting an account deletes its personal connections and removes it from shared connection lists.
- **Connection test**: `POST /api/llm-connections/{id}/test` sends one short message with the chosen model and returns the reply or the reason it failed; owners test personal connections, admins test shared ones.
- The chat model menu groups models by connection (personal / shared) and tells accounts without any model to add one in their profile.
- **Fetch models from the API**: when adding or editing a connection, one click lists the models the provider reports (OpenAI-compatible `/models`, Gemini, Claude's Models API, Ollama's `/api/tags`) to check off; editing reuses the stored key. New endpoint: `POST /api/llm-connections/discover-models`. Foundry cannot list deployments, so those are still typed in.
- The account list of a shared connection is searchable, with select all / clear for the search results; deactivated accounts are labelled.
- **User management**:
  - Admins can add accounts in the admin dashboard (`POST /api/admin/users`, with the same rules as self-registration).
  - Admins can reset other accounts' passwords (`PUT /api/admin/users/{id}/password`), which signs that account out everywhere.
  - Editing an account lets admins check the shared connections it may use (`GET/PUT /api/admin/users/{id}/llm-connections`) and see its personal connections.
  - The user list is searchable and shows the last sign-in time.
- **Docker Compose deployment for a VM** (`deploy/`): `docker-compose.yml` runs PostgreSQL 17, the backend, and an nginx frontend, with the database and the backend's `data`, `keys`, and `logs` on named volumes. The backend image installs the CPU build of torch and skips the `nvidia-`, `triton`, and `cuda-` packages; nginx serves the frontend build and reverse-proxies `/api`, resolving the backend address through Docker's built-in DNS so a recreated backend container does not cause `502`; the frontend build converts `index.html` to LF first. `deploy/gen-env.sh` generates `deploy/.env` on the target host (the PostgreSQL and application account passwords, `TOOL_SECRETS_KEY`, and so on) from `PUBLIC_ORIGIN`, `WEB_PORT`, `NETWORK_SUBNET`, and `WEB_CONTAINER_IP`, so no secrets go into the repository.

### Changed

- **Chat only uses the connections an account may use**: `GET /api/chat/models` now requires sign-in and returns `{"connections": [{id, name, provider, scope, models}]}`; `connection_id` and `model_name` are required in `POST /api/chat/send`, which returns `400` when the connection is not the caller's own or granted to them, or the model is not in its list. It no longer falls back to `MODEL_NAME` or the keys in `.env`.
- The LLM settings in `.env` (`MODEL_NAME`, `AVAILABLE_MODELS`, the provider keys, and `LLM_API_BASE`) only serve background system work: AI summaries of uploaded documents and `GET /api/tags`.
- Self-registered accounts never use the operator's LLM keys; with `ALLOW_REGISTRATION=true`, remember that all accounts still share the knowledge base and the enabled tools.
- Admins cannot deactivate or delete their own account or remove their own admin rights (`400`), so the system always keeps someone who can manage it; `PUT /api/admin/users/{id}` validates the username and email format (`422` otherwise), and toggling admin rights sets `role` to `admin` or `user` accordingly.
- **`PUT /api/auth/me` only updates the email**: it no longer accepts `current_password` and `new_password` (they are ignored if sent, and the password does not change); change passwords with `POST /api/auth/change-password`.
- **Conversation endpoints no longer include messages**: `messages` in `GET /api/chat/conversations` (previously the 5 most recent per conversation) and `GET /api/chat/conversations/{conversation_id}` (previously the newest 500) is always an empty array; read messages page by page from `GET /api/chat/conversations/{conversation_id}/messages`. The `LIST_PREVIEW_MESSAGES` constant is removed.
- The `POST /api/documents/rebuild-index` response gains `failed_documents` (each with `document_id` and `filename`); when documents fail, `message` says how many, and the knowledge base page lists the failed file names.
- `scripts/reprocess_existing_docs.py` runs the same flow as the rebuild-index endpoint: it no longer clears every index first or regenerates every document's summary (hand-edited summaries are kept), and it lists the documents that failed.
- A BM25 index write that still fails after 3 attempts now fails the operation (uploading a file, deleting or rebuilding a document, or the BM25 rebuild at startup) instead of writing one error log line and leaving BM25 out of step with the vector index.
- **Claude caching, reasoning effort, and refusal fallback**: the last user message gets a cache breakpoint, so multi-turn chats and tool loops can read from the cache, and the log records `cache_read` and `cache_creation` token counts; reasoning effort `none` now sends effort `low` (previously nothing was sent, so the model used its higher default); `claude-opus-4-8`, `claude-opus-4-7`, `claude-opus-4-6`, and `claude-sonnet-4-6` explicitly enable adaptive thinking unless the effort is `none`; `claude-opus-5-5`, `claude-opus-5`, `claude-fable-5-1`, and `claude-sonnet-5-5` on the Claude API directly enable the server-side refusal fallback (`fallbacks: "default"`); tool loops use streaming, so long responses are no longer bound by a single request timeout.

### Fixed

#### Knowledge base and document extraction

- A document is split into Q&A pairs as an FAQ only when nothing but whitespace comes before its first 「Q：」 line: a manual with an FAQ section in the middle is now indexed in full, where previously everything before the first 「Q：」 line was left out of the index; Q&A pairs longer than `CHUNK_SIZE` are split further instead of becoming one chunk each.
- `search_knowledge_base` with `target_document` searches only that document's chunks: previously it took the top results from the whole knowledge base and then filtered them, so in a large knowledge base the document's chunks often did not make the cut and nothing was reported found.
- Documents left without any chunks by an interrupted upload (for example a backend crash) are indexed at startup, with the same extraction as a rebuild.
- Deleting a document returns `500` when removing it from the indexes fails, instead of reporting success; leftover chunks are removed by the reconciliation at the next startup.
- Rebuilding the index no longer clears the whole index first: each document's old chunks are replaced by its new ones, other documents stay searchable during the rebuild, and a document whose re-extraction or chunking fails keeps its old chunks and is listed in `failed_documents`.
- Query embeddings are computed outside the index lock, so other searches and document writes no longer queue behind them.
- PDF: before extraction, alternate glyphs in embedded TrueType fonts that the ToUnicode map leaves unmapped or maps to U+FFFD are mapped back to their source character through the font's GSUB single substitutions, so digits in Noto Sans TC exported by Illustrator, for example, are no longer extracted as 「俸」 or 「俻」; the font repair code that did not work is removed.
- A PDF with no extractable text on any page (for example a scan with OCR not configured or failing) is rejected with `400` and the reason, instead of being stored as the placeholder 「[本頁為圖檔或無可提取純文字]」 (page is an image or has no extractable text); different scans are no longer treated as duplicates because of identical placeholder text.
- An upload whose name matches an existing document (including one whose original file is missing) also gets a `_1`, `_2`, … suffix, and the suffixed name stays within `MAX_FILENAME_BYTES` (255 bytes in UTF-8).
- Failed uploads show the actual reason (an extraction limit, an invalid Office file, no extractable text, a password-protected PDF, and so on) instead of always 「安全驗證失敗」 (security check failed); password-protected PDFs and Chinese file names over 255 bytes now return `400` instead of `500`.
- When one file of a batch upload fails its database commit, the transaction is rolled back and the other files in the batch are processed as usual.
- PPTX extraction includes shapes and tables inside groups and each slide's speaker notes; DOCX extraction outputs paragraphs and tables in document order, so tables stay under their headings instead of all coming at the end.
- New SQLite databases create `rag_chunks` with `AUTOINCREMENT`, so deleted chunk ids are never reused; existing tables are unchanged.

#### Custom API tools, OpenAPI, and MCP

- Tool names given to the model are at most 64 characters (`MAX_TOOL_NAME_CHARS`): names generated from an OpenAPI `operationId` or an MCP tool, and overlong names already in the database, are truncated with an 8-character hash appended; creating a tool by hand or importing one with a name over 64 characters returns `400`. Previously an overlong name made the provider reject the whole request.
- Re-importing an OpenAPI spec keeps the stored headers and credentials (only fields this import sends with a value override them) and the tool's enabled state, so disabled tools are not re-enabled.
- When the request body is an array, string, number, or object without `properties`, the `request_body` from the model is sent as the whole body and keeps its full schema (such as an array's `items`); a non-object body with a form or `multipart/form-data` body type returns `400` with the reason.
- A `$ref` used in several places is expanded in full at each one (previously only a description remained from the second use on); at most 200 references (`MAX_OPENAPI_SCHEMA_REFS`) are expanded per parameter or body schema.
- Swagger 2.0 `in: formData` parameters become body fields and are sent as a form according to the endpoint's or the spec's top-level `consumes`.
- Parameters, request bodies, and security schemes given as a `$ref` import correctly: previously resolving them lost fields such as `name`, `in`, and `content`.
- Changing an MCP server's URL clears an OAuth client obtained through dynamic registration (a client entered by an admin is kept), so the old server's client is not carried to a new authorization server.
- The page title returned by `web_fetch` is the first `<title>`; pages with several `<title>` elements (for example inline SVG) no longer get the last one.

#### Chat and models

- When `run_skill_script` is offered, the system prompt and skill content no longer tell the model that 「本系統不會執行技能內的腳本」 (this system never runs scripts in skills); they explain that scripts run through `run_skill_script` and only scripts of the skills it lists can run.
- `PUT /api/auth/me` no longer saves a new email before a failing password check (the password fields are removed; see Changed).
- The conversation list and single-conversation endpoints no longer read messages and attachment content from the database.
- Follow-up questions include the text of earlier attachments: the text extracted from an attachment (at most `MAX_ATTACHMENT_TEXT_CHARS`, 50,000 characters, each) is saved back to its user message and carried in the history of later questions in the same conversation, at most 50,000 characters in total counted from the newest message back; the saved text counts against the attachment quota and is not saved once the quota is reached. Previously the model could not see earlier attachments in follow-up questions.
- "Load older messages" no longer shows duplicates after sending a message.
- The original `gpt-5`, `gpt-5-mini`, and `gpt-5-nano` get `minimal` for `none` and `high` for `xhigh` and `max`; always sending `none` with tools now applies only to `gpt-5.x` (these three models do not accept `none`).
- Looking up a Claude model's output limit no longer holds a global lock, so one slow connection does not make other Claude requests wait.
- `claude-haiku-4-5` no longer gets an effort it does not support (which returned `400`); `max_tokens` sent to Claude is the smaller of the configured output token limit (the API connection's setting, or `ANTHROPIC_MAX_TOKENS` for the system model) and the model's output limit from the Models API (not queried on Foundry), so models with a lower output limit no longer return `400`.
- Only PNG, JPEG, GIF, and WebP chat attachments go to the model as images, and SVG is read as text; other image formats (such as BMP or TIFF) and unreadable attachments (an invalid Office file, or a PDF that is password-protected or has no text) are not read, and the model is told why.
- Deleting a conversation while an answer is streaming no longer writes the assistant message into a newly created orphan conversation; the `done` event's `message_id` is then `null`.
- Removing the `[n]` citation markers of earlier answers from the history no longer touches code blocks and inline code (such as `arr[1]`).
- Setting `name`, `provider`, `api_base`, or `models` to `null` in a connection update returns `400` instead of causing a server error or storing an invalid model list.

#### Frontend

- The profile is read again on load and on every page change, so granting or removing admin rights takes effect without signing in again, and the admin pages check rights against the latest profile.
- Attachments over 15 MiB are rejected with a message as soon as they are selected.
- When an answer stream is interrupted, tool steps still running are marked 「結果不明」 (result unknown) instead of failed, with a reminder to check the result before resending so tools with side effects do not run twice.
- The knowledge base page no longer crashes when a document's `created_at` is null.
- The key hint in the connection form reflects whether the stored key will be kept: after the provider or API address changes, it asks for the key again, and the key becomes required for providers that need one.

#### Deployment and scripts

- A new `.gitattributes` keeps `*.sh` and `frontend/index.html` on LF line endings: Windows working copies with `core.autocrlf=true` converted them to CRLF, so `init-app-role.sh` failed inside the container and the CSP hash of the inline script in `index.html` no longer matched, leaving a blank page.
- `scripts/reset_faiss.py` deletes the indexes at `FAISS_INDEX_PATH`, `METADATA_PATH`, and `BM25_INDEX_DIR` from `.env` instead of hard-coded file names under `backend/data/`.

### Removed

- `scripts/migrate_sqlite_to_postgres.py`, which imported the long-removed `app.models.custom_agent` and could not run.
- Frontend code with no callers: `utils/logger.js`, `utils/offlineCache.jsx`, `utils/motion.js`, the unused exports of `utils/secureLogger.ts`, and `authService.updateProfile`, `authService.isAdmin`, `chatService.getConversations`, and `chatService.getConversation`.
- Backend code with no callers: `get_users`, `deactivate_user`, `activate_user`, `delete_user`, `update_user_role`, and `count_users` in `crud_user`; `TokenRefresh`, `PasswordReset`, and `UserCreate` in `schemas/auth.py`; `RSAKeyManager.load_private_key` and `load_public_key`; `jwt_auth.sanitize_username`; `ChunkStore.delete_ids`; `DocumentProcessor.get_file_info`; and the unused `allow_private_ips` and `allowed_schemes` parameters of the SSRF validation.

---

## [6.0.0] - 2026-10-26

### Security

- **Index metadata is stored as JSON**: the index metadata at `METADATA_PATH` (the last rebuild time and similar) is read and written as JSON, the default file name is now `data/index_metadata.json`, and the backend no longer reads this file with `pickle.load`, so tampering with it cannot run code in the backend (CWE-502). An existing `index_metadata.pkl` is no longer read; the last rebuild time shows as empty until the next index write. The BM25 index directory is still pickled by Whoosh, so `DATA_DIR` must still be writable only by the backend account.
- **Concurrent login requests no longer bypass the failure lockout**: the lockout is checked again after a password-hashing slot is acquired, and failures are recorded before the slot is released. Previously 40 wrong passwords sent at once were all verified, making the threshold useless; now, once locked, at most the 4 requests already being verified complete.
- **Login response time no longer reveals whether an account exists**: unknown and deactivated accounts verify the password against a dummy hash. Previously an existing account took about 76 ms and an unknown one 0.3 ms, so accounts could be listed even with registration closed.
- **The attachment quota can no longer be bypassed with concurrent sends**: messages with attachments check the quota and are written one at a time. Previously concurrent requests all saw the same old usage, so any signed-in account could exceed the 200 MiB limit.
- **Agent Skills trust boundary**: skills are installed by admins and their content reaches the model as instructions, not wrapped in `<untrusted_tool_result>`, but the system prompt says skills cannot override the data-safety and citation rules. Scripts inside skills are not executed by default; the model can only read them. Uploaded zips with absolute paths, `..`, drive letters, or symlinks are rejected, and the limit counts the bytes actually decompressed (`MAX_SKILL_UNCOMPRESSED_BYTES`, 50 MiB); `read_skill_resource` accepts only relative paths to UTF-8 text files inside the skill directory.
- **Skill scripts run only after an admin enables them and the user approves, and they are not sandboxed**: a skill's `allow_scripts` is off by default; once on, every `run_skill_script` call needs approval from the asking user in the chat (unless the skill's `allowed-tools` lists the tool). Scripts run in a temporary copy of the skill directory, inherit only the same minimal environment as `stdio` MCP (backend settings and keys are not passed), and the whole process group is killed on timeout; but they still run as the backend's OS account, can read any file that account can read, and can reach the network, so enable this only for trusted skills.
- **MCP OAuth state and tokens**: `state` is single-use and valid for 10 minutes, and tokens are obtained with PKCE (S256); an MCP server's OAuth settings and tokens are encrypted with `TOOL_SECRETS_KEY` like other tool credentials, and `client_secret` is masked in responses. The OAuth2 `client_secret` of custom API tools is masked too, and the access token and `client_secret` are replaced with `[已遮蔽]` ("redacted") when they appear in tool results.

### Added

- **Responses API**: `gpt-6*` (OpenAI) and Foundry deployments whose names start with `gpt-`, `o3`, or `o4` now use the Responses API, so tool calling works together with reasoning effort and reasoning items are sent back with tool results; other Foundry models (Kimi, Mistral, Grok, DeepSeek, Llama, `gpt-oss`) stay on Chat Completions and get no `reasoning_effort`.
- **Claude on Foundry**: deployments in `FOUNDRY_DEPLOYMENT` starting with `claude-` use `{FOUNDRY_ENDPOINT}/anthropic` (authenticated with `x-api-key`); a `FOUNDRY_ENDPOINT` that is not `*.services.ai.azure.com` fails with a clear error.
- The frontend reasoning levels gain `max`; levels a provider does not support are disabled and downgraded when sent (`xhigh` and `max` become `high` for Claude and Gemini, and `none` becomes `low` for Gemini 3 and later).
- Claude uses prompt caching (the system prompt and the last tool definition) and supports `output_config.effort`.
- Ollama: optional `OLLAMA_NUM_CTX`; when `LLM_API_BASE` points at `ollama.com`, `OLLAMA_API_KEY` is sent as `Authorization: Bearer` (including the model list query).
- Community files: [Contributing](.github/CONTRIBUTING_en.md), [Code of Conduct](.github/CODE_OF_CONDUCT_en.md), [Security Policy](.github/SECURITY_en.md), and [Accessibility Statement](.github/ACCESSIBILITY_en.md), each with a Traditional Chinese version. Security vulnerabilities are reported through GitHub private vulnerability reporting or email, with a first reply within 14 days and public disclosure no later than 90 days after the report; only the latest major version receives security fixes.
- Issue forms in `.github/ISSUE_TEMPLATE/` for bug reports, feature requests, documentation issues, and accessibility barriers, plus links to private security reporting and troubleshooting; a pull request template in `.github/pull_request_template.md` that lists the verification steps and the checks for documentation, the changelog, and intro site sync.
- Structured data is now parsed once by the new `app/services/structured_data/` into rendered text plus a record list; chunking uses the records directly instead of parsing them back out of the text with regular expressions.
  - `.jsonl` uploads are supported (one record per line); YAML is actually parsed with `yaml.safe_load`; CSV and XLSX use the first non-empty row as the header and turn every later row into a record, with row numbers matching the spreadsheet.
  - When the root is an object, each array-of-objects property becomes its own group of records, and the remaining top-level fields form one `【上下文】` (context) record.
  - Records longer than `CHUNK_SIZE` are split on whole field lines into parts that each repeat the record header with a `（2/3）` suffix, with `part` and `part_count` in the metadata.
- The domain profile has two new required fields: `record_label_fields` (label fields for record headers and `label`) and `record_ignore_fields` (fields dropped while parsing).
- Upload results gain `record_count` and `warning` (explaining when a structured format failed to parse or exceeded the limit and was handled as plain text); the rebuild-index response gains `records_detected` and `missing_source_files` (documents whose uploaded file is gone and that were rebuilt from the stored content). The frontend upload dialog and rebuild message show them.
- `MAX_KB_CATALOG_CHARS` (4,000 characters): caps the document catalog (file names and summaries) in the `search_knowledge_base` tool description; past it, only the first documents are listed and the rest are counted.
- `POST /api/documents/rebuild-index` returns `409` when called while a rebuild is running.
- [Agent Skills](https://agentskills.io) support: admins upload skills on the AI Tools page, and the model loads a skill's instructions and reference files on its own when a question calls for it.
  - Upload a `.zip` of the skill directory (`SKILL.md` at the root or inside a single top-level directory; the `.skill` extension is treated as zip) or a single `SKILL.md`. Installs are written to a staging directory and then renamed, and leftover staging directories are removed at startup. A `name` that breaks the spec or a missing `description` is rejected (`400`); other problems (a `name` that differs from the directory name, overlong fields, unknown frontmatter fields, an empty body, and so on) become warnings shown on the card, and the skill still loads.
  - With at least one enabled skill, the model gets two built-in tools, `activate_skill` and `read_skill_resource`: the tool description lists only skill names and descriptions (`MAX_SKILL_CATALOG_CHARS`, 8,000 characters), the `SKILL.md` body and file list arrive only after the model activates a skill, and text files inside the skill are read one at a time when needed; the system prompt also gains a 【技能規則】 (skill rules) section. With no enabled skills, neither the tools nor the rules appear.
  - A message starting with `/skill-name` loads that skill before sending and drops the prefix, and the research trace records an `activate_skill` step; typing `/` in the input lists matching skills (↑/↓ to choose, Enter or Tab to insert, Esc to dismiss).
  - New `/api/skills` endpoints: list enabled skills (any signed-in user), and list, view, upload, enable or disable, and delete skills (admins only); `GET /api/chat/tools` includes the two skill tools when skills are enabled.
  - New required setting `SKILLS_DIR` (the skill file directory, one subdirectory per skill) and table `agent_skills` (created automatically at startup).
  - Admins can turn on `allow_scripts` for a skill: such skills add a `run_skill_script` tool that runs `.py` (the backend's Python, with `-I`), `.sh` (bash), and `.js`/`.mjs` (node, when the interpreter is installed) files inside the skill, returning `exit_code`, `timed_out`, `duration_seconds`, `stdout`, `stderr`, and `output_truncated`; limits on run time, output, arguments, and concurrency are the `MAX_SKILL_SCRIPT_*` constants in the configuration reference.
  - After a skill is activated (by the model or `/skill-name`), the tool names in its `allowed-tools` (the part before any `(`) no longer ask for approval for the rest of that question.
  - Admins can restrict a skill to specific users (`allowed_user_ids`): other users do not see it in their tool list, `/` suggestions, `GET /api/skills/enabled`, or `GET /api/chat/tools`, and cannot activate, read, or run it. New `PATCH /api/skills/{id}/settings` sets both options, and skill objects gain `allow_scripts` and `allowed_user_ids`; `agent_skills` gains matching columns (added automatically at startup).
- Remote MCP servers support OAuth authorization (MCP authorization specification `2025-06-18`): click “OAuth 授權” (OAuth authorize) on an HTTP / SSE server card, and the backend finds the authorization server through `WWW-Authenticate` or `/.well-known/oauth-protected-resource`, uses the admin-entered client or obtains one through dynamic registration (RFC 7591), and gets tokens with the authorization code flow and PKCE, sending `resource` (RFC 8707); later requests carry the Bearer token, which is refreshed with the refresh token when it is about to expire or a connection gets `401`. New `POST /api/mcp/servers/{id}/oauth/start`, `DELETE /api/mcp/servers/{id}/oauth`, and the public callback `GET /api/mcp/oauth/callback`; `mcp_servers` gains `oauth_config` and `oauth_tokens` (added automatically at startup).
- MCP resources and prompts: discovery also reads `resources/list` and `prompts/list` when the server declares the capability, stores them in the new columns `discovered_resources` and `discovered_prompts` (added automatically at startup), and lists them on the server card; the agent gains `read_mcp_resource` and `get_mcp_prompt`, which accept only listed URIs and prompt names and follow the server's `requires_approval`. The lists in the tool descriptions are capped by `MAX_MCP_CATALOG_CHARS` (8,000 characters).
- When `initialize` on an HTTP MCP server returns `400`, `404`, or `405`, the client falls back to the legacy HTTP+SSE transport (a GET opens the SSE stream and waits for the `endpoint` event, whose endpoint must be on the same origin as the SSE URL); when the server ends a Streamable HTTP session with `404`, the client re-initializes once and retries, and closing the connection ends the session with `DELETE`.
- Custom API tools support OAuth2 client credentials (`auth_type` `oauth2_client_credentials`): the access token is fetched from `token_url` and cached until 30 seconds before it expires, and a `401` from the API fetches a new token and retries once; if no token can be obtained, the result is `502` with an error code.
- OpenAPI import reads the spec's `securitySchemes` (3.x) or `securityDefinitions` (2.0) and `security`, and fills each endpoint's `auth_type` and `auth_config` fields (API key name and location, Basic, Bearer, OAuth2 client credentials `token_url` and scopes); the actual credentials are entered by editing the tool after import.
- Custom API tools gain `body_content_type`: the request body can be sent as `application/json`, `application/x-www-form-urlencoded`, or `multipart/form-data` (without files), and OpenAPI import picks it from the spec; `custom_api_tools` gains the column (added automatically at startup, `application/json` for existing tools).
- The intro site gains a 75-second intro video (`site/assets/film/`) with a transcript. Product footage comes from a running AskMiao instance, and the answers on screen were generated by a local Ollama model; background music ducks while the video plays.
- The intro site gains background music and interaction sounds. The sound toggle in the navigation bar is on by default and remembers the choice in `localStorage`; because browsers block autoplay, playback starts after the first click or key press, and pauses while the tab is in the background. The music and sounds are original arrangements made from CC0 samples, shipped as Opus and AAC (`site/assets/audio/`).
- The intro site gains a "Coming next" section covering Agent Skills, MCP updated to the 2025-06-18 spec, OpenAPI import with authentication, the structured data rework, and four security fixes, with a reminder of the settings to add before upgrading.

### Changed

- **The minimum Python version moves from 3.10 to 3.12**: the code already uses 3.12-only syntax, and `requirements.txt` is regenerated with `--python-version 3.12` (dropping the 3.10 and 3.11 specific package versions and markers); an existing 3.10 or 3.11 environment must be replaced with 3.12 before reinstalling the packages.
- **Azure OpenAI is renamed Microsoft Foundry**: the settings become `FOUNDRY_API_KEY`, `FOUNDRY_ENDPOINT`, and `FOUNDRY_DEPLOYMENT`; the old `AZURE_OPENAI_*` names are still read (the new names win when both are set); the internal provider id changes from `azure` to `foundry`.
- Built-in model lists updated: OpenAI adds `gpt-6.1-sol`, Claude adds `claude-sonnet-5-5` and `claude-haiku-5-5`, and Gemini becomes `gemini-4-argon`, `gemini-3.8-flash`, `gemini-3.6-flash`, `gemini-3.5-flash-lite`, `gemini-3.1-flash-lite` (the retired `gemini-3-pro` and the unlisted `gemini-3.5-flash` are removed); `GEMINI_VISION_MODEL` now defaults to `gemini-3.8-flash`.
- `reasoning_effort` is now also sent to Claude (`output_config.effort`), Gemini (mapped to `minimal` through `high`), and Ollama (mapped to `think`), not only to OpenAI and Foundry.
- The README's Contributing section is now a summary; the full rules, including the intro site sync list, moved to `.github/CONTRIBUTING_en.md`.
- Structured record text always uses the original field names, one `key: value` per line, with nested objects flattened into dotted paths (`contact.email`, `items[0].name`) instead of translating fields into Chinese labels for author, content, link, and tags; dates are written in ISO format. Headers read `【記錄 3】`, `【data 記錄 3】`, `【第 5 列】`, or `【工作表1 第 5 列】` depending on the source, followed by the label value.
- Structured formats (JSON, JSONL, YAML, CSV, XLSX) no longer go through Q&A detection; `qa_pairs` and `qa_pairs_detected` count only real Q&A pairs.
- `filter_and_count_records` merges the parts of each record by `(document_id, record_index)` before filtering, so every record counts once; the result fields `author` and `link` became `label` and `links`, and every URL in `links` may be read with `web_fetch`.
- AI summaries of structured data include the record count, format, and field names; rule-based summaries no longer depend on Chinese field labels.
- Base64 images and SVGs inside values are replaced by placeholders while the field is kept; the list of noise fields dropped by name moved from the code to `record_ignore_fields`.
- Rebuilding the index summarizes only documents without a summary and keeps existing summaries, including hand-edited ones; the confirmation dialog now says the knowledge base returns nothing during a rebuild.
- `GET /api/documents/` and `GET /api/admin/documents` return only the fields the lists need (no `content`), run as sync routes in the thread pool, and no longer call the model for documents without a summary during the request.
- Adding documents and `POST /api/admin/vector-store/reindex` compute embeddings outside the index lock, so other people's searches no longer wait while a large file is uploaded or vectors are recomputed.
- `/api/tags` and `/api/chat/models` share one model list and default model rule (`MODEL_NAME`, then the first Azure deployment, then the remote list's default); the remote list is fetched with httpx.
- Deleting an account keeps the documents it uploaded and the tools it created, setting `uploaded_by` and `created_by` to null.
- Password hashing uses `argon2-cffi`'s `PasswordHasher`; the hash format and parameters are unchanged.
- The frontend sends only one access token refresh at a time, shared by axios and chat sends; an expired token is refreshed directly instead of the sign-in state being cleared first.
- The AI Tools page is split into `frontend/src/pages/AiTools/`: the tool lists stay in `index.jsx`, and the five dialogs (OpenAPI import, custom API tool form and test, MCP server form, MCP tool test) are each their own component, mounted only while open; converting between form fields and API data moved to `forms.js`, now with tests. The UI and behavior are unchanged.
- The intro site hero gains a Scorpius constellation (stars light up in turn and carry [1]–[3]; Antares echoes the mascot's red tail) and a clickable mascot. Motion respects `prefers-reduced-motion` and pauses while off screen. The supported upload format count is updated to 28.

### Fixed

- Fixed `gpt-6` and `gpt-5.6` style models being rejected on Chat Completions when tools and reasoning are combined (they now use the Responses API).
- Fixed Claude not seeing failed tool calls as errors (`is_error` is now set), and `pause_turn` and `model_context_window_exceeded` being treated as normal replies.
- Fixed Ollama answers being silently cut off when an error arrives mid-stream, and `think` receiving effort names it does not accept; multi-turn tool calls now send `thinking` back.
- **HTTP MCP servers use Streamable HTTP**: requests send `Accept: application/json, text/event-stream`, SSE responses are accepted, later requests carry the server-issued `Mcp-Session-Id` and `MCP-Protocol-Version`, and `notifications/initialized` is sent after the handshake; the protocol version is now `2025-06-18`. Previously only a JSON POST was sent, so most remote servers built to the current specification could not connect.
- `tools/list` follows `nextCursor` through every page (at most 50), so servers with many tools no longer return only the first page.
- The MCP handshake no longer declares the unimplemented `sampling` and `roots` capabilities; stdio skips server-initiated requests whose id happens to match while waiting for a response.
- OpenAPI endpoints whose spec declares a form body no longer always send the body as JSON.
- The tool form on the AI Tools page saved the API key as `token`, so API key auth set up in the UI never sent the key; the form now shows the fields for each auth type and a body format selector.
- The skill detail `load_error` no longer includes the exception message; it is a fixed message with an error code (CodeQL `py/stack-trace-exposure`).
- Nested objects and arrays in structured data are no longer dropped; JSON objects no longer keep only top-level strings, numbers, and booleans.
- Uploads store the content with surrounding whitespace removed, matching the value the duplicate check compares.
- When cleanup of an admin-uploaded JSON file failed, the second parse no longer bypasses the parse limit.
- The `--uploads` and `--out` defaults of `scripts/docx_to_txt.py` use `/` separators, so on Linux and macOS they are no longer read as a single file name that reports a missing directory.
- The first message sent after staying idle past the access token lifetime no longer fails: chat sends use `fetch`, which never refreshed the token, so they got `401` (or `413` with attachments over 1 MiB) until the page was reloaded.
- Times of conversations, accounts, and documents are no longer 8 hours early: the backend returns times without a time zone, and the frontend now parses them as UTC (`utils/serverDate.ts`).
- A wrong tool argument from the model (such as a `null` or text `top_k`, or arguments that are not an object) no longer ends the whole answer; the model gets an error code instead.
- Rebuilding the index no longer overwrites hand-edited summaries, and two tabs rebuilding at once no longer write every chunk twice.
- With many documents, the knowledge-base catalog no longer adds tens of thousands of characters to every model call or exceeds the model's context window.
- The tool list at the start of a chat is assembled in a worker thread, and the sync document summary no longer calls the model while holding a lock, which could stall the whole backend waiting for it.
- `created_by` of custom API tools and MCP servers was always null; it now records the admin who created them, and deleting an account that created tools or uploaded documents no longer fails on PostgreSQL foreign keys.
- Per-request timeouts on model calls no longer stretch the wait for a connection pool slot from 15 seconds to 18 to 120 seconds.
- `requirements.txt` is regenerated with the command in CONTRIBUTING: Dependabot updates had stripped the platform and Python version markers, so Windows and macOS tried to install Linux-only nvidia packages and Python 3.10 and 3.11 could not install the locked numpy.
- The API reference for `DELETE /api/admin/documents/{document_id}` now matches the behavior: the uploaded file is deleted too.

### Removed

- `DocumentProcessor.split_structured_records`, `_clean_structured_data`, and `_extract_from_code_or_data`, along with the `【設定模組: key】` chunks and the `json_key` and `tags` metadata.
- Code with no callers: `security_monitor.py`, `audit_logger.py`, `batch_processor.py`, `models/payloads.py`, `healthcheck.py` (which checked a nonexistent `/api/admin/stats`), `intrusion_detection.py` (rate-limit `429` responses now just log a warning), `input_validator.py` (its file name check duplicated `documents.py`, and its SSRF check was used only by tests), `ResearchAgent.run_research`, `RAGManager.reset_instance`, the compatibility functions in `redis_client`, unused `security_logging` helpers, and in the frontend `pages/Chat.jsx` (empty), `authService.refreshAccessToken`, `validateToken`, `chatService.sendMessage`, and `networkMonitor.pingServer`.
- The settings `ADMIN_API_KEY` (required, yet no route used it), `ENABLE_BATCH_ACCUMULATION`, `BATCH_ACCUMULATOR_SIZE`, and `BASE_URL`; they are ignored if left in `.env`.
- The agent's tool-turn limit and the `AGENT_MAX_TURNS` setting: the research loop now runs until the model stops calling tools, and the setting is ignored if left in `.env`. If the model keeps calling tools, that question does not end on its own.
- The direct backend dependencies `passlib`, `websockets`, and `requests` (the last two remain indirect dependencies of other packages).
- `raw_result` in MCP tool results, which duplicated `content`.
- The `custom_agents` table, which no feature used, from `init.sql` and the migration script (an existing table in your database is not dropped).

> [!IMPORTANT]
> Before upgrading, add `record_label_fields` and `record_ignore_fields` to the domain profile and `SKILLS_DIR` to `.env`, or the backend will not start, and reinstall the backend packages from the new `requirements.txt`; after upgrading, have an admin run "Rebuild index" once so existing documents switch to the new record format. See the [upgrade guide](docs/upgrading_en.md#upgrading-from-500-to-600).

---

## [5.0.0] - 2026-10-10

This release addresses the findings of a second security audit: chat attachment parsing has a memory budget, failed logins pause the account or source address, a password change revokes every token, self-registration can be turned off, tool credentials are encrypted at rest and no longer readable through the admin API, custom API tools accept only declared parameters, dependencies are pinned by hash, and PostgreSQL is accessed as a non-superuser.

> [!WARNING]
> **This release requires manual changes.** Before upgrading, work through the [upgrade guide](docs/upgrading_en.md#upgrading-from-400-to-500):
>
> - `.env` has 10 new required settings: `ALLOW_REGISTRATION`, `LOGIN_MAX_FAILURES_PER_ACCOUNT`, `LOGIN_MAX_FAILURES_PER_ADDRESS`, `LOGIN_FAILURE_WINDOW_SECONDS`, `LOGIN_LOCKOUT_SECONDS`, `TOOL_SECRETS_KEY`, `HOST`, `RELOAD`, `COOKIE_SECURE`, and `ENABLE_API_DOCS`. The backend does not start if any is missing, and `TOOL_SECRETS_KEY` must be a Fernet key generated for each deployment.
> - `HOST` and `RELOAD` no longer default to `0.0.0.0` and `true`, and `COOKIE_SECURE` is no longer derived from `ENVIRONMENT`; `/docs`, `/redoc`, and `/openapi.json` are served only with `ENABLE_API_DOCS=true`.
> - With `backend/docker-compose.yml`, `POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD` are required and `DATABASE_URL` must use that non-superuser account; for an existing data volume, recreate the container with the new settings and then run `20-app-role.sh` once.
> - stdio MCP subprocesses now run in a fresh empty temporary directory, so paths in `command` and `args` that were relative to the backend's working directory must become absolute.
> - Tool parameters not declared in `parameters_schema` return `400`; `GET /api/external-tags` and the WebSocket `/api/chat/ws/{user_id}` are removed; the `POST /api/api-tools/parse-spec` response no longer includes `raw_spec`.
> - To add or upgrade a backend package, edit `requirements.in` and regenerate `requirements.txt`; JWT handling moved from python-jose to PyJWT, so reinstall the backend packages from the new `requirements.txt`; `bun install` fails when `bun.lock` and `package.json` disagree.
> - After a password change, every session, including the current one, must sign in again with the new password.

### Security

#### Authentication and accounts

- **Login failure throttling**: once one login identifier (case-insensitive) or one source address reaches its failure threshold within `LOGIN_FAILURE_WINDOW_SECONDS`, logins for that identifier or address pause for `LOGIN_LOCKOUT_SECONDS` with `429` and `Retry-After`. Unknown accounts are counted too, the right password is not accepted during a lockout, and the response does not reveal whether the password was correct (CWE-307).
- **A password change revokes every token**: `users` gains `tokens_valid_after`, which is set to the current time on a password change; access and refresh tokens issued before it are rejected. Token `iat` values keep microseconds, so tokens issued earlier in the same second are rejected too, and a stolen refresh token cannot keep renewing after the victim changes their password. `POST /api/auth/change-password` and a `PUT /api/auth/me` that sets a new password clear the refresh token cookie; accounts created while an older version was running, which have no value in this column, are backfilled with `created_at` on every start (CWE-613).
- **Self-registration can be turned off**: with the new required `ALLOW_REGISTRATION` set to false, `POST /api/auth/register` returns `403` and writes a security log entry, and accounts (including the first admin) are created with `scripts/create_user.py`. Previously anyone who could reach the API could register, query the whole knowledge base, and call the enabled tools with the operator's credentials (CWE-284).
- **The admin user API no longer returns password hashes**: `GET /api/admin/users` and `PUT /api/admin/users/{user_id}` filter fields through `UserProfile`, so responses no longer contain `hashed_password` (CWE-200).
- **PyJWT replaces python-jose**: python-jose up to 3.5.0 accepts a DER-encoded public key without PEM armor as an HMAC key, so a verifier that does not restrict algorithms accepts HS256 tokens forged with the server's public key (an incomplete fix for CVE-2024-33663); its dependency ecdsa is subject to the Minerva timing attack on P-256 (CVE-2024-23342). Neither has a patched release. This project already accepts only RS256 when decoding and does not use ECDSA, so neither was exploitable, but both packages came with the install. With PyJWT, python-jose, ecdsa, and rsa, pyasn1, and six (used only by them) are no longer installed, and HS256 tokens signed by hand with a shared string or the PEM or DER public key are all rejected. PyJWT also rejects tokens whose issue time is in the future (CWE-347, CWE-208).
- **Revoked tokens stay revoked until they would have expired**: `revoke_token` computed how long to keep a revoked token as `exp - datetime.utcnow().timestamp()`, and `timestamp()` treats a naive datetime as local time: on a server in a negative UTC offset (for example in the Americas) the result was 0, so the revocation lasted 1 second and a logged-out or rotated access token became usable again; at UTC+8 tokens were kept 8 hours longer than needed. It now uses `time.time()` (CWE-613).
- **Logout works with an expired access token**: `POST /api/auth/logout` verifies only the access token's signature, so it still revokes the refresh token and clears the cookie after the access token expires; the `Authorization` header is still required, so a cross-site form cannot trigger a logout (CWE-613).
- Admin changes to an account's role or status and account deletions are written to the security log (`ADMIN_USER_UPDATED`, `ADMIN_USER_DELETED`) with the acting admin and the changes (CWE-778).
- The JWT private key is created with mode `0600` from the start instead of being written with default permissions and changed afterwards; a newly created `backend/keys/` is `0700` (CWE-276).

#### Deployment and dependencies

- **PostgreSQL is accessed as a non-superuser**: `docker-compose.yml` requires `POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD`, and `backend/init-app-role.sh` runs after `init.sql` to create the account, grant `USAGE` and `CREATE` on the `public` schema, and hand it ownership of existing tables. A SQL injection can no longer run system commands with `COPY ... TO PROGRAM` or read server files (CWE-250).
- **Insecure defaults are now required settings**: `HOST`, `RELOAD`, and `COOKIE_SECURE` no longer default to listening on all interfaces, auto-reloading, or deriving Secure from `ENVIRONMENT`; the new required `ENABLE_API_DOCS` turns off the interactive documentation that lists every endpoint and parameter (CWE-1188).
- **Dependencies are pinned by hash**: `backend/requirements.in` lists only direct dependencies, and `requirements.txt` is generated with `uv pip compile --universal --generate-hashes` and verified on install; `frontend/bun.lock` is committed and `frozenLockfile = true`. Previously neither side pinned versions, so every install took the newest release available at the time (CWE-1357, CWE-494).
- Removed `GET /api/external-tags`, which needed no login, was not cached, and relayed upstream JSON as is, and the WebSocket `/api/chat/ws/{user_id}`, which needed no authentication and bypassed rate limiting; the frontend used neither (CWE-306).
- The larger upload body limit applies only to requests whose token carries `is_admin`, so regular users cannot make the backend parse a multipart body of about 500 MiB; the rate limiter tracks a bounded number of addresses and evicts the least recently active first (CWE-770).

#### Tool credentials and outbound requests

- **Tool credentials are encrypted at rest**: custom API tools' `headers` and `auth_config` and MCP servers' `env_vars` and `headers` are encrypted with `TOOL_SECRETS_KEY` (Fernet) before they reach the database, and existing plaintext rows are encrypted at startup. Admin API responses show `••••••••` in place of secret values, and fields sent back masked keep their stored value on update. They used to be stored in plaintext and returned as is (CWE-312, CWE-522).
- **Custom API tools accept only declared parameters**: parameters must be declared in `parameters_schema`, and body fields are checked too when `request_body` has a schema with declared properties. Query parameters in the tool URL are fixed by the admin, and a call that supplies a parameter with the same name is rejected. Previously every key from the model was sent, and on httpx 0.28 any query parameter replaced the fixed parameters in the URL entirely (CWE-20, CWE-915).
- **Redirects are followed manually**: custom API tools and HTTP MCP never read the body of a redirect response, and the whole call has a deadline (custom API tools return `504` when it passes, HTTP MCP returns a tool error with an error ID); HTTP MCP follows only same-origin redirects, so admin-configured headers and the JSON-RPC body are never sent to another domain (CWE-200, CWE-400).
- **MCP subprocesses and errors**: stdio subprocesses run in a fresh empty temporary directory, waiting for a free slot has a timeout, stderr is drained continuously, and a single message line is capped at 4 MiB; only tools whose names match `[A-Za-z0-9_.-]{1,128}` are kept; tool failures return only an error ID, and startup failures no longer include the command's arguments (CWE-400, CWE-209).
- User-supplied URLs (`web_fetch`) and admin-configured endpoints use separate DNS thread pools, so a slow domain cannot stall the SSRF checks for tools and spec imports; the SSRF deny list explicitly covers 6to4 (`2002::/16`) and NAT64 local-use (`64:ff9b:1::/48`) (CWE-400, CWE-918).
- Fixed query parameter values in a tool URL (which may be keys written into the URL) no longer appear in URLs returned to the model and the user; the `approval_required` event gains `target`, which names where the request is actually sent (CWE-200).
- OpenAPI specs with YAML aliases are rejected: the event stream is checked first (syntax only, no objects are built), and only a spec without aliases is loaded with `yaml.safe_load`; the parse result no longer carries the whole raw spec (CWE-776, CWE-502).

#### Resource limits

- **A parsing budget for chat attachments**: admin uploads and chat attachments each use their own `ExtractionLimits`. For chat attachments, the XML parts of a docx or pptx that are built into a DOM, counted from `[Content_Types].xml` so renaming does not bypass the check, are capped at 8 MiB; the total uncompressed size is capped at 64 MiB and the member count at 10,000, and the compression ratio is checked for the whole file as well as for each member. JSON and code over 2,000,000 characters are not passed to `json.loads`. At most 2 attachments are parsed at a time per process, and an attachment over budget is reported to the model as unread (CWE-409, CWE-400).
- The separator pattern in `split_structured_records` now runs in linear time (CWE-1333).

#### Frontend

- **The build ships a CSP**: `bun run build` writes a CSP `<meta>` tag into `index.html` that allows only the built scripts and the hashes of the inline scripts in `index.html`, adds the API origin from `VITE_API_BASE`/`VITE_API_URL` to `connect-src`, and allows images only from the same origin, `data:`, and `blob:`. Even when the web server sets no CSP, injected HTML cannot run scripts (CWE-79).
- **The tool approval card shows everything**: it lists where the request is sent and every parameter, no longer inside a scrolling box, and marks control and format characters (bidirectional controls, zero-width characters, Unicode tag characters, and so on) as `⟦U+…⟧` (CWE-451).
- **External links show the real site**: whether a link is external is decided from the resolved URL; external links open in a new tab and name the actual host, a Markdown `title` cannot replace the URL hint, and external links no longer get the in-app action button style (CWE-451).
- Failed requests log only the status code and error message to the console, not the axios error object with passwords, API keys, and access tokens (CWE-532).
- When the logout request fails, the login page says so: the server did not revoke the refresh token, and the httpOnly cookie holding it can still obtain access tokens until it expires (CWE-613).
- **Markdown autolinks no longer freeze the chat page**: remark-gfm's autolink transform (mdast-util-gfm-autolink-literal 2.0.1, the latest release) takes time quadratic in length on a long run of dots, hyphens, underscores, or plus signs, or on repeated `www.`; 50,000 characters took about 2.6 seconds, during which the chat page stopped responding, and it happened again every time the conversation was opened. Answers now use `remarkGfmSafe`, which reuses remark-gfm but estimates each text node's scan cost in linear time before the transform and skips autolinking in nodes over the limit; everything else renders exactly as with remark-gfm, and the same input takes about 0.03 seconds (CWE-1333).
- Research trace arguments and output previews are always rendered as text, so an object from the model no longer crashes the conversation page (the trace is stored in the database, so the page used to crash every time the conversation was opened); the post author field no longer uses a pattern that backtracks in quadratic time on a long run of dots (CWE-1333).

### Added

- Required settings `ALLOW_REGISTRATION`, `LOGIN_MAX_FAILURES_PER_ACCOUNT`, `LOGIN_MAX_FAILURES_PER_ADDRESS`, `LOGIN_FAILURE_WINDOW_SECONDS`, `LOGIN_LOCKOUT_SECONDS`, `TOOL_SECRETS_KEY`, `HOST`, `RELOAD`, `COOKIE_SECURE`, and `ENABLE_API_DOCS`; `POSTGRES_APP_USER` and `POSTGRES_APP_PASSWORD` in `docker-compose.yml`.
- `GET /api/auth/registration` reports whether self-registration is open; the frontend uses it to hide the sign-up link on the login page and shows an explanation on the sign-up page.
- `backend/scripts/create_user.py` creates an account with an interactively entered password, applying the same rules as registration; `--admin` creates an admin.
- `backend/init-app-role.sh` (the PostgreSQL application account, safe to rerun), `backend/requirements.in`, and `frontend/bun.lock`.
- Tool and MCP server responses from the admin API gain `credentials_unreadable`, so credentials that cannot be decrypted with the current key can be re-entered instead of breaking the page; meanwhile the tool test and MCP discover endpoints return `400` saying the credentials must be entered again, and the AI tools page shows a notice on the card and in the edit dialog.
- The quick starts in the README and on the website now generate `TOOL_SECRETS_KEY`, create the first admin with `scripts/create_user.py`, and list all 20 required settings; the [upgrade guide](docs/upgrading_en.md#upgrading-from-400-to-500) covers this release.
- New backend tests `test_admin_user_api.py`, `test_login_throttle.py`, `test_registration.py`, and `test_tool_secrets.py`, and the frontend test `remarkGfmSafe.test.tsx`.
- **"Tool approval" section on the website**: an interactive approval card (approve, deny, simulate a timeout) that shows the resulting SSE events such as `approval_required` and `approval_resolved`, plus a switch between HTTP methods that shows a custom API tool's default approval rule, matching `tool_approval.py`.
- The website gains a 4.0.0 release pill and stats row, a "Every entry point has a limit" resource-limit table in the security section, and ADR-0006 in the documentation list.
- The README gains "What's new in 4.0.0", "Tool call approval", "Threat coverage", and "Key resource limits" sections, and two troubleshooting entries on approval timeouts and read-only tools asking for approval.
- **"5.0.0" release section on the website**: an interactive login-throttling demo (wrong passwords, an identifier in different case, a nonexistent account, and many accounts tried in turn, with counting, lockout, and `429`/`Retry-After` responses matching `login_throttle.py`), a password-change demo that compares each token's `iat` with `tokens_valid_after` (including a token issued earlier in the same second), and one set of tool credentials as stored in the database, returned by the admin API, and sent in the real request; plus the other fixes and the six steps for upgrading from 4.0.0. The navigation bar, the hero release pill, and the version timeline all point to 5.0.0.
- The README gains a "What's new in 5.0.0" section.

### Changed

- Visual refresh of the website: the hero gains a slowly drifting brand-blue glow and, on desktop, a screenshot that tilts slightly with the pointer; the navigation bar shows scroll progress; cards in the features, defenses, and release sections get a border glow that follows the pointer. All motion respects `prefers-reduced-motion`, and browsers without scroll-driven animations show the static page. The dark palette in `site/styles.css` is now defined once as `--night-*` and shared by the dark theme and the release panel, which is dark in both themes.
- A password change also signs out the current session; the frontend clears the sign-in state and returns to the login page.
- The `iat` of access and refresh tokens is now a fractional number with microseconds (RFC 7519 NumericDate allows fractions); clients that decode tokens themselves should not assume it is an integer.
- Custom API tools that declare no parameters no longer accept any; the `POST /api/api-tools/parse-spec` response no longer includes `raw_spec`.
- Tool and MCP credentials in admin API responses are shown as `••••••••`; ordinary headers such as `Accept` and `Content-Type` and settings such as `key_name` and `username` are shown as before. After changing `TOOL_SECRETS_KEY`, stored credentials must be entered again.
- Intrusion detection now only raises alerts; `RateLimitMiddleware` no longer has a blocking branch that returns `403`.
- stdio MCP subprocesses no longer run in the backend's working directory, so relative paths must become absolute; HTTP MCP follows only same-origin redirects.
- To add or upgrade a frontend package, temporarily set `frozenLockfile` to `false` in `frontend/bunfig.toml`, update with `bun add`/`bun remove`, set it back to `true`, and commit `package.json` and `bun.lock` together.
- `backend/.env.example` adds the required settings above and its `DATABASE_URL` example uses `askmiao_app`; `frontend/.env.example` notes that `VITE_API_BASE` is written into the CSP `connect-src`.

### Removed

- `GET /api/external-tags` and the WebSocket `/api/chat/ws/{user_id}`.
- The intrusion detection IP blocklist, which was never populated.
- The unused `app/core/secret_manager.py`, which silently fell back to a random key when its key was missing, and the unused `reject_unsafe_request`, which did not pin the connection IP.
- Backend packages no code used: FlagEmbedding, waitress, docxtpl, XlsxWriter, langchain, and langchain-community.
- python-jose (replaced by PyJWT), and ecdsa, rsa, pyasn1, and six, which only it used.

### Fixed

- Installing from `requirements.txt` paired an old datasets release pulled in by FlagEmbedding with a new pyarrow, so sentence-transformers failed to import; pydantic-settings, PyYAML, and lxml, previously installed only as transitive dependencies, are now direct dependencies.
- `cache = "~/.bun/install/cache"` in `bunfig.toml` did not expand `~` and created a cache directory literally named `~` under `frontend/`, whose third-party tests vitest then picked up.
- The website's web_fetch inspector now matches URL provenance on the full normalized URL, as `research_session.py` does; it used to match a decoded substring, which counted fragments of a URL as having appeared.
- The website no longer mentions the removed `JWT_SECRET_KEY` (quick start, required settings, and the subprocess environment table) and explains RSA keys, `POSTGRES_PASSWORD`, and the local-only dev server instead; the security notes now cover IP pinning and tokens resolved to database accounts.

---

## [4.0.0] - 2026-09-27

This release addresses the 52 leads from a security audit: tokens are mapped to the database account on every request, tool calls with side effects need the user's approval, outbound connections are pinned to the SSRF-validated IP, and request bodies, attachments, tool results, concurrent streams, and other resources are capped.

> [!WARNING]
> **This release needs manual steps**; go through the [upgrade guide](docs/upgrading_en.md#upgrading-from-300-to-400) before upgrading:
>
> - `JWT_SECRET_KEY` and `JWT_ALGORITHM` are gone; the RSA keys in `backend/keys/` are required in every environment, and the backend refuses to start if they cannot be loaded or generated.
> - `backend/docker-compose.yml` requires `POSTGRES_PASSWORD` and binds `127.0.0.1:7690` only; the password of an existing data volume must be changed separately.
> - The Vite dev and preview servers listen on `localhost` only; LAN devices need a production build behind a real web server.
> - `/api/chat` message responses no longer include the raw `context_used` (always `null`); `GET /api/chat/tools` requires sign-in; `model_name` must be in the available model list.
> - Custom API tools and MCP servers gain `requires_approval` (added and backfilled at startup), so calls to existing MCP servers' tools now ask the user for approval first.

### Security

#### Authentication

- **HS256 fallback removed**: development setups no longer sign tokens with the shared secret from `.env` when the RSA keys cannot load; the keys must be usable in every environment, or the backend refuses to start (CWE-1188).
- **Tokens bound to the database account**: every request loads the account by `sub`; it must exist and be active, `is_admin` and the role come from the database rather than the token, and tokens issued before the account was created (a deleted account's id reused) are rejected, so deactivation, deletion, and demotion apply immediately (CWE-613, CWE-285). New SQLite databases create `users` and `documents` with `AUTOINCREMENT`, so ids are never reused.
- **Single-use refresh tokens**: the old token is revoked as soon as a new pair is issued (CWE-294).
- Passwords are capped at 256 characters and login identifiers at 254; Argon2 hashing and verification run in worker threads, at most 4 at once; the revocation list holds at most 100,000 entries (CWE-400).

#### Deployment

- **No built-in PostgreSQL password**: `POSTGRES_PASSWORD` is required, and the port binds `127.0.0.1:7690` only (CWE-798, CWE-1327).
- **Client-supplied `X-Forwarded-For` is not trusted**: `python main.py` turns uvicorn's `proxy_headers` off by default, so rate limiting and the block list use the direct peer; only reverse proxies named in the new `FORWARDED_ALLOW_IPS` setting are trusted (CWE-348).
- **Vite dev server for this machine only**: the dev and preview servers listen on `localhost` only, and `/__open-in-editor` answers loopback clients only (CWE-1327); both send `X-Frame-Options: DENY` and `Content-Security-Policy: frame-ancestors 'none'; img-src 'self' data: blob:`, and `index.html` adds an anti-framing style guard (CWE-1021).

#### Tools and outbound requests

- **Approval before calls**: custom API and MCP tools with side effects run only after the asking user approves in the chat; see Added below (CWE-862).
- **SSRF validation pins the connection IP**: custom API tools, the MCP HTTP transport, and `safe_fetch_text` pin every hop to the approved IP after validation, so DNS rebinding cannot change the target between validation and connection; DNS lookups run in a dedicated 4-thread pool with a 5-second timeout (CWE-918, CWE-367).
- **Custom API tools**: path parameters are percent-encoded and the host after substitution must match the configured one; cross-origin redirects drop the admin-configured headers and auth header; credential values in results and URLs are masked as `[已遮蔽]`; response bodies are capped at 1 MiB (CWE-918, CWE-522, CWE-200, CWE-400).
- **SSRF rejections return only an error code**: custom API tools, `web_fetch`, and `POST /api/api-tools/parse-spec` no longer return reasons that may contain intranet IPs; MCP HTTP errors no longer include the peer's response body, and one response is capped at 4 MiB (CWE-209, CWE-400).
- **Stricter `web_fetch` URL provenance**: only URLs that appeared as a whole URL count, both sides are normalized by httpx and compared exactly, and the matched URL is what gets fetched (CWE-918).
- **MCP presets**: `mcp_fetch`, which bypassed `web_fetch`'s outbound protections, is removed; `mcp_filesystem` is rooted at the dedicated `backend/mcp_filesystem_sandbox` (instead of `./data`, which holds pickled index metadata) and pins `@modelcontextprotocol/server-filesystem@2026.8.31` (CWE-918, CWE-552, CWE-829).
- **MCP subprocesses**: each runs in its own process group, closing it terminates the whole tree, and at most 4 run at once (CWE-404, CWE-400).
- **Chat attachments accept base64 `data:` URLs only**, so remote URLs are no longer handed to model providers to fetch (CWE-918); Markdown images in answers become links that open only when clicked instead of loading from external hosts automatically (CWE-201).
- The `httpx` and `httpcore` loggers are pinned to `WARNING`, so full URLs with query-string keys are no longer logged (CWE-532).

#### Resource limits

- New `RequestBodyLimitMiddleware`: request bodies are capped at 1 MiB, raised for chat sends and document uploads only with a valid access token; larger bodies get `413` (CWE-770).
- Chat messages are capped at 20,000 characters and 5 attachments (15 MiB each, 20 MiB in total), and attachment text and tool results are truncated before reaching the model; each user may store 200 MiB of attachments (`413`) and run 2 answer streams at once (`429`); PDF chat attachments are OCR'd for at most 20 pages at no more than 25 MP per page; waiting for the LLM connection pool is capped at 15 seconds (CWE-400, CWE-770).
- OOXML files have their uncompressed size and compression ratio checked before parsing (CWE-409); HTML extraction, SVG stripping, JSON declaration extraction, Q&A splitting, and table-of-contents cleanup run in linear time, and `filter_and_count_records` limits its date range and result count (CWE-1333).
- The conversation list returns at most 200 conversations with 5 preview messages each and no attachment bodies; one conversation returns at most its latest 500 messages; the remote model list is cached for 30 seconds and queried in a worker thread (CWE-400).
- Security log fields are capped at 200 characters, `app.log` and `security.log` rotate at 10 MiB × 5 files, and security events are no longer duplicated into `app.log`; the intrusion detector bounds its events and tracked addresses (CWE-779, CWE-400).

#### Other

- **`send` only accepts listed models**, so nobody can call an unlisted model with the operator's keys (CWE-770); `GET /api/chat/tools` now requires sign-in (CWE-200).
- The jieba dictionary cache moved to `DATA_DIR/jieba_cache` (mode `0700`) instead of a predictable file name in the system temp directory (CWE-377).
- **MCP SSRF rejections no longer echo resolution results**: when the SSRF guard rejects the URL while creating or discovering an MCP server, `last_error` and the 400 response now say it was rejected and carry an error code; the full reason, which can include private IPs from server-side DNS resolution or redirect targets, goes only to the server log (CWE-209).
- **Intro page RRF demo escapes chunk IDs**: `site/main.js` now passes chunk IDs and reranker probabilities from the embedded JSON through `escapeHtml` before inserting them into HTML, so quotes or angle brackets in the data are no longer parsed as markup (CWE-79).

### Added

- **Tool call approval**: custom API tools and MCP servers gain `requires_approval` (API tools default by HTTP method, `true` for anything other than `GET`, `HEAD`, and `OPTIONS`; MCP servers default to `true`). When the agent calls such a tool it sends the SSE event `approval_required` and pauses; once the user answers through `POST /api/chat/approvals/{approval_id}`, it sends `approval_resolved`. Only the asking user can answer, and nothing runs after a 300-second timeout or without an approver. The frontend shows a confirmation card in the answer, and the AI tools page forms gain a matching checkbox. See [ADR-0006](docs/adr/0006-tool-call-approval_en.md).
- `FORWARDED_ALLOW_IPS` setting: names reverse proxies that overwrite `X-Forwarded-For`, so rate limiting counts real client IPs.
- `backend/app/core/limits.py` defines the resource limits in one place, documented in a new "Resource limits" section of the [configuration reference](docs/configuration_en.md#resource-limits).
- `upgrade_schema()`: adds new columns to existing tables and backfills them at startup (and in `init_db.py`).
- When sending a message fails with a `422` validation error, the frontend shows each reason (for example an oversized attachment).
- New [ADR-0006](docs/adr/0006-tool-call-approval_en.md) and follow-up amendments to ADR-0004; the [upgrade guide](docs/upgrading_en.md#upgrading-from-300-to-400) covers this release.
- New backend tests `test_auth_token_binding.py`, `test_outbound_tool_security.py`, `test_process_hardening.py`, `test_resource_limits.py`, and `test_tool_approval.py`.

### Changed

- `/api/chat` message responses no longer include the raw `context_used` (always `null`); the parsed `sources`, `sources_detail`, `research_trace`, and `attachments` carry the data, and attachments in the conversation list have no `data_url`.
- During a chat stream the database connection goes back to the pool, and database access plus attachment decoding and parsing run in worker threads; conversation read routes are now sync functions run in the thread pool.
- Custom API tools, the MCP HTTP transport, and `web_fetch`'s direct fetches no longer use the `HTTP_PROXY` and `HTTPS_PROXY` environment variables.
- PDF OCR rasterizes pages one at a time on the document's thread, with only the vision calls in parallel; XLSX files are opened read-only.
- Deleting a document removes its database record before its index chunks, and index writes skip chunks whose document was deleted after taking the lock.
- `backend/.env.example`: `JWT_SECRET_KEY` and `JWT_ALGORITHM` removed; `POSTGRES_PASSWORD` and `FORWARDED_ALLOW_IPS` examples added.

### Removed

- The `JWT_SECRET_KEY` and `JWT_ALGORITHM` settings and the HS256 signing path (ignored if left in `.env`).
- The `mcp_fetch` MCP preset (`uvx mcp-server-fetch`).

### Fixed

- `POST /api/auth/refresh` read a `user_id` claim that does not exist, so every exchange failed; it now maps the account by `sub`.
- A document deletion racing an index write could write the deleted document's chunks back into the knowledge base (CWE-362).
- SQLite reused the ids of deleted users and documents, so old tokens or chunks could map to new rows.

---

## [3.0.0] - 2026-09-25

This release turns "where did this answer come from" into a verifiable chain: chunks are keyed by a database chunk_id, retrieval fuses tracks with RRF and judges relevance by the reranker probability, and answers cite the sources they actually used as `[n]`. It also adds a trust boundary for tool output, restricts tool management to admins, and overhauls the frontend experience.

> [!WARNING]
> **This release contains breaking changes.** Follow the [upgrade guide](docs/upgrading_en.md) before upgrading:
>
> - `.env` gains 8 required settings: `ENABLE_WEB_SEARCH`, `AGENT_MAX_TURNS`, `CONVERSATION_HISTORY_MESSAGES`, `RRF_K`, `RERANK_RELEVANCE_THRESHOLD`, `WEB_FETCH_ALLOWED_DOMAINS`, `BLOCK_WEB_TOOLS_AFTER_KB`, and `DOMAIN_PROFILE_PATH`. The backend refuses to start if any is missing; Claude models also need `ANTHROPIC_MAX_TOKENS`.
> - Indexes are keyed by chunk_id: the old FAISS index is renamed to `faiss_index.bin.legacy.bak` on first startup, and the index must be rebuilt once before existing documents are searchable again.
> - The reranker is a required component; the backend refuses to start if the model cannot load.
> - The AI tools page and every endpoint under `/api/api-tools` and `/api/mcp` are admin-only; MCP `stdio` subprocesses no longer inherit the backend environment; MCP HTTP servers on loopback or private addresses are rejected.
> - Several settings were removed, `HF_HOME` no longer has a default, the default models changed, and the `/api/admin/rag-config` response fields changed (see the sections below).

### Added

#### Retrieval and indexing

- **Database-backed chunk index**: a new `rag_chunks` table is the single source of truth for chunks; FAISS now uses `IndexIDMap2(IndexFlatIP)`, and both FAISS and BM25 are keyed by chunk_id. At startup the backend reconciles the indexes against the database: it deletes orphaned chunks, removes stale vectors, embeds missing ones, and rebuilds BM25 when it disagrees with the database. See [ADR-0005](docs/adr/0005-chunk-id-index-and-database-source-of-truth_en.md).
- **RRF fusion and relevance threshold**: vector search and BM25 always both run and are merged by rank with standard RRF (`RRF_K`); `RERANK_RELEVANCE_THRESHOLD` applies directly to the reranker probability, exact URL, post ID, and date matches are exempt, and when nothing passes the tool reports that the knowledge base has nothing relevant. See [ADR-0003](docs/adr/0003-rrf-relevance-citations-and-tool-trust_en.md).
- **Domain profile**: new `backend/config/domain_profile.json` and `DOMAIN_PROFILE_PATH` hold domain words, record date fields, and summary fallback rules, validated at startup; the optional `JIEBA_DICTIONARY` replaces the jieba main dictionary.
- **Retrieval evaluation CLI**: `scripts/evaluate_retrieval.py` computes hit@k, recall@k, and MRR read-only on a copy of the index, and `--min-mrr` works as a CI gate; golden sets accept negatives with `"relevant_sources": []`, and `--relevance-thresholds` compares several thresholds over one rerank pass (positive hit rate and negative rejection rate).

#### Agent and models

- **Citations mapped to sources**: each question builds a citation table (`app/rag/research_session.py`), answers cite evidence as `[n]`, and `sources_detail` lists only the cited entries with a `citation` number; frontend badges now read like "[2] 員工手冊.pdf（段落 3）".
- **Tool calling on all five providers**: `llm_client.py` unifies OpenAI, Azure OpenAI, Anthropic Claude (official `anthropic` SDK), Google Gemini (OpenAI-compatible endpoint), and Ollama, with consistent tool calling and streaming behavior.
- Ollama generation options `OLLAMA_TEMPERATURE` and `OLLAMA_NUM_PREDICT` (optional; model defaults apply when unset).

#### Frontend

- **Stop and retry**: answers can be stopped while streaming (a stopped answer is not saved) and the input stays usable during streaming; failed answers show the reason and a retry button, and a message that fails before streaming starts puts its text and attachments back into the input.
- **Appearance switch**: the account menu offers light, dark, and follow-system themes, defaulting to the system setting and applied before first paint, so dark mode no longer flashes white.
- **Confirm before deleting**: deleting conversations, users, documents, custom API tools, and MCP servers, clearing the upload list, and overwriting an edited summary now ask for confirmation (`ConfirmDialog`).
- The chat page adds a jump-to-latest button and announces completed, failed, or stopped answers to screen readers; new offline and back-online notices, a skip link, and a "no permission" page for non-admins on admin pages instead of a native `alert()`.
- `frontend/src/services/sse.ts`: a spec-compliant SSE parser with 8 Vitest tests (events split across reads, CRLF, multi-line data, and more).

#### Documentation and tests

- New [configuration reference](docs/configuration_en.md) (every environment variable explained) and [upgrade guide](docs/upgrading_en.md); new [ADR-0003](docs/adr/0003-rrf-relevance-citations-and-tool-trust_en.md), [ADR-0004](docs/adr/0004-tool-admin-permissions-and-subprocess-isolation_en.md), and [ADR-0005](docs/adr/0005-chunk-id-index-and-database-source-of-truth_en.md).
- 13 new backend test files covering index consistency, RRF and the relevance threshold, citation numbering, agent guardrails, tool calling per provider, conversation history, settings validation, the uploads watcher, and tool management permissions.

### Changed

#### Retrieval and indexing

- Deleting a document removes only that document's chunks and vectors instead of re-embedding everything.
- Retrieval and index writes run in worker threads and no longer block the event loop; reads and writes of chunks, FAISS, and BM25 share one lock.
- The reranker is a required component: the backend refuses to start if it cannot load, and a reranking failure at query time returns an error code instead of unfiltered chunks.
- `search_knowledge_base` with `target_document` restricts candidates before reranking and no longer falls back to the whole library.
- BM25 queries are built from analyzer tokens combined with OR; tokens are always lowercased; the index directory records a tokenizer signature, BM25 is rebuilt automatically on a mismatch (vectors are not recomputed), and read-only evaluation refuses to run.
- Relative path settings (`DATA_DIR`, `UPLOAD_DIR`, index paths, `HF_*`, `DOMAIN_PROFILE_PATH`, `JIEBA_DICTIONARY`) are always resolved against `backend/`.
- Hugging Face settings (`HF_HOME`, `HF_HUB_CACHE`, `SENTENCE_TRANSFORMERS_HOME`, `HF_HUB_OFFLINE`, `HF_HUB_DISABLE_SYMLINKS_WARNING`) are exported to the environment before any model loads; `HF_HOME` no longer defaults to `./data/hf_home` and falls back to the library default `~/.cache/huggingface`.
- The `RERANK_TOP_K` example value in `.env.example` changed from 50 to 20.
- `/api/admin/rag-config` now returns `rrf_k` and `rerank_relevance_threshold` and drops `hybrid_alpha`, `final_threshold`, and `normalization`.

#### Agent and models

- When the model stops calling tools, its answer is used as is instead of being regenerated, and fake streaming is removed; the answer is streamed from a fresh call only when the turn limit is reached or the model returns empty content.
- Conversation history is loaded from the database (the latest `CONVERSATION_HISTORY_MESSAGES` messages), so restarts no longer lose context; `[n]` markers from earlier answers are stripped first so old numbers are not reused.
- `ENABLE_WEB_SEARCH` and `AGENT_MAX_TURNS` are required; with `ENABLE_WEB_SEARCH=false`, `web_search` and `web_fetch` are left out of the tool list.
- Default models updated: `OPENAI_VISION_MODEL` changes from `gpt-4o` to `gpt-6-sol` and `GEMINI_VISION_MODEL` from `gemini-2.5-flash` to `gemini-3.5-flash`; Azure without `AZURE_OPENAI_DEPLOYMENT` now lists `gpt-6-sol`; the built-in model lists now cover GPT-6 / GPT-5.6, Claude Opus 5.5 / Fable 5.1 / Sonnet 5, and Gemini 3.x.

#### Frontend and interface

- Dialogs, the mobile conversation list, and the image viewer use the native `<dialog>`: Esc closes them, the background is inert, and focus returns to the button that opened them; the account menu supports arrow keys.
- The mobile top bar is a single 64px row and the chat page fits one viewport height; buttons and inputs are larger on touch devices, and inputs use 16px text so iPhones no longer zoom in on focus.
- Secondary text, status colors, and dark-mode primary buttons were recolored to meet WCAG AA contrast.
- The brand reads AskMiao everywhere, each page has its own title, and the navigation uses links that mark the current page.
- Message times include the date when not sent today; source relevance is shown as a percentage.
- Frontend text and backend messages use Taiwan Mandarin terms (for example 使用者名稱, 電子郵件, 字元, 權杖), and accessibility labels no longer mix in English.
- The favicon now uses 32px and 64px versions, so visitors no longer download the 4.5 MB 2048px original (which stays as the source of the `site/assets` icons).

#### Versioning and documentation

- The version is 3.0.0 everywhere: the backend reads it from `__version__` in `backend/app/__init__.py`, which both the OpenAPI document and the MCP handshake `clientInfo` use; the frontend `package.json` matches; the OpenAPI title is now "AskMiao API".
- The README, API reference, architecture document, and `llms.txt` were rewritten for 3.0.0 in both languages, fixing statements that did not match the code, such as `init_db.py` creating an admin account (it does not), the list of supported knowledge-base file extensions, and the environment variables the frontend actually reads.
- `frontend/.env.example` keeps only the variables the frontend reads, dropping the removed workflow WebSocket URL and backend-only settings.
- The intro site (`site/`) was redesigned around the current implementation: its interactive demos reproduce citation numbering, RRF with the relevance threshold, URL provenance, the SSRF check order, and MCP environment inheritance in the browser, and the screenshots show the new brand.

### Removed

- The `HYBRID_ALPHA`, `NORMALIZATION`, and `FINAL_THRESHOLD` settings and `auto_tune_alpha` (ignored if left in `.env`); query-type routing and the hard-coded FAQ keyword check.
- The daily automatic reindex task (`tasks/index_rebuilder.py`) and the `ENABLE_AUTO_REINDEX`, `ENABLE_AUTO_REINDEX_TASK`, and `REINDEX_HOURS` settings.
- The `DOCUMENTS_PATH` (`documents.pkl`), `TRANSFORMERS_CACHE`, and `HUGGINGFACE_HUB_CACHE` settings; use `HF_HOME` or `HF_HUB_CACHE` for the Hugging Face cache.
- `gpt-5.5`, `gpt-5.2`, `gpt-4o`, `gpt-4o-mini`, `o1`, `o3`, `o3-mini`, and `gemini-2.5-flash` from the built-in model lists; list them in `AVAILABLE_MODELS` to keep using them.
- The hidden auto-loading of `data/jieba_dict.txt`; custom words now always live in the domain profile.
- The `documents_update` WebSocket notification sent by the uploads watcher, which the frontend never received.
- The frontend `dompurify` dependency: react-markdown already refuses to render raw HTML, and the extra pass rewrote answer content.

### Fixed

#### Retrieval and agent

- FAISS, `documents.pkl`, and BM25 were aligned by list position, so deleting documents, rebuilding, load failures, and concurrent writes shifted chunks out of alignment.
- The `AGENT_MAX_TURNS` and `ENABLE_WEB_SEARCH` settings had no effect.
- Reranker scores went through sigmoid twice, squeezing probabilities into the 0.5 to 0.73 range where they could not judge relevance.
- BM25 parsed the whole question with the Whoosh query syntax (AND by default), so multi-word queries often found nothing and punctuation was read as query syntax.
- The relevance threshold applied to the mixed score, so the top candidate always scored 0.15 and passed, and at least one irrelevant chunk always reached the model.
- Chunks found only by BM25 never reached the rerank candidates after weighted fusion.
- The uploads watcher deleted index and database records when an uploaded file went missing, and starting from another directory marked every document as missing; it now logs a single warning instead.
- Claude model IDs used the wrong format (2.2.1 listed them as `claude-4-8-opus`).
- The PostgreSQL init script `init.sql` was missing the `documents.description` column.

#### Frontend

- Pressing Enter to pick a character in Zhuyin, Cangjie, and other input methods sent the message.
- Answers were rewritten: blockquotes broke, `<Button>` in code became lowercase, `<script>` lines disappeared, and paragraphs containing `|` were turned into social post cards.
- SSE events split across network reads were lost, so new conversations did not appear in the sidebar and the next message started yet another conversation.
- A streaming error left the page stuck on "researching" with no message, and a failed conversation list load only showed "no conversations yet".
- Switching conversations mid-stream wrote the answer into the other conversation, and the title jumped back afterwards.
- A wrong password showed "未找到刷新令牌" (refresh token not found) on the login page: 401 responses from login, register, and token refresh no longer trigger a token refresh.
- Keyboard focus was invisible; field labels were not bound to inputs, so screen readers could not name them; suggested prompts, citations, and the upload drop zone were not keyboard-operable.
- On phones the conversation list button was covered by the top bar and answer bubbles were wider than the screen; the desktop chat page had an extra page scrollbar.
- Loading older messages jumped back to the bottom, and scrolling up while streaming was pulled back down.
- A failed knowledge-base delete still reported success and its error could not be dismissed; reloading replaced the page with a spinner; upload failure reasons were dropped; "cancel all uploads" kept uploading the remaining files.
- Errors in the change-password and admin edit-user dialogs appeared on the page behind the dialog.
- AI tools page notifications had no styles, search did not filter MCP servers, forms overflowed on phones, and the OpenAPI import prefilled an example spec.
- Button loading spinners did not spin; the knowledge-base "clear list" button used a nonexistent variant, and two icon names did not exist.
- Copying failed silently where the Clipboard API is unavailable (for example over http on a LAN).
- The admin tables pushed the actions column off screen at 1024px.
- `bun run lint` could not run: the missing `@eslint/js` and `globals` dev dependencies were added.

### Security

- Every tool result is wrapped in an `<untrusted_tool_result>` marker whose id changes per question, and the system prompt treats it as data only.
- `web_fetch` may only read URLs that appear verbatim in the user's message or in this question's built-in tool results (query arguments echoed by tools do not count); new `WEB_FETCH_ALLOWED_DOMAINS` domain allowlist and `BLOCK_WEB_TOOLS_AFTER_KB` (web tools disabled once knowledge-base content has been read).
- **Tool management is admin-only**: any registered user could create a `stdio` MCP server and run arbitrary commands on the host (RCE), and could read tool credentials configured by others. Every endpoint under `/api/api-tools` and `/api/mcp`, including reads, now requires an admin, and the frontend AI tools page is shown to admins only. See [ADR-0004](docs/adr/0004-tool-admin-permissions-and-subprocess-isolation_en.md).
- MCP `stdio` subprocesses inherit only essential system variables such as `PATH` and no longer receive the backend's JWT key, database URL, or model API keys.
- The MCP HTTP transport gains the SSRF validation it was missing, and custom API tools and the MCP HTTP transport validate every redirect again, so an external API can no longer redirect into the internal network or cloud metadata.

---

## [2.2.1] - 2026-09-19

### Fixed

- **Error responses now use error codes**:
  - Added `app/core/error_response.py`: unexpected exceptions and stack traces stay in server logs while clients receive only a random error code and `error_id` (CWE-209 / CWE-497).
  - Applied across `api_tools.py`, `mcp.py`, `chat.py`, and `openapi_parser.py`; input validation errors are marked with `SafeClientError` and returned verbatim so users keep an actionable message.
- **Removed exception text leaking through the RAG stream**: streaming output in `rag/agent.py`, `rag/pipeline.py`, and `rag/tools.py` no longer carries exception details.

---

## [2.2.0] - 2026-09-01

### Fixed

- **SSRF vulnerability in OpenAPI parsing and outbound requests (#25)**:
  - Added `app/core/ssrf_protection.py`, validating user-supplied URLs by scheme, port, hostname, and post-DNS IP ranges, blocking private ranges, loopback and link-local addresses, cloud metadata endpoints, and dangerous ports.
  - `openapi_parser.py`, `rag/tools.py` (`web_fetch`), and `api_tools.py` now route through the SSRF guard.
  - Added `backend/tests/test_ssrf_protection.py` covering both blocked and allowed cases.

---

## [2.1.0] - 2026-08-27

### Added

- **Custom API tools**:
  - New `custom_api_tools` table and `/api/api-tools` endpoints for tool CRUD, enable/disable toggling, and live connectivity tests.
  - A generic HTTP executor handling path variable substitution, query assembly, header and auth injection (Bearer / API Key / Basic), JSON and form body serialization, and timeout isolation.
- **OpenAPI / Swagger import**:
  - New `services/openapi_parser.py` parsing OAS 2.0, 3.0, and 3.1 specs from raw content or a URL, with bulk import of selected endpoints as AI tools (existing names are updated in place).
- **MCP server integration**:
  - New `mcp_servers` table and `/api/mcp` endpoints for server CRUD, preset catalog, tool discovery (`initialize` + `tools/list`), and single-tool invocation tests.
  - New `services/mcp_service.py` providing JSON-RPC clients over `stdio` subprocesses and HTTP.
- **Dynamic tool registration**: `ResearchToolRegistry` loads enabled custom API tools and MCP tools (named `mcp_<server>_<tool>`) whenever tool definitions are assembled — no backend restart required.
- **Frontend AI tools page**: new `/tools` route and `AiTools` page with a tool overview, OpenAPI import wizard, and MCP server management.

### Changed

- Simplified `.gitignore` rules and removed local database files from version control.

---

## [2.0.1] - 2026-08-26

### Added

- **Multimodal chat pipeline**: image and file attachments in chat; images are sent to vision models as `image_url` content parts while text attachments are extracted into the prompt context.
- **Dynamic knowledge base descriptions**: uploads receive an AI-generated outline and summary, with endpoints to regenerate or edit it manually.

### Changed

- Modernized the frontend interface and component library.

---

## [2.0.0] - 2026-08-24

### Added

- **Agentic RAG Autonomous Research Pipeline**:
  - Implemented ReAct research agent (`ResearchAgent`) supporting multi-turn reasoning and Native Tool Calling.
  - Provided native toolset in `ResearchToolRegistry`: internal knowledge base search (`search_knowledge_base`), live web search (`web_search` with Ollama & DuckDuckGo dual fallback), and deep web fetch (`web_fetch`).
- **Reasoning Effort Multi-Tier Selection**:
  - Added 5 reasoning depth levels in the top navigation: `None`, `Low`, `Medium`, `High`, and `X-High`.
  - Fully compatible with Azure OpenAI v1 and OpenAI reasoning models, with tool-call compatibility handled automatically according to the Microsoft Foundry specification.
- **Frontend Research Visualization**:
  - Added `ResearchTraceBlock`: Collapsible step-by-step research trace timeline with tool execution logs.
  - Added `SourceBadges`: Clickable external source reference badges that open in new tabs.
- **Modular RAG Engine Architecture**:
  - Refactored RAG subsystem into decoupled modules: index managers (`indices/`), hybrid retrievers (`retrievers/`), pipeline orchestrator (`pipeline.py`), evaluator (`evaluator.py`), and unified facade (`contextual_rag.py`).

### Changed

- **Zero-Dependency Lightweight Core**:
  - Defaulted to the built-in SQLite database and in-memory caching, eliminating mandatory Docker/PostgreSQL/Redis setups for local development.
  - Retired the legacy discussion board and custom agent modules to focus on knowledge-base Q&A and deep research.
  - Removed cache hits to ensure all queries reflect grounded knowledge and live web data.
- **Frontend Experience & Layout**:
  - Unified sidebar into a single adaptive instance (docked on desktop, drawer on mobile).
  - Adopted Bun as the preferred toolchain for package management and building.

### Fixed

- **Azure OpenAI v1 API Compatibility**:
  - Removed legacy `AZURE_OPENAI_API_VERSION` dependency in favor of standard v1 endpoints.
  - Removed unsupported `max_tokens` and `temperature` parameters for reasoning models in favor of a compatible payload structure.
- **Stability & Bug Fixes**:
  - Fixed `NameError` caused by missing `Dict, Any` imports in `MessageResponse`.
  - Fixed `TypeError` in `HybridContextualRAG.generate_response()` missing `reasoning_effort` argument.
  - Fixed 500 error in `/api/chat/models` caused by missing `settings` import and added comma-separated deployment name normalization.
  - Fixed duplicate sidebar rendering on desktop viewports.

---

## [1.0.0] - 2026-08-01

### Added

- Contextual Hybrid RAG retrieval pipeline (FAISS + Whoosh BM25 + Cross-Encoder Reranker).
- RSA-2048 JWT authentication with token revocation blacklist.
- Sensitive data two-layer redaction (`security_logging.py`).
- Document upload, chunking, embedding, and background reindexing tasks.