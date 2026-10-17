# PR S — Requested AI case summaries

Branch: `feat/case-ai-summary`, based on staging after B1, E1, P1 and F1.

## Behaviour

- Reading a case, ranking and changing workflow state do not create AI work. `POST /cases/{id}/summary` alone requests a snapshot. Like the E1 endpoint, it takes no body or demo identity; AWS Basic Auth remains the outer gate.
- GET `summary` and the POST response have `{current, history}`. A never-requested snapshot has `current.summary_id=null`, status NOT_REQUESTED, text/generated_at null and request availability. No internal payload, failure string or cost is returned.
- Same snapshot reuses the existing row, including PENDING and READY. A READY answer stays readable when LLM is off or quota exhausted. Requests after repairable failures keep attempts and quota; the per-request and lifetime limits match E1.
- New persisted facts produce a new SHA-256. Before requesting, the latest older READY text remains visible with `stale=true`; after requesting, the current snapshot's state is shown and old READY texts stay in history. Generated timestamps are completion times, history orders by request ID descending.
- Snapshot facts: case status; shift times and patient count; the latest **saved** gap and headcount intervals plus role/skill counts; solver status/candidate count; stored offer, approval, ward-decision and event counts; anonymous roster statuses and actual cover windows. This is not an authoritative live shortage calculation. The prompt forbids subtracting assignments from the saved gap or recommending roster decisions.
- No staff identifiers/names, LINE UID, incoming messages, approval reasons or audit prose enter the prompt. Catalog role/skill labels are included. Times normalize to Asia/Bangkok (+07:00), matching the head nurse’s local times; the prompt requires that same zone. Lists sort deterministically; time passing, quota usage, model logs and summary rows do not change the input hash.
- The worker uses the stored snapshot even when the case changes during the call. It never changes workflow, roster, audit or LINE. Failures remain non-READY and do not appear as AI text.

## Delivery and migration

- Migration `f9a1c3e5b7d2` follows E1 `e7c3a5d9b1f4`, creates CASE_SUMMARY with snapshot uniqueness and a pending index, and performs no backfill.
- Internal Job schedules a separate summary worker session after the response, following the ranking worker. Each worker handles at most three rows per tick; both use B1's shared daily quota, paid-call ledger and number/format validator. Claims use DB real time and UUID tokens. Network work runs without an open transaction or row lock.
- Demo reset drops summary snapshots with case data. B1 preserves quota and call logs, detaches subject references, and an old worker cannot attach its result to the reset data. Downgrade likewise detaches summary ledger references before dropping the table, preserving quota and costs.
- Upgrade a development database with `alembic upgrade head` before running the feature. Do not reset the database just to enable S. No new environment values, AWS resources or LINE setup are needed; LLM must already be configured and enabled to request new text.
- UI: the case page includes an explicit summary button, pending state, stale warning, prior summaries and quota/configuration/attempt-limit messages. Polling restarts on a request even for a closed case and continues until that summary finishes. No automatic POST on mount or refresh.

## Integration notes

- Staging after E2 (#112) is merged. The case page retains both ranking-explanation controls (including timeout/refusal handling) and the case-summary section. A regression test keeps polling a final case until both requested jobs finish. F2 can use the existing case page without new summary controls.
- Follow staging's latest migration head if another migration lands first; preserve every workflow changelog row.
- The fake adapter produces a clearly marked `[fake]` summary; it never falls back from failed Bedrock to fake.

## Validation

Tests cover snapshot stability across UTC and Asia/Bangkok database sessions, Thai-time output passing the number validator, the HTTP Job with no environment secret, identity exclusion, no automatic work, cached READY reads, stale/history behaviour, failure recovery and lifetime limits, shared quota with E1, unknown-case/refusal responses, frozen inputs, two-connection requests and workers, network lock release, reset during model work, migration downgrade/upgrade with paid usage retained, explicit UI requests, duplicate clicks, quota messages, unmount cancellation and final-case polling.

All external adapters in tests are fake or guarded. No live Bedrock/LINE or AWS deployment was performed. Production frontend build is checked in an isolated temporary copy, keeping the developer server's build cache separate.

Verified locally: backend **3,140 passed, 14 skipped** (solver timing harness), with `INTERNAL_JOB_SECRET` absent from the environment; frontend **404 passed**; TypeScript, Ruff check/format, mypy (192 app files), single Alembic head and `git diff --check` passed. The isolated production build passed. The live Demo database was not upgraded or reset.
