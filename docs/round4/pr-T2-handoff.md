# PR T2 — work in progress

Branch: `feat/roster-duty-intervals`, based on staging after #77.

This is partial preparation while T1 (#78) is under review. It is not ready to merge.

## Prepared

- Nullable `ROSTER_ASSIGNMENT.actual_start_at`, `actual_end_at` and unique self-FK
  `transferred_from_assignment_id`; NULL endpoints independently fall back to Shift times.
- Shared SQL endpoint expressions in `roster_time_service`.
- Working-time snapshots load effective roster intervals and combine contiguous segments
  only through recorded transfer links, including completed source segments. Ordinary
  adjacent rows remain separate duties. A linked duty keeps the originating shift's
  identity, start-day/week and night classification.
- Roster completion uses the effective end, retaining the queued-event safeguard.
- Both Roster read APIs expose the new raw fields, compute leave overlap on effective
  intervals, and the staff timeline orders rows by effective start.
- Tests create transfer rows directly. No transfer-writing workflow is enabled.

## Finish after T1 merges

1. Merge updated staging and change migration `b8d4f1a6c2e9.down_revision` from the
   temporary parent `e1a4c7f2b9d6` to the actual staging head (expected T1 `a9c3e7f1b5d2`).
2. Adapt T1's hard-rule roster loader to actual times and recorded completed transfer
   duties. Integrate the stored-duty reader with T1's proposed `Cover`/`linked_duty`
   transformation, so retained prefixes never count twice. Test planning and Safety.
3. Update the frontend Roster types/display and tests to show each row's effective
   interval and transfer source, keeping the shift header's scheduled times.
4. Update `database-schema.md` and `workflow.md` to describe implemented T2 behavior,
   fill the status row, and add the changelog entry only when implementation is complete.
5. Verify migration round trip, a single head, baseline scenarios, backend/frontend
   checks and the interaction with T1. Have person 2 review duty/hour accounting.

## Local testing

Use a separate test database (`staffing_t2_draft_test`) and `LINE_MODE=simulation`.
The draft migration has not been applied to the Demo database. Because development
Compose binds the checkout and reloads Python, the live Demo must use staging again
or have the correct migration before exercising the changed readers. Do not reset
Demo merely to test this draft; it would erase LINE bindings.

## Preparation validation

- Backend: 2,279 passed, 14 timing tests skipped, with simulation mode and a separate DB.
- Ruff check, Ruff format check and mypy passed on the prepared implementation.
- Coverage includes linked/unlinked duties, Sunday-to-Monday attribution, actual-end
  completion, API endpoint/link fields, leave overlap, CHECK/UNIQUE constraints,
  nullable fallback, and migration downgrade/upgrade.
- Full frontend checks and T1 integration remain for completion; no frontend changes yet.
