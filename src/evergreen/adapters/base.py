from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from evergreen.manifest import Manifest


@dataclass
class StageContext:
    stage: str
    stage_dir: Path
    video_dir: Path
    manifest: Manifest


@dataclass
class Done:
    outputs: list[Path]


@dataclass
class NeedsManual:
    instructions: Path
    expected_files: list[str]


StageResult = Done | NeedsManual


class Adapter(Protocol):
    name: str

    def run(self, ctx: StageContext) -> StageResult: ...
