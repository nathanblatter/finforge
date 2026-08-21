"""Regression tests for the pure FIRE math in services.fire.

Only the DB-free functions are exercised (fi_number, years_to_fi_deterministic,
coast_fire_number, coast_age, simulate_years_to_fi with a fixed seed). The
savings-rate/DB layer is excluded — it carries the known sign-convention bug
tracked as finforge-14.
"""

import math

import numpy as np
import pytest

from services.fire import (
    coast_age,
    coast_fire_number,
    fi_number,
    simulate_years_to_fi,
    years_to_fi_deterministic,
)


def test_fi_number_basic():
    assert fi_number(60_000, 0.04) == pytest.approx(1_500_000)


def test_fi_number_rejects_nonpositive_rate():
    with pytest.raises(ValueError):
        fi_number(60_000, 0)


def test_years_to_fi_already_there():
    assert years_to_fi_deterministic(2_000_000, 10_000, 0.05, 1_500_000) == 0.0


def test_years_to_fi_zero_return_is_linear():
    years = years_to_fi_deterministic(0, 50_000, 0.0, 500_000)
    assert years == pytest.approx(10.0)


def test_years_to_fi_unreachable_returns_none():
    assert years_to_fi_deterministic(100_000, 0, 0.0, 1_500_000) is None


def test_years_to_fi_closed_form_matches_simulation():
    years = years_to_fi_deterministic(100_000, 30_000, 0.05, 1_000_000)
    # verify by compounding the closed-form answer back
    value = 100_000 * (1.05 ** years) + 30_000 * ((1.05 ** years - 1) / 0.05)
    assert value == pytest.approx(1_000_000, rel=1e-6)


def test_coast_fire_number_discounts_target():
    assert coast_fire_number(1_000_000, 0.07, 10) == pytest.approx(
        1_000_000 / (1.07 ** 10)
    )
    assert coast_fire_number(1_000_000, 0.07, 0) == 1_000_000


def test_coast_age_immediate_when_already_coasting():
    target = 1_000_000
    needed_now = coast_fire_number(target, 0.07, 30)
    assert coast_age(needed_now + 1, 0, 0.07, 35, 65, target) == 35


def test_simulate_years_to_fi_deterministic_with_seed():
    returns = np.random.default_rng(1).normal(0.0004, 0.01, 500)
    a = simulate_years_to_fi(returns, 100_000, 30_000, 500_000, n_sims=200, seed=42)
    b = simulate_years_to_fi(returns, 100_000, 30_000, 500_000, n_sims=200, seed=42)
    assert a == b
    assert 0 < a["years_to_fi_p10"] <= a["years_to_fi_p50"] <= a["years_to_fi_p90"]


def test_simulate_years_to_fi_already_hit_target():
    returns = np.random.default_rng(1).normal(0.0004, 0.01, 500)
    out = simulate_years_to_fi(returns, 600_000, 0, 500_000, n_sims=50, seed=7)
    assert out["years_to_fi_p90"] == 0.0
    assert out["prob_never_by_cap"] == 0.0
