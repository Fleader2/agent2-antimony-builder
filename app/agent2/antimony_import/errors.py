"""Antimony Import increment: the import error hierarchy.

All subclass ``ValueError``, mirroring every other ``app.agent2`` error hierarchy's own
convention (e.g. ``app.agent2.build_request.errors.BuildRequestError``) -- a caller that only
catches ``ValueError`` still catches every import failure without needing to know this module
exists.
"""

from __future__ import annotations


class AntimonyImportError(ValueError):
    """Base class for every Antimony-import failure."""


class MalformedAntimonySourceError(AntimonyImportError):
    """The supplied text is not valid Antimony -- libAntimony itself rejected it (a syntax
    error, an undeclared reference, ...). The real parser's own error message is preserved
    verbatim in this exception's message; nothing here re-interprets or guesses at the cause.
    """


class UnsupportedAntimonyConstructError(AntimonyImportError):
    """The supplied Antimony is syntactically valid but uses a construct this importer does
    not support (e.g. a function definition, an ``InitialAssignment``, a local kinetic-law
    parameter, or an SBML package/plugin extension) -- rejected deterministically rather than
    silently dropping the construct's own semantics or guessing a substitute. See
    ``app.agent2.antimony_import.parser``'s own module docstring for the exact supported/
    unsupported construct list.
    """
