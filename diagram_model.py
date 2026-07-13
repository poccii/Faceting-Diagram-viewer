from dataclasses import dataclass, field
from facet_model import Facet

@dataclass
class Diagram:
    title: str = ""
    author: str = ""
    index_gear: int = 64
    facets: list[Facet] = field(default_factory=list)
    # ↓ 追加: 切削手順を格納するリスト
    instructions: list[str] = field(default_factory=list)