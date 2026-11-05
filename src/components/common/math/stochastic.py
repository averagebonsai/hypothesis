"""Deterministic, seeded distribution sampling for reproducible stochastic simulation events."""

import hashlib
from collections.abc import Sequence
from math import isfinite
from typing import TypeVar

import numpy as np

from simulation_core.types import FrozenModel

T = TypeVar("T")


class SeededSampler(FrozenModel):
    """Seed-stable stochastic distribution sampler.

    Generates identical draws given the same base_seed, tick, and domain_key,
    guaranteeing that simulation event replay and checkpoint resumption are 100% deterministic.
    """

    base_seed: int

    def _generator(self, tick: int, domain_key: str) -> np.random.Generator:
        digest = hashlib.sha256(f"{self.base_seed}:{tick}:{domain_key}".encode()).digest()
        seed_int = int.from_bytes(digest[:8], "big")
        return np.random.Generator(np.random.PCG64(seed_int))

    def uniform(
        self, tick: int, domain_key: str, low: float = 0.0, high: float = 1.0
    ) -> float:
        if not (isfinite(low) and isfinite(high)) or low > high:
            raise ValueError("Invalid uniform bounds")
        rng = self._generator(tick, domain_key)
        return float(rng.uniform(low, high))

    def normal(
        self, tick: int, domain_key: str, mean: float = 0.0, std: float = 1.0
    ) -> float:
        if not (isfinite(mean) and isfinite(std)) or std < 0:
            raise ValueError("Invalid normal parameters")
        rng = self._generator(tick, domain_key)
        return float(rng.normal(mean, std))

    def bernoulli(self, tick: int, domain_key: str, p: float = 0.5) -> bool:
        if not isfinite(p) or not 0.0 <= p <= 1.0:
            raise ValueError("Probability p must be between 0 and 1")
        rng = self._generator(tick, domain_key)
        return bool(rng.uniform(0.0, 1.0) < p)

    def poisson(self, tick: int, domain_key: str, lam: float) -> int:
        if not isfinite(lam) or lam < 0:
            raise ValueError("Poisson parameter lam must be non-negative")
        rng = self._generator(tick, domain_key)
        return int(rng.poisson(lam))

    def choice(
        self,
        tick: int,
        domain_key: str,
        options: Sequence[T],
        weights: Sequence[float] | None = None,
    ) -> T:
        if not options:
            raise ValueError("options cannot be empty")
        rng = self._generator(tick, domain_key)
        if weights is not None:
            if len(weights) != len(options):
                raise ValueError("weights must match options length")
            total = sum(weights)
            if total <= 0 or not isfinite(total):
                raise ValueError("Sum of weights must be positive and finite")
            normalized = [w / total for w in weights]
            index = int(rng.choice(len(options), p=normalized))
        else:
            index = int(rng.choice(len(options)))
        return options[index]

    def shuffle(self, tick: int, domain_key: str, items: Sequence[T]) -> tuple[T, ...]:
        rng = self._generator(tick, domain_key)
        result = list(items)
        rng.shuffle(result)
        return tuple(result)
