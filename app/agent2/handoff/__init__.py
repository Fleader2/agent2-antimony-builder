"""Agent 1 -> Agent 2 Translation Layer.

Public API: ``translate_agent1_view_to_agent2``. See ``translate.py`` for
the full contract and ``docs/14_agent1_agent2_translation_layer.md`` for
the field-by-field mapping this package implements.
"""

from __future__ import annotations

from app.agent2.handoff.errors import HandoffTranslationError, MalformedHandoffPayloadError
from app.agent2.handoff.translate import translate_agent1_view_to_agent2

__all__ = [
    "HandoffTranslationError",
    "MalformedHandoffPayloadError",
    "translate_agent1_view_to_agent2",
]
