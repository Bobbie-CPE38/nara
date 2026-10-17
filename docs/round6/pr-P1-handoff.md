# PR P1 — Nurse handover history pagination

`GET /me/handovers` now returns an object rather than the original full list:

```json
{"active": [], "history": [], "next_cursor": null}
```

- `active`: every handover with an ASSIGNED roster row whose effective end is still in the future, newest generated time/ID first. Available on every page, independently of the history limit, so current shifts remain discoverable for check-in.
- `history`: at most `limit` rows (default 20, range 1–100), ordered by immutable `generated_at DESC, id DESC`. SQL fetches only limit + 1 history rows.
- `next_cursor`: null when there is no next page. Otherwise pass it as the `cursor` query parameter. The Base64 JSON carries version, header staff ID, generated time and handover ID; it is a position, not an authorization token. Bad, naive-time, UTC-overflowing or foreign-staff cursors return 422 through a dedicated InvalidCursorError; stored-row validation failures remain server errors. Maximum length is 512.
- Authorization always comes from X-Demo-User; a staff_id parameter cannot select another nurse. Anonymous requests remain 401.
- Dynamic status changes are evaluated anew per request, not frozen into a cursor. History that becomes eligible before an existing boundary appears on a refresh from page one. No cross-request database snapshot is promised.
- The case API continues using the original full list; this PR changes only the nurse endpoint and its web consumer. No migration.

The nurse page initially fetches one history page and all active handovers. Polling fetches only page one every two seconds and merges it into the loaded history, deduplicating IDs and replacing the active list. “Load more history” fetches exactly one older page with an independent 10-second deadline; only success advances the cursor. Failures retain the list and cursor with a warning, and only another click retries the older page. A failed older-page read explicitly asks the nurse to click Load more history to retry; successful page-one polls do not silently clear that failure. Active rows absent from the latest server list are removed rather than converted into invented history; completed rows appear only when returned in a history page. Older history outside page one is cached until the page is reopened; reopening starts again at page one. A complete first page replaces the cache, including an empty result after Demo reset. Sign-out/user changes cancel outstanding reads.

No LINE or Bedrock calls are added. Handover delivery and check-in validation are unchanged.

Validation: backend 3,035 passed, 14 skipped (solver timing harness); frontend 353 passed; frontend typecheck, Ruff check/format, mypy (183 app files), and `git diff --check` passed. No live LINE/AWS testing is needed for this read-only change; no external service was called.

Review follow-up validation: 57 targeted backend handover tests passed, including UTC-overflowing cursors and stored-row validation staying HTTP 500; frontend 361 tests passed, including a three-page cache with page-one-only polling, failed-page retry, malformed pages, independent deadlines, concurrent reads, sign-out cancellation, and removal of deleted active rows without synthesizing history. Ruff check/format and mypy passed. The frontend has no configured formatter/linter script; the page import order and JSX formatting were adjusted locally without reformatting unrelated code.
