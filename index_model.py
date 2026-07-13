from dataclasses import dataclass, field


@dataclass
class IndexSet:
    original: list[int] = field(default_factory=list)
    jamb: list[str] = field(default_factory=list)