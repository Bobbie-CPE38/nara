# PR T2 — Roster actual intervals and recorded duties

Branch: `feat/roster-duty-intervals`. Integrates T1 (#78) from staging.

## Behavior

- Nullable `actual_start_at` and `actual_end_at` independently fall back to the
  corresponding scheduled Shift endpoints. Both specified endpoints must be ordered.
- `transferred_from_assignment_id` is a unique self-FK. Transfer workflows (C2/C3)
  own writing/cutting roster rows; T2 enables no transfer workflow by itself.
- Shared effective SQL endpoints are used by working-time snapshots, hard-rule
  roster loading, completion, Roster API leave flags and leave-update overlap reports.
- Committed contiguous segments are grouped only through explicit transfer links.
  Completed prefixes count. Ordinary adjacent rows are separate duties.
- The originating shift determines a duty's day, week and night classification.
  Snapshot loading includes a one-day lookahead to retain a Sunday duty's Monday tail.
- Hard Rules keep physical roster rows for identity/cancellation/overlap checks.
  Several rows may share a shift ID with different effective intervals, including
  cancelled full-shift history and committed partial rows. Existing intervals are
  never rewritten to the proposed Cover. Identity checks still use shift ID;
  overlap checks inspect every committed interval. Identical intervals are deduplicated,
  while separate committed parts survive both fatigue and snapshot accounting.
  Fatigue rules use recorded duty groups. If the proposed shift is already a
  non-root member, its entire existing duty is counted once; ALREADY_ON_SHIFT still
  rejects it through the physical roster rows. T1's proposed Cover/source cut is applied
  before grouping, and the retained source ancestry joins the proposed duty once.
- Completion uses actual end with the queued staff-event safeguard unchanged.
- Replacement creation validates effective endpoints and copies a partial Cover. A Cover
  equal to both scheduled endpoints is stored as NULL/NULL, retaining whole-shift
  fallback behavior if the schedule changes. Transfer cutting/link writing remains C2/C3.
- Both Roster APIs expose the three raw fields on each assignment; nested Shift
  times remain scheduled times. The staff timeline orders by effective start.
- The Roster page shows the effective interval and source assignment ID per row.

## Migration

`b8d4f1a6c2e9` follows T1 `a9c3e7f1b5d2`. NULLs preserve existing assignments;
there is no backfill or reset requirement. Recheck the parent against staging
before merging if another migration lands first.

## Validation and handoff

Use `LINE_MODE=simulation` and a separate test database. Tests write transfer rows
and Cover data directly, including retained completed prefixes, an additional move,
plain adjacency, week boundaries, planning/Safety agreement, schema constraints,
migration round trip, API fields and frontend display.

Person 2 should review the duty/hour accounting. Gap coverage by intervals remains
T3's work; actual transfer execution remains C2/C3. These are not implemented here.

## Verified

- Backend: 2,355 passed, 14 timing tests skipped in the main run.
- Solver timing: the 14 skipped tests passed separately.
- Ruff check, Ruff format check, mypy and `git diff --check`: passed.
- One Alembic head, correct T1 parent; schema/model check reports no new operations.
- Frontend: 315 passed, TypeScript and production build passed.
- Local additive migration and read-only HTTP smoke: health and Roster return 200;
  the existing LINE binding remains present. No Demo reset was performed.

## Writer invariants and bounded-read limitations

- The database CHECK checks `actual_start_at < actual_end_at` only when both are
  non-NULL. It cannot validate a mixed-NULL interval against another table's Shift
  endpoints. `roster_time_service.effective_interval()` checks the resolved endpoints;
  replacement creation calls it while holding the Shift lock. C2/C3 must also call
  it before writing/cutting roster intervals, and future schedule-edit writers must
  revalidate affected overrides. Direct SQL bypasses this application validation.
- Lookahead loads next-week segments to complete Sunday duties; `working_time_at()`
  excludes their own next-week hours and future-start run entries. A regression test
  proves those rows are loaded without changing the current snapshot.
- If a source is outside the bounded read window (or absent from the committed
  input), the remaining destination becomes a standalone duty. Its own start sets
  its day/week, which can differ from the complete chain's attribution. This is a
  known limitation, explicitly tested at the Sunday/Monday boundary; no omitted
  prefix is guessed or reconstructed.
