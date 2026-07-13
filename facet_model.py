from dataclasses import dataclass, field
from index_model import IndexSet


@dataclass
class Facet:

    id: int = 0

    name: str = ""

    section: str = ""

    angle: float = 0.0

    index: IndexSet = field(default_factory=IndexSet)

    has_name: bool = False

    is_virtual: bool = False

    # ↓ 追加: ファセットごとの注釈を保持するフィールド
    instruction: str = ""