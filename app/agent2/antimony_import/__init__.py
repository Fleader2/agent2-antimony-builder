"""Antimony Import increment: Antimony text -> canonical ``ModelSpecification``.

Public API: ``import_antimony`` (parse), ``MalformedAntimonySourceError``/
``UnsupportedAntimonyConstructError`` (the error hierarchy). See ``parser``'s own module
docstring for the full supported/unsupported construct list and ``errors`` for the exception
hierarchy.
"""

from __future__ import annotations

from app.agent2.antimony_import.errors import (
    AntimonyImportError,
    MalformedAntimonySourceError,
    UnsupportedAntimonyConstructError,
)
from app.agent2.antimony_import.parser import import_antimony
from app.agent2.antimony_import.version import ANTIMONY_IMPORT_PARSER_VERSION

__all__ = [
    "ANTIMONY_IMPORT_PARSER_VERSION",
    "AntimonyImportError",
    "MalformedAntimonySourceError",
    "UnsupportedAntimonyConstructError",
    "import_antimony",
]
