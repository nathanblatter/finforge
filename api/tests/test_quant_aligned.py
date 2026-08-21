"""Regression tests for date-based return alignment (finforge-34)."""

import numpy as np

from services.quant import aligned_returns


def test_aligned_returns_inner_joins_on_dates():
    # B is missing day 2; alignment must drop that date for both symbols,
    # not shift B's series positionally.
    a = [(1, 100.0), (2, 110.0), (3, 121.0), (4, 133.1)]
    b = [(1, 50.0), (3, 60.5), (4, 66.55)]
    returns, symbols = aligned_returns({"A": a, "B": b})
    assert symbols == ["A", "B"]
    assert returns.shape == (2, 2)  # dates 1,3,4 → 2 return rows
    # A: 100→121 then 121→133.1 ; B: 50→60.5 then 60.5→66.55 (both +21%, +10%)
    np.testing.assert_allclose(returns[:, 0], [0.21, 0.10], rtol=1e-9)
    np.testing.assert_allclose(returns[:, 1], [0.21, 0.10], rtol=1e-9)


def test_aligned_returns_identical_series_perfectly_correlated():
    a = [(i, 100.0 * (1.01 ** i)) for i in range(10)]
    b = [(i, 200.0 * (1.01 ** i)) for i in range(10)]
    returns, _ = aligned_returns({"A": a, "B": b})
    corr = np.corrcoef(returns[:, 0], returns[:, 1])[0, 1]
    assert corr > 0.999999


def test_aligned_returns_empty_and_disjoint():
    empty, syms = aligned_returns({})
    assert empty.size == 0 and syms == []
    disjoint, _ = aligned_returns({"A": [(1, 1.0), (2, 2.0)], "B": [(3, 1.0), (4, 2.0)]})
    assert disjoint.size == 0
