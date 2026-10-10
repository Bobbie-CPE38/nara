# Repo Structure

> โครงสร้างเป้าหมายของ Repo ใช้คู่กับ `docs/workflow.md` และ `docs/database-schema.md`

```text
nara/
│
├── README.md
├── .env.example
├── .gitignore
├── docker-compose.yml
├── Makefile
│
├── docs/
│   ├── architecture.md
│   ├── database-schema.md
│   ├── workflow.md
│   ├── walking-skeleton.md
│   ├── repo-structure.md
│   ├── optimization.md
│   ├── safety-validation.md
│   ├── approval.md
│   ├── audit.md
│   ├── api.md
│   └── demo.md
│
├── scripts/
│   ├── reset-demo.sh
│   ├── load-demo-data.sh
│   ├── export-openapi.sh
│   ├── test-all.sh
│   └── lint-all.sh
│
├── backend/
│   │
│   ├── pyproject.toml
│   ├── alembic.ini
│   │
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │
│   ├── app/
│   │   │
│   │   ├── main.py
│   │   │
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── constants.py
│   │   │   ├── logging.py
│   │   │   ├── security.py
│   │   │   ├── errors.py
│   │   │   ├── clock.py
│   │   │   └── locks.py
│   │   │
│   │   ├── db/
│   │   │   ├── base.py
│   │   │   ├── session.py
│   │   │   │
│   │   │   └── models/
│   │   │       ├── staff.py
│   │   │       ├── actor.py
│   │   │       ├── ward.py
│   │   │       ├── skill.py
│   │   │       ├── role.py
│   │   │       ├── staff_skill.py
│   │   │       ├── shift.py
│   │   │       ├── staffing_event.py
│   │   │       ├── staffing_requirement.py
│   │   │       ├── staffing_requirement_role.py
│   │   │       ├── staffing_requirement_skill.py
│   │   │       ├── staffing_case.py
│   │   │       ├── staff_unavailability.py
│   │   │       ├── roster_assignment.py
│   │   │       ├── candidate_plan.py
│   │   │       ├── candidate_item.py
│   │   │       ├── contact.py
│   │   │       ├── candidate_outreach.py
│   │   │       ├── attendance.py
│   │   │       ├── staff_working_time_snapshot.py
│   │   │       ├── approval_policy.py
│   │   │       ├── hard_constraint_policy.py
│   │   │       ├── soft_constraint_policy.py
│   │   │       ├── staffing_gap.py
│   │   │       ├── staffing_gap_role.py
│   │   │       ├── staffing_gap_skill.py
│   │   │       ├── safety_validation.py
│   │   │       ├── approval_request.py
│   │   │       ├── structured_handover.py
│   │   │       └── audit_log.py
│   │   │
│   │   ├── repositories/
│   │   │   ├── staff_repository.py
│   │   │   ├── actor_repository.py
│   │   │   ├── ward_repository.py
│   │   │   ├── shift_repository.py
│   │   │   ├── event_repository.py
│   │   │   ├── case_repository.py
│   │   │   ├── requirement_repository.py
│   │   │   ├── unavailability_repository.py
│   │   │   ├── roster_repository.py
│   │   │   ├── attendance_repository.py
│   │   │   ├── working_time_repository.py
│   │   │   ├── policy_repository.py
│   │   │   ├── gap_repository.py
│   │   │   ├── candidate_repository.py
│   │   │   ├── outreach_repository.py
│   │   │   ├── safety_repository.py
│   │   │   ├── approval_repository.py
│   │   │   ├── handover_repository.py
│   │   │   └── audit_repository.py
│   │   │
│   │   ├── schemas/
│   │   │   ├── types.py
│   │   │   ├── auth.py
│   │   │   ├── staff.py
│   │   │   ├── ward.py
│   │   │   ├── shift.py
│   │   │   ├── event.py
│   │   │   ├── case.py
│   │   │   ├── requirement.py
│   │   │   ├── unavailability.py
│   │   │   ├── roster.py
│   │   │   ├── working_time.py
│   │   │   ├── staffing_gap.py
│   │   │   ├── candidate.py
│   │   │   ├── optimization.py
│   │   │   ├── outreach.py
│   │   │   ├── safety.py
│   │   │   ├── approval.py
│   │   │   ├── policy.py
│   │   │   ├── handover.py
│   │   │   └── audit.py
│   │   │
│   │   ├── domain/
│   │   │   ├── enums.py
│   │   │   ├── errors.py
│   │   │   │
│   │   │   ├── workflow/
│   │   │   │   └── transitions.py
│   │   │   │
│   │   │   ├── staffing/
│   │   │   │   ├── coverage.py
│   │   │   │   └── gap_calculator.py
│   │   │   │
│   │   │   ├── constraints/
│   │   │   │   ├── codes.py
│   │   │   │   ├── context.py
│   │   │   │   ├── hard_rules.py
│   │   │   │   ├── evaluator.py
│   │   │   │   ├── soft_metrics.py
│   │   │   │   └── penalties.py
│   │   │   │
│   │   │   └── policies/
│   │   │       ├── hard_constraint.py
│   │   │       ├── soft_constraint.py
│   │   │       └── approval.py
│   │   │
│   │   ├── optimization/
│   │   │   ├── types.py
│   │   │   ├── input_builder.py
│   │   │   ├── snapshot_builder.py
│   │   │   ├── candidate_filter.py
│   │   │   ├── model_builder.py
│   │   │   ├── objective_builder.py
│   │   │   ├── solver.py
│   │   │   ├── result_mapper.py
│   │   │   └── explanation.py
│   │   │
│   │   ├── safety/
│   │   │   ├── context_builder.py
│   │   │   ├── validator.py
│   │   │   └── snapshot_builder.py
│   │   │
│   │   ├── workflow/
│   │   │   ├── context.py
│   │   │   ├── orchestrator.py
│   │   │   │
│   │   │   └── handlers/
│   │   │       ├── base.py
│   │   │       ├── intake_event.py
│   │   │       ├── assess_staffing.py
│   │   │       ├── optimize.py
│   │   │       ├── contact_candidate.py
│   │   │       ├── validate_safety.py
│   │   │       ├── execute_assignment.py
│   │   │       └── manual_handoff.py
│   │   │
│   │   ├── services/
│   │   │   ├── event_service.py
│   │   │   ├── case_service.py
│   │   │   ├── requirement_service.py
│   │   │   ├── gap_service.py
│   │   │   ├── candidate_service.py
│   │   │   ├── optimization_service.py
│   │   │   ├── outreach_service.py
│   │   │   ├── safety_service.py
│   │   │   ├── approval_service.py
│   │   │   ├── roster_service.py
│   │   │   ├── attendance_service.py
│   │   │   ├── unavailability_service.py
│   │   │   ├── working_time_service.py
│   │   │   ├── policy_service.py
│   │   │   ├── availability_service.py
│   │   │   ├── handover_service.py
│   │   │   ├── actor_service.py
│   │   │   └── audit_service.py
│   │   │
│   │   ├── integrations/
│   │   │   ├── common/
│   │   │   │   ├── client.py
│   │   │   │   ├── retry.py
│   │   │   │   └── errors.py
│   │   │   │
│   │   │   ├── his/
│   │   │   │   ├── interface.py
│   │   │   │   └── mock.py
│   │   │   │
│   │   │   ├── hr/
│   │   │   │   ├── interface.py
│   │   │   │   └── mock.py
│   │   │   │
│   │   │   ├── attendance/
│   │   │   │   ├── interface.py
│   │   │   │   └── mock.py
│   │   │   │
│   │   │   ├── roster/
│   │   │   │   ├── interface.py
│   │   │   │   └── mock.py
│   │   │   │
│   │   │   └── line/
│   │   │       ├── interface.py
│   │   │       ├── client.py
│   │   │       ├── signature.py
│   │   │       ├── parser.py
│   │   │       └── mock.py
│   │   │
│   │   ├── messaging/
│   │   │   ├── formatter.py
│   │   │   └── templates/
│   │   │       ├── candidate_offer.py
│   │   │       ├── approval_request.py
│   │   │       ├── approval_escalation.py
│   │   │       └── case_status.py
│   │   │
│   │   ├── jobs/
│   │   │   ├── runner.py
│   │   │   │
│   │   │   └── tasks/
│   │   │       ├── candidate_timeout.py
│   │   │       ├── approval_timeout.py
│   │   │       ├── advance_case.py
│   │   │       ├── detect_no_show.py
│   │   │       └── refresh_working_time.py
│   │   │
│   │   ├── api/
│   │   │   ├── dependencies.py
│   │   │   ├── exception_handlers.py
│   │   │   │
│   │   │   └── routes/
│   │   │       ├── auth.py
│   │   │       ├── dashboard.py
│   │   │       ├── staff.py
│   │   │       ├── wards.py
│   │   │       ├── shifts.py
│   │   │       ├── events.py
│   │   │       ├── cases.py
│   │   │       ├── requirements.py
│   │   │       ├── optimization.py
│   │   │       ├── outreach.py
│   │   │       ├── approvals.py
│   │   │       ├── policies.py
│   │   │       ├── roster.py
│   │   │       ├── audit.py
│   │   │       ├── webhooks.py
│   │   │       ├── line_sim.py
│   │   │       └── demo.py
│   │   │
│   │   └── seed/
│   │       ├── __init__.py
│   │       ├── __main__.py
│   │       ├── reset.py
│   │       ├── base_data.py
│   │       └── scenarios/
│   │           ├── golden_case.py
│   │           ├── candidate_reject.py
│   │           ├── candidate_timeout.py
│   │           ├── safety_failure.py
│   │           ├── head_nurse_reject.py
│   │           ├── auto_approval.py
│   │           ├── manual_handoff.py
│   │           ├── duplicate_event.py
│   │           ├── integration_unavailable.py
│   │           ├── approval_timeout.py
│   │           └── no_feasible_solution.py
│   │
│   └── tests/
│       ├── conftest.py
│       ├── unit/
│       │   ├── api/
│       │   │   └── test_scaffold.py
│       │   │
│       │   ├── core/
│       │   │   ├── test_clock.py
│       │   │   └── test_config.py
│       │   │
│       │   ├── db/
│       │   │   ├── test_models.py
│       │   │   └── test_types.py
│       │   │
│       │   ├── domain/
│       │   │   ├── test_gap_calculator.py
│       │   │   ├── test_hard_rules.py
│       │   │   ├── test_soft_metrics.py
│       │   │   ├── test_penalties.py
│       │   │   └── test_approval_policy.py
│       │   │
│       │   ├── optimization/
│       │   │   ├── test_candidate_filter.py
│       │   │   ├── test_model_builder.py
│       │   │   ├── test_objective_builder.py
│       │   │   └── test_solver.py
│       │   │
│       │   ├── safety/
│       │   │   └── test_validator.py
│       │   │
│       │   └── workflow/
│       │       ├── test_handlers.py
│       │       └── test_transitions.py
│       │
│       ├── integration/
│       │   ├── conftest.py
│       │   ├── test_migrations.py
│       │   ├── test_models.py
│       │   ├── test_seed.py
│       │   ├── test_gap_policy.py
│       │   ├── test_gap_snapshot.py
│       │   ├── test_demo_reset.py
│       │   ├── test_health.py
│       │   ├── test_actor_service.py
│       │   ├── test_dependencies.py
│       │   ├── test_case_routes.py
│       │   ├── test_golden_flow.py
│       │   ├── test_events.py
│       │   ├── test_event_ignored.py
│       │   ├── test_gap_service.py
│       │   ├── test_assess_staffing.py
│       │   ├── test_orchestrator.py
│       │   ├── test_optimize.py
│       │   ├── test_execute_assignment.py
│       │   ├── test_outreach.py
│       │   ├── test_accepted_outreach.py
│       │   ├── test_outreach_response.py
│       │   ├── test_validate_safety.py
│       │   ├── test_pending_approvals.py
│       │   ├── test_approval_decision.py
│       │   ├── test_line_webhook.py
│       │   ├── test_candidate_timeout.py
│       │   ├── test_approval_timeout.py
│       │   ├── test_safety_failure.py
│       │   ├── test_no_feasible_solution.py
│       │   └── test_audit_trail.py
│       │
│       └── e2e/
│           └── test_workforce_recovery.py
│
├── frontend/
│   ├── package.json
│   ├── package-lock.json
│   ├── tsconfig.json
│   ├── next.config.ts
│   ├── vitest.config.mts
│   │
│   ├── tests/
│   │   └── unit/
│   │       ├── lib/
│   │       │   └── api.test.ts
│   │       └── hooks/
│   │           └── usePolling.test.ts
│   │
│   └── src/
│       ├── app/
│       │   ├── layout.tsx
│       │   ├── page.tsx
│       │   │
│       │   ├── dashboard/
│       │   │   └── page.tsx
│       │   │
│       │   ├── cases/
│       │   │   └── [id]/
│       │   │       └── page.tsx
│       │   │
│       │   ├── approvals/
│       │   │   └── page.tsx
│       │   │
│       │   ├── roster/
│       │   │   └── page.tsx
│       │   │
│       │   ├── policies/
│       │   │   └── page.tsx
│       │   │
│       │   └── demo/
│       │       ├── control/
│       │       │   └── page.tsx
│       │       └── line-sim/
│       │           └── page.tsx
│       │
│       ├── components/
│       │   ├── dashboard/
│       │   ├── case/
│       │   ├── candidate/
│       │   ├── optimization/
│       │   ├── outreach/
│       │   ├── safety/
│       │   ├── approval/
│       │   ├── roster/
│       │   ├── audit/
│       │   └── common/
│       │
│       ├── lib/
│       │   ├── api.ts
│       │   ├── types.ts
│       │   └── constants.ts
│       │
│       └── hooks/
│           └── usePolling.ts
│
└── infra/
    ├── docker/
    │   ├── backend.Dockerfile
    │   ├── worker.Dockerfile
    │   └── frontend.Dockerfile
    │
    └── aws/
        ├── ecs/
        ├── rds/
        ├── iam/
        └── cloudwatch/
```

Frontend tests live in `frontend/tests/`, separate from application code, following
the backend convention. Vitest runs the API tests with mocked network responses;
the polling hook tests use React Testing Library and jsdom with fake timers.
These unit tests do not require a running backend or database.

Run once: `docker compose exec frontend npm test`.
Watch changes: `docker compose exec frontend npm run test:watch`.
