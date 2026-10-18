<!--
感謝貢獻！送出前請先閱讀 .github/CONTRIBUTING.md。安全漏洞請依 .github/SECURITY.md 私下通報，不要開公開的 Pull Request。
Thanks for contributing! Please read .github/CONTRIBUTING_en.md first. Report security vulnerabilities privately as described in .github/SECURITY_en.md, not in a public pull request.
-->

## 變更內容 / Summary

<!-- 這個 PR 改了什麼、為什麼要改 / What this PR changes and why -->

## 相關 Issue / Related issues

<!-- 例如 / For example: Closes #123 -->

## 驗證方式 / Verification

<!-- 目前沒有自動執行測試的 CI，請勾選在本機執行過的檢查並補充手動測試 / There is no CI that runs the tests; tick the checks you ran locally and describe any manual testing -->

- [ ] 後端 / Backend: `python -m pytest`
- [ ] 前端 / Frontend: `bun run test --run`, `bun run lint`, `bun x tsc --noEmit`
- [ ] 手動測試 / Manual testing:

## 檢查清單 / Checklist

- [ ] Commit 訊息遵循 Conventional Commits，破壞性變更標上 `!` 與 `BREAKING CHANGE:` / Commit messages follow Conventional Commits, with `!` and `BREAKING CHANGE:` for breaking changes
- [ ] 遵守 `llms.txt` 的系統約束 / Follows the system constraints in `llms_en.txt`
- [ ] 文件的中英版本一起更新 / Updated both the Chinese and the `_en` documents
- [ ] 在 `CHANGELOG.md` 與 `CHANGELOG_en.md` 的 `[Unreleased]` 記下變更 / Recorded the change under `[Unreleased]` in `CHANGELOG.md` and `CHANGELOG_en.md`
- [ ] （如適用）改到介紹頁重現的後端規則時，同步更新 `site/index.html` 與 `site/main.js` / (If applicable) Updated `site/index.html` and `site/main.js` for backend rules the intro site reproduces
- [ ] （如適用）`requirements.in` 與 `requirements.txt`、`package.json` 與 `bun.lock` 一起提交 / (If applicable) Committed `requirements.in` with `requirements.txt`, and `package.json` with `bun.lock`
- [ ] （如適用）使用者看得到的文字使用臺灣用語 / (If applicable) User-facing text uses Traditional Chinese as written in Taiwan

## 破壞性變更與升級步驟 / Breaking changes and upgrade steps

<!-- 沒有就寫「無」 / Write "None" if there are none -->

## 截圖 / Screenshots

<!-- 介面有變動時附上變更前後的截圖 / For UI changes, attach before-and-after screenshots -->
