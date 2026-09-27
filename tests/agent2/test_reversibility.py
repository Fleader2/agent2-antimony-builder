"""Tests for the conservative reversibility default (``app.agent2.reversibility``).

Pure unit tests: no database, no assembly pipeline.
"""

from __future__ import annotations

import pytest

from app.agent2.reversibility import (
    REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE,
    ReversibilityBasis,
    classify_reversibility_basis,
    effective_reversible,
    is_assumed,
)

# --- classify_reversibility_basis ---------------------------------------------------------------


def test_curated_true_classifies_as_curated_reversible():
    assert classify_reversibility_basis(True) is ReversibilityBasis.CURATED_REVERSIBLE


def test_curated_false_classifies_as_curated_irreversible():
    assert classify_reversibility_basis(False) is ReversibilityBasis.CURATED_IRREVERSIBLE


def test_none_classifies_as_assumed_reversible():
    assert classify_reversibility_basis(None) is ReversibilityBasis.ASSUMED_REVERSIBLE


# --- effective_reversible ------------------------------------------------------------------------


def test_effective_reversible_true_passes_through():
    assert effective_reversible(True) is True


def test_effective_reversible_false_passes_through():
    assert effective_reversible(False) is False


def test_effective_reversible_none_becomes_true():
    assert effective_reversible(None) is True


# --- is_assumed -----------------------------------------------------------------------------------


@pytest.mark.parametrize(("value", "expected"), [(True, False), (False, False), (None, True)])
def test_is_assumed(value, expected):
    assert is_assumed(value) is expected


# --- Determinism / no fabrication -----------------------------------------------------------------


def test_functions_are_pure_and_deterministic():
    for value in (True, False, None):
        assert classify_reversibility_basis(value) == classify_reversibility_basis(value)
        assert effective_reversible(value) == effective_reversible(value)


def test_reason_code_is_a_plain_string_not_an_enum_member():
    assert isinstance(REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE, str)
    assert REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE == (
        "REVERSIBILITY_ASSUMED_FROM_UNRESOLVED_EVIDENCE"
    )
