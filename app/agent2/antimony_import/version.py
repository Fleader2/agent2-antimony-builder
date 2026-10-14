"""Antimony Import increment: the parser's own policy version.

Recorded on every ``ModelSourceProvenance.parser_version`` this package produces -- bumped
whenever this package's own parsing *policy* changes (which constructs are supported, how a
construct maps onto the canonical representation), independent of the real ``antimony``/
``libsbml`` library versions actually installed (also recorded, separately, alongside it --
see ``parser.import_antimony``) and independent of ``AGENT2_CONTRACT_VERSION``.
"""

from __future__ import annotations

ANTIMONY_IMPORT_PARSER_VERSION = "antimony-import-v1"

__all__ = ["ANTIMONY_IMPORT_PARSER_VERSION"]
