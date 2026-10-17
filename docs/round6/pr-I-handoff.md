# PR I — Contextual LINE message guidance

The team expanded the original fixed-reply scope to four deterministic responses. No LLM or intent classification is used. For personal non-command messages (including images/stickers), read only the sender's active binding and existing offer views, in this priority:

1. **Unbound:** Ask the nurse to obtain a code from the administrator and send `LINK <code>`.
2. **An offer can be answered:** Direct the nurse to the buttons on an actionable offer. Typing is not an offer response. Use existing `can_accept` / `can_reject` rules; avoid promising that acceptance is available when another case pauses it.
3. **Accepted and awaiting a result, including reserves:** Confirm that acceptance was already recorded and ask the nurse to wait for assignment confirmation. Exclude stopped cases, confirmed assignments and offers with a final outcome.
4. **No pending offer activity:** Greet the nurse, explain that no offer is awaiting action, and direct questions to the head nurse. This does not claim that the nurse has no assigned shifts.

Exact Thai messages and priorities are documented in `workflow.md` 6.29.

- LINK, CHECKIN and postback buttons retain their existing handlers and validation.
- No LLM call, message persistence, message echo, audit or business-state change. Only the webhook event ID and processed time are stored.
- No guidance in group/room conversations, unidentified sources, or non-message events. Missing reply tokens do not trigger network work.
- Read status before dedup commits, then reply using the existing post-commit scheduler. Simultaneous redelivery has one winner. A failed reply does not roll back dedup or retry on redelivery.
- The response reflects the status at processing time; it does not reserve an offer or replace validation when its button is pressed.
- No migration or environment change. No tunnel/deployment configuration changes.

Verification uses fake LINE adapters, signed callbacks, sequential and simultaneous redelivery, snapshots of all business tables, and command/button regression tests. Live LINE testing has not been run for this change.

Validation after the four-case update: backend 2,909 passed, 14 skipped (solver timing harness); 25 new message-guidance tests cover the four outcomes and edge cases. Ruff check, Ruff format, mypy (180 app files), and `git diff --check` passed. No frontend files changed.
