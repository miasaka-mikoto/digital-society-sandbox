"""Small deterministic random-source wrapper."""
from __future__ import annotations
import random
from typing import Sequence, TypeVar

T = TypeVar("T")


class SeedRNG:
    def __init__(self, seed: int):
        self.seed = int(seed)
        self._r = random.Random(self.seed)

    def random(self) -> float:
        return self._r.random()

    def uniform(self, a: float, b: float) -> float:
        return self._r.uniform(a, b)

    def randint(self, a: int, b: int) -> int:
        return self._r.randint(a, b)

    def choice(self, seq: Sequence[T]) -> T:
        return self._r.choice(seq)

    def sample(self, population: Sequence[T], k: int):
        return self._r.sample(population, min(k, len(population)))

    def chance(self, probability: float) -> bool:
        return self.random() < max(0.0, min(1.0, probability))

    def state(self):
        return self._r.getstate()

    def set_state(self, state) -> None:
        self._r.setstate(state)
