"""Model trial for round 6 PR B2 (docs/round6/round6-contract-draft.md, section 3.2).

An internal tool, never reached from an API route. The trial calls the LLM only through
llm_gateway with the MODEL_TRIAL work type, so its calls are counted against the run's own
cap and written to llm_call_log like every other call.
"""
