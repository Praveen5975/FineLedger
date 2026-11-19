from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Alert:
    """What an agent produced. Agents propose and explain; they never decide or settle."""
    agent: str
    level: str  # info | green | amber | red
    subject: str
    summary: str
    details: dict = field(default_factory=dict)
    cites: list[int] = field(default_factory=list)
    to: list[str] = field(default_factory=list)
