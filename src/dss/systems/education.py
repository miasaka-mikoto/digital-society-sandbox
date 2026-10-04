"""Study and skill acquisition model."""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Any

from .economy import Economy, Good


def _g(o, n, d=None): return o.get(n, d) if isinstance(o, dict) else getattr(o, n, d)
def _s(o, n, v): o.__setitem__(n, v) if isinstance(o, dict) else setattr(o, n, v)


@dataclass
class Course:
    course_id: str
    skill: str
    cost: float
    duration_days: int = 30
    capacity: int = 30
    enrolled: list[Any] = field(default_factory=list)


class EducationSystem:
    def __init__(self, economy: Economy, courses: list[Course] | None = None) -> None:
        self.economy, self.courses = economy, courses or []
        # Allows the generic economy purchase path to treat courses as services
        # rather than requiring a physical inventory item.
        self.service_provider = True
        self.progress: dict[tuple[str, str], int] = {}

    def enroll(self, citizen: Any, course: Course, day: int) -> bool:
        if len(course.enrolled) >= course.capacity or citizen in course.enrolled: return False
        if not self.economy.purchase(citizen, self, Good.EDUCATION, 1, day,
                                     unit_price=course.cost, reason="education"):
            return False
        course.enrolled.append(citizen)
        self.progress[(str(_g(citizen, "agent_id", id(citizen))), course.course_id)] = 0
        return True

    def study(self, citizen: Any, course: Course, day: int, *, hours: float = 1.0) -> bool:
        key = (str(_g(citizen, "agent_id", id(citizen))), course.course_id)
        if citizen not in course.enrolled or key not in self.progress: return False
        self.progress[key] += max(1, int(hours))
        if self.progress[key] >= course.duration_days:
            self.acquire_skill(citizen, course.skill, amount=0.1)
            self.progress[key] = 0
        return True

    def acquire_skill(self, citizen: Any, skill: str, *, amount: float = 0.1) -> float:
        skills = _g(citizen, "skills", None)
        if skills is None: skills = {}; _s(citizen, "skills", skills)
        skills[skill] = min(1.0, float(skills.get(skill, 0.0)) + max(0.0, amount))
        return skills[skill]
