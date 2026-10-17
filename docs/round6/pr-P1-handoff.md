# PR P1 — Nurse handover history pagination

`GET /me/handovers` now returns an object rather than the original full list:

```json
{"active": [], "history": [], "next_cursor": null}
```

- `active`: every handover with an ASSIGNED roster row whose effective end is still in the future, newest generated time/ID first. Available on every page, independently of the history limit, so current shifts remain discoverable for check-in.
- `history`: at most `limit` rows (default 20, range 1–100), ordered by immutable `generated_at DESC, id DESC`. SQL fetches only limit + 1 history rows.
- `next_cursor`: null when there is no next page. Otherwise pass it as the `cursor` query parameter. The Base64 JSON carries version, header staff ID, generated time and handover ID; it is a position, not an authorization token. Bad, naive-time or foreign-staff cursors return 422. Maximum length is 512.
- Authorization always comes from X-Demo-User; a staff_id parameter cannot select another nurse. Anonymous requests remain 401.
- Dynamic status changes are evaluated anew per request, not frozen into a cursor. History that becomes eligible before an existing boundary appears on a refresh from page one. No cross-request database snapshot is promised.
- The case API continues using the original full list; this PR changes only the nurse endpoint and its web consumer. No migration.

The nurse page initially fetches one history page and all active handovers. “Load more history” expands the prefix. Polling rebuilds that prefix sequentially from page one, deduplicates IDs and replaces the browser snapshot only after all requested pages succeed. An error retains the previous list with a warning. Sign-out/user changes unmount and cancel the old request chain.

No LINE or Bedrock calls are added. Handover delivery and check-in validation are unchanged.

Validation: backend 3,035 passed, 14 skipped (solver timing harness); frontend 353 passed; frontend typecheck, Ruff check/format, mypy (183 app files), and `git diff --check` passed. No live LINE/AWS testing is needed for this read-only change; no external service was called.
