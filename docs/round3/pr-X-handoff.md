# PR X — LLM ranking explanation

Branch: `feat/rank-explanation-llm`, based on `staging` after PR #68. Round 3 uses
the `fake` adapter only. No real Bedrock call is made anywhere (tests, CI, local
runs). The `bedrock` adapter is written and unit-tested offline with botocore's
`Stubber`. Real Bedrock, IAM, Budget and the 20 to 30 case model trial are round 6.

## Configuration

Names and safe defaults are in `.env.example` and are passed to the `backend`
service by `docker-compose.yml` (not to `job`). No AWS keys anywhere: Bedrock uses
the default boto3 credential chain.

| Variable | Default | Notes |
|---|---|---|
| `LLM_ENABLED` | `false` | Master switch. Off means nothing is enqueued or called. |
| `LLM_PROVIDER` | `fake` | `fake` or `bedrock`, chosen strictly by this value. |
| `LLM_MODEL_ID`, `AWS_REGION` | empty | Both required for `bedrock` (`llm_ready`). |
| `LLM_MAX_OUTPUT_TOKENS` | 1024 | 1 to 4096. |
| `LLM_REQUEST_TIMEOUT_SECONDS` | 15 | Per attempt, above 0 up to 60. |
| `LLM_MAX_RETRIES` | 1 | 0 or 1, so at most 2 attempts. |
| `LLM_INPUT_PRICE_PER_MTOK_USD`, `LLM_OUTPUT_PRICE_PER_MTOK_USD` | empty | Blank becomes `None` (Compose passes unset as ""). |

## How generation works

1. `optimize.handle()` calls `explanation_service.enqueue()` after `SOLVER_EXECUTED`
   when `LLM_ENABLED` and the plan has candidates. It only inserts a `PENDING`
   `rank_explanation` row inside the plan's savepoint, so it rolls back with the plan.
   No payload, no network, no LLM lock in the workflow.
2. `POST /internal/merge-windows/close-due` queues
   `run_pending_in_new_session()` as a FastAPI background task with its own Session.
   The tick never waits on the LLM, so a sentence can take up to about
   `JOB_INTERVAL_SECONDS` (30 s) plus the call. It is not in `job_service.run_due_work`,
   so `POST /demo/clock/advance` never calls the LLM.
3. A sweep handles at most 3 rows. `_claim` uses `FOR UPDATE SKIP LOCKED`, sets a claim
   UUID and `lease_until = clock_timestamp() + max(60, timeout x (retries + 1) + 30)` s, then
   commits. Lease time and the claim comparison use the database clock, not `clock.now()`: the
   lease times a real network call, so the Demo Clock must not expire it (exception to D10).
4. Before each attempt the row is re-locked, `attempts` is incremented and an
   `IN_FLIGHT` `llm_call_log` row is committed. The gateway is called with no
   transaction open. The result is then recorded under the claim. Attempts are durable,
   so the bound `1 + LLM_MAX_RETRIES` holds across crashes.
5. Outcomes: `SUCCEEDED` gives `READY`. `TIMEOUT`, `THROTTLED`, `SERVICE_ERROR` retry
   while attempts remain, then `FAILED`. `CONFIG_ERROR`, `TRUNCATED`, `INVALID_OUTPUT`
   give `FAILED` at once. No weights, a score mismatch or no candidates gives `SKIPPED`
   with no call. `llm_ready` false (bedrock without model or region) logs one error,
   calls nothing and leaves rows `PENDING`.
6. Implementation notes: a gateway that raises is recorded as `SERVICE_ERROR` with the
   exception type name (still bounded by attempts). A leftover `IN_FLIGHT` row after a
   crash is left as is (unknown usage). When a lease later expires with attempts
   exhausted, the next claim sets `FAILED` / `ATTEMPTS_EXHAUSTED` without calling.

## Payload and privacy

The payload is built from `input_snapshot` and `objective_score` only: `targets`
(IDs and counts), `plan_penalty` (selects the first wave) kept apart from
`ranking_key` (orders candidates in the plan), `candidate_count`, and the first 10
candidates by rank with `first_wave`, `total`, `terms` and their ranking-key numbers.
It has no names, `staff_id`, LINE ID or free text; people are "อันดับ N". The stored
`input_payload` is exactly what was sent, and `input_hash` is its canonical sha256.
Output must be non-empty, at most 2000 characters, with no control characters (Unicode
category `Cc`, including C1) other than newline and no bidirectional controls. Logs carry exception type names only, never prompts, responses or SDK
messages. Round 3 validates the format only, not that the sentence's numbers match.

## Call log and cost

`llm_call_log` has one row per attempt: provider, model, region, status, error type,
tokens, duration, the prices used and `estimated_cost_usd`. NULL tokens or cost mean
unknown, never 0. Cost is computed only when usage and both rates are known. `fake`
reports rate 0, so its cost is 0.

## API and UI

`GET /cases/{id}` gets `explanation`: `null` (no row for the latest plan), or
`{status, text, provider, model_id}` with `PENDING`, `READY` or `UNAVAILABLE`
(`FAILED` and `SKIPPED`). It is read from the latest row of the latest plan via
`case_service._latest_explanation`; there is no `explanation_service.latest_for_plan`.
It never exposes failure reasons, tokens or payload, and never calls the LLM.
`cases/[id]` shows the sentence in `ScoreBreakdown` after the intro text, with a note
when `provider` is `fake`, and "คำอธิบายยังไม่พร้อม" otherwise. The page keeps polling a
final case while its explanation is `PENDING`, and stops at `READY` or `UNAVAILABLE`
(no explanation row: stops at once).
`LlmRequest` and `LlmAttempt` live in `app/integrations/llm/__init__.py` and are
re-exported by `llm_service`.

## Migration `e1a4c7f2b9d6`

Follows PR K's `d7f0b3c5e9a2` (single head). Adds `rank_explanation` (unique
`plan_id, prompt_version`; partial index on `id` where `PENDING`) and `llm_call_log`
(unique `explanation_id, attempt`; index on `plan_id`). Downgrade drops both. No DB ENUM
or CHECK on the status text (D8). Migration tests cover the head, round trip, offline SQL
and the unique constraint.

## Round 6 switch-on checklist

1. Check that credits cover Bedrock and model access is enabled in the region.
2. IAM Role allowing `bedrock:InvokeModel` on the chosen model only.
3. AWS Budget alert.
4. Set `LLM_PROVIDER=bedrock`, `LLM_MODEL_ID`, `AWS_REGION` and the price variables.
5. Run 20 to 30 cases and compare sentences with the numbers.
6. Add a trial-period request cap. It is not in PR X. Current guards are `LLM_ENABLED`,
   enqueue for new plans only, 3 rows per sweep and at most 2 attempts per row.

## Verification

- Backend: **2,237 passed, 14 skipped** (opt-in timing harness).
- Ruff check, Ruff format check and mypy strict (159 files) passed.
- Frontend: **289 tests passed** (11 files); typecheck passed.
- `git diff --check` and `grep -ri "aws_secret\|AKIA"` over `.env.example`,
  `docker-compose.yml` and `backend/app`: clean.
- `alembic heads` prints exactly `e1a4c7f2b9d6`.
- Manual smoke test, fake adapter, via the backend HTTP API (browser not used):
  `LLM_ENABLED=true`, migrated the dev DB, created a case with `POST /events` (staff 105,
  shift 1). The first `GET /cases/1` gave `PENDING`, then `READY` with a `[fake]` text,
  provider `fake`, within about 20 s of the Job tick. `llm_call_log` had one `SUCCEEDED`
  row (470 input, 23 output tokens, cost 0). Five more GETs and a 40 s wait left it at one.
  `.env` was restored byte for byte.

Not tested: real Bedrock and live AWS credentials, a browser view of the page, and any
LINE real-mode behaviour. The `bedrock` adapter is covered only by `Stubber`.
