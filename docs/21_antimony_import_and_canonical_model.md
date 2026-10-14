# Antimony Import and the Canonical Executable-Model Representation

## 1. Purpose

Agent 2 now supports two entry paths into one shared, canonical executable-model
representation:

```text
Build from curated biology (Agent 1 handoff)
        |
        v
Canonical ModelSpecification / FullNetwork
        ^
        |
Upload existing Antimony
```

`ModelSpecification` (together with the `FullNetwork` it references) was already this
repository's authoritative top-level contract for the **build** path (Increments 1-10). This
increment extends it additively -- new `rules`/`events`/`observables` fields, a
`source_type`/`source_provenance` pair -- so the same type now also serves as the target of a
real Antimony **import** path, without changing anything about how the build path already
populates it. Antimony itself remains an import/export *format*, never the canonical
representation.

## 2. Canonical model schema (additions)

All additions are on `ModelSpecification` (`app.agent2.types`), alongside the pre-existing
`kinetic_laws`/`parameters`:

```python
rules: tuple[RuleSpecification, ...] = ()
events: tuple[EventSpecification, ...] = ()
observables: tuple[ObservableSpecification, ...] = ()
source_type: ModelSourceType = ModelSourceType.GENERATED
source_provenance: ModelSourceProvenance | None = None
```

- **`RuleSpecification`**: `rule_id`, `rule_type` (`RuleType.ASSIGNMENT`/`RATE`/`ALGEBRAIC`),
  `formula` (opaque text, the same convention `KineticLawSpecification.expression` already
  uses), `variable` (required for `ASSIGNMENT`/`RATE`, always `None` for `ALGEBRAIC` -- SBML's
  own `AlgebraicRule` has no distinguished target), `unit`.
- **`EventSpecification`**: `event_id`, `trigger_formula`, `assignments` (tuple of
  `EventAssignmentSpecification{variable, formula}`), `name`, `use_values_from_trigger_time`,
  `delay_formula`, `priority_formula`.
- **`ObservableSpecification`**: `observable_id`, `name`, `formula`, `unit`. Semantically a
  labeled, derived, non-dynamical reporter quantity. **Antimony/SBML has no native "observable"
  keyword** (confirmed: neither core SBML Level 3 nor Antimony's own grammar declares one --
  this is a PEtab/COPASI-style convention layered on top). An observable round-trips only
  through *this repository's own* exporter/importer pair (§5) -- never inferred from
  arbitrary, third-party Antimony.
- **`ModelSourceType`**: `GENERATED` (the pre-existing build path's default) or `IMPORTED`.
- **`ModelSourceProvenance`**: `original_antimony_text` (verbatim, byte-for-byte, an immutable
  source artifact), `checksum` (sha256 hex digest of that text), `parser_version`, `imported_at`
  (ISO 8601). Enforced one-to-one with `source_type`: `IMPORTED` iff `source_provenance` is
  set.

Two small, additive enum extensions support this without disturbing any existing value's
meaning: `ParameterSource.IMPORTED` and `KineticLawAssignmentSource.IMPORTED` (a value read
verbatim from an external source, outside the existing CURATED/.../PLACEHOLDER precedence
chain entirely), and `KineticLawType.IMPORTED` (distinct from `CUSTOM`: an imported
expression's symbols are already known `species_ids`/`parameter_ids`, safe to render by
substitution, unlike `CUSTOM`'s own curated free text).

## 3. Import flow (`app.agent2.antimony_import`)

```text
Antimony text
    -> antimony.loadAntimonyString()      (real libAntimony)
    -> antimony.getSBMLString()
    -> libsbml.readSBMLFromString()       (real libSBML)
    -> walk the SBML Model -> ModelSpecification / FullNetwork
```

A **new, first-of-its-kind runtime dependency** for this repository: `antimony` and
`python-libsbml` (see `pyproject.toml`), confined entirely to this one package. Chosen over a
hand-rolled parser because Antimony's real grammar (arrows, rate-law expressions, event
trigger/delay/priority math, units) is non-trivial, and a subset parser would carry real,
silent correctness risk. `app.agent2.antimony` (the generator) remains fully dependency-free;
see §7 for how the boundary is enforced.

`import_antimony(antimony_text: str) -> ModelSpecification` is the one public entry point.
Raises `MalformedAntimonySourceError` (libAntimony/libSBML itself rejected the text; its own
message is preserved verbatim) or `UnsupportedAntimonyConstructError` (valid Antimony, but uses
a construct this importer does not support).

Never guesses a biological mapping from a symbol name: a compartment/species/parameter id is
carried through exactly as the source spelled it -- `source_compound_id`/`organism_id` are
always `None` for an imported model.

## 4. Supported / unsupported constructs

**Supported:**

- Compartments (id, name, size, unit, constant).
- Species (id, name, compartment, initial amount *or* concentration, constant, boundary
  condition).
- Reactions (reactants/products with stoichiometry, modifiers, reversibility, a kinetic-law
  expression).
- Global parameters (id, name, value, unit).
- Assignment, rate, and algebraic rules.
- Events (trigger, assignments, `useValuesFromTriggerTime`).

**Unsupported, rejected with a structured error (never silently dropped):**

- Function definitions -- a formula calling one would otherwise look fine as opaque text
  while silently losing the function's own mathematical meaning.
- `InitialAssignment` -- a distinct SBML construct (a one-time, not continuously-enforced,
  computed initial value); not in this increment's own supported-construct list.
- Local, kinetic-law-scoped parameters -- Antimony's own compiler already promotes an
  ordinarily-declared rate constant to a global parameter; encountering a local one signals a
  construct this importer has not verified it handles correctly.
- Any SBML package/plugin extension beyond core (`comp`, `fbc`, ...).

**Supported on import, but not re-serialized on export (disclosed in an export comment, never
silently dropped):**

- Event `delay`/`priority` -- real, live verification against this version of libAntimony
  found no confirmed Antimony-text syntax for either on an `at` event declaration; guessing at
  invalid syntax would be worse than omitting it with a clear comment.

## 5. Export flow and the reversibility correctness fix

`app.agent2.antimony.generate_antimony` (unchanged entry point) now also renders
`rules`/`events`/`observables` when present (new `// rules`/`// events`/`// observables`
sections). A `GENERATED` model -- which never populates any of the three today -- emits
byte-identical text to before this increment.

**Correctness fix, found while building the semantic round trip**: reaction serialization
previously always used `->`, with reversibility disclosed only in a trailing comment. Since
`->` is Antimony's own *reversible* arrow and `=>` its *irreversible* one, a real Antimony/SBML
parser re-reading any previously-generated model would have seen every reaction as reversible,
regardless of the model's own `reversible` value. The arrow now encodes reversibility
correctly (`=>` for a confirmed-irreversible reaction, `->` otherwise); the structured
downstream handoff's own `reversible` field was never affected (it reads
`ReactionSpecification.reversible` directly, never the Antimony arrow) -- see
`agent-integration-harness`'s own real-workflow tests, unaffected.

**Observable round-trip convention**: an `ObservableSpecification` is exported as a plain
assignment rule (`{antimony_id} := {formula};`) immediately followed by a structured comment,
`// agent2:observable id=... name=... [unit=...]`
(`app.agent2.antimony.generator.OBSERVABLE_COMMENT_PREFIX`). `import_antimony` scans the raw
text for this exact comment and, when found, moves the corresponding assignment rule out of
`rules` and into `observables` -- recovering the original `ObservableSpecification` on a
canonical -> Antimony -> canonical round trip through this repository's own exporter/importer
specifically. Arbitrary, third-party Antimony never carries this comment, so it always produces
`observables=()` -- confirmed by test.

## 6. Semantic round-trip guarantees

Verified by `tests/agent2/test_antimony_import.py` (both directions), using a representative
fixture with two compartments, four species with initial values, one irreversible and one
reversible reaction, parameters, kinetic laws, an assignment rule, and an event:

- **Antimony -> canonical -> Antimony**: reaction count, stoichiometry (participant count),
  reversibility (as a multiset -- Antimony-safe identifiers are regenerated on export, so
  individual reaction/species *names* are never expected to match byte-for-byte), species
  initial values, rules, and events are all preserved. The re-exported text is itself real,
  valid, re-importable Antimony.
- **Canonical -> Antimony -> canonical**: verified for both a `GENERATED` model and a
  constructed model carrying a rate rule and an observable.
- Export is deterministic: two calls on the identical model produce byte-identical text.

Semantic equivalence, not byte-for-byte text identity, is the guarantee -- identifiers are
always regenerated through `app.agent2.antimony.naming`'s own deterministic, collision-safe
mapping (now extended with `events`/`observables` categories), exactly like every pre-existing
compartment/species/parameter/reaction identifier already was.

## 7. Dependency isolation

`antimony`/`python-libsbml` are confined to `app/agent2/antimony_import/`. Two tests enforce
both directions of this boundary:

- `tests/agent2/test_contracts.py::test_no_forbidden_library_imported_anywhere_in_app` --
  every other file in `app/` (including the generator, `app/agent2/antimony/`) is still held
  to the original, full prohibition.
- `tests/agent2/test_contracts.py::test_only_antimony_import_package_imports_antimony_or_libsbml`
  -- the flip side: no file *outside* `app/agent2/antimony_import/` may import either library.

`tests/agent2/test_antimony_import_scope.py` mirrors `test_antimony_scope.py`'s own discipline
for the generator (no simulation, fitting, Agent 1/3/4/5 imports, database/network access,
LLM libraries) applied to the importer.

## 8. Relationship to `ModelSpecification` and modularization

`ModelSpecification` keeps its existing meaning exactly: the complete assembled executable
model, regardless of which path produced it. This increment adds no new top-level type.
**Modularization is explicitly a later, separate layer**: this increment implements no module
parsing at all. The representative fixture's own `// module: ...` comments are deliberately
inert text, confirmed by `model.module_specifications == ()` / `model.module_decomposition is
None` for every imported model -- an imported model is never pre-partitioned into modules by
this importer.

## 9. Downstream compatibility

`agent2-downstream-v1` (`build_canonical_downstream_handoff`) is **unchanged**. An imported
model flows through the identical, unmodified function the build path already uses -- every
field that function reads (`model.model_id`, `network.compartments/species/reactions`,
`model.kinetic_laws`, `model.parameters`, `model.model_assumptions`, the full Antimony
artifact) is already populated by the importer. No Agent-1-specific or claim-tracing field is
required. Verified directly: the generated and imported paths' handoff dicts share an
identical top-level key set.
