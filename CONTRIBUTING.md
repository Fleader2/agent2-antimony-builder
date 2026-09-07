# Contributing to Agent 2 — Antimony Builder

## Repository purpose

This repository implements Agent 2: it consumes Agent 1's curated
biochemical knowledge (from the separate `agent1-biochemical-curator`
repository, via `docs/02_agent1_handoff_contract.md`) and transforms it
into Antimony model specifications. See `docs/01_agent2_architecture.md`
for the full architecture.

## Scope boundaries

Before implementing anything, confirm it belongs to Agent 2:

- Agent 2 builds models. It does not curate literature (Agent 1), validate
  models beyond minimal syntax/internal-contract checks (Agent 3),
  simulate or fit parameters (Agent 4), or critique model biology
  (Agent 5).
- Agent 2 never imports Agent 1's runtime package, ORM models, or database
  session objects — only the local, decoupled handoff contract
  (`app.agent2.types.Agent1CuratedKnowledgeViewContract`).
- Agent 2 never adds a Tellurium, COPASI, `libsbml`/`libroadrunner`, or
  `antimony` runtime dependency until an increment's own specification
  explicitly requires it and says so.

If you are unsure whether something belongs in this repository, check
`docs/01_agent2_architecture.md` §22 (explicit non-goals) before writing
code.

## Development workflow

1. Read the relevant specification document under `docs/` before
   implementing or changing behavior.
2. Implement the smallest coherent increment — do not jump ahead to a
   later increment's scope (see `README.md`'s roadmap).
3. Add or update tests for every behavior change.
4. Run `ruff check .` and `pytest` before considering a change complete.
5. Update the relevant `docs/` contract in the same change as any behavior
   it describes — do not let documentation and code drift apart.

## Tests required

- Every new contract type needs at least: a construction test, a
  validation-failure test for its required fields, and an immutability
  test.
- Every new increment that introduces a heuristic (e.g. boundary
  assessment rules) needs a test for each rule's stated behavior, not just
  a happy-path smoke test.
- Scope-safety tests (`tests/agent2/test_contracts.py`) must keep passing:
  no Tellurium/COPASI/`libsbml`/`antimony` import, no Agent 1 runtime
  import, no simulation/parameter-fitting/model-critic implementation.

## No behavior changes without contract updates

A change to what a public type or function accepts, returns, or means
must be accompanied by an update to the `docs/` file that describes it.
Do not silently widen or narrow a contract's meaning in code only.

## Dependencies

- No Agent 1 runtime dependency (package import, database driver, or
  connector) belongs in this repository.
- No Tellurium, COPASI, `libsbml`/`libroadrunner`, or `antimony` runtime
  dependency until an increment specification explicitly calls for
  Antimony generation or downstream execution and says so.
- Keep `pyproject.toml` dependencies minimal; prefer the standard library.
