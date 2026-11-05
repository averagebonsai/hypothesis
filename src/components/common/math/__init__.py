"""Domain-independent numerical optimization, allocation, and stochastic sampling."""

from .allocation import (
    LPResult,
    optimal_bipartite_matching,
    priority_rationing,
    proportional_rationing,
    solve_linear_program,
)
from .scalar import (
    SCALAR_SEARCH_CONTRACT,
    OptimizationBudgetExceeded,
    ScalarMaximum,
    ScalarSearchSettings,
    maximize_scalar,
)
from .stochastic import SeededSampler

__all__ = [
    "SCALAR_SEARCH_CONTRACT",
    "LPResult",
    "OptimizationBudgetExceeded",
    "ScalarMaximum",
    "ScalarSearchSettings",
    "SeededSampler",
    "maximize_scalar",
    "optimal_bipartite_matching",
    "priority_rationing",
    "proportional_rationing",
    "solve_linear_program",
]
