"""Agent 1 -> Agent 2 Translation Layer's own error hierarchy.

Every error here is raised only for a genuine structural problem in the
raw handoff payload itself (a missing required key, a value of the wrong
shape) -- never for a scientific or heuristic judgment, and never for
"this field could not be resolved" (that is a legitimate ``None``/``()``,
not an error -- see ``translate.py``'s own module docstring).

Subclasses ``ValueError``, mirroring every other Agent 2 package's own
error-hierarchy convention (``app.agent2.network.errors
.NetworkAssemblyError`` and siblings).
"""

from __future__ import annotations


class HandoffTranslationError(ValueError):
    """Base class for every Agent 1 -> Agent 2 translation failure."""


class MalformedHandoffPayloadError(HandoffTranslationError):
    """The raw payload is missing a required key, or a value has the wrong shape.

    Never raised for a field that is legitimately absent/``None`` in
    Agent 1's own contract (e.g. an unresolved ``reaction_id``, an empty
    ``protein_ids``) -- only for a payload that does not match the
    documented shape at all (e.g. ``kinetic_measurements`` is not a list,
    or an entry is missing ``kinetic_measurement_id``).
    """


__all__ = ["HandoffTranslationError", "MalformedHandoffPayloadError"]
