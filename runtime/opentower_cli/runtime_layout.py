from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RuntimeLayout:
    mode: str
    root: Path
    log_dir: Path
    active_file: Path
    transcript_dir: Path
    output_dir: Path
    checkpoint_dir: Path
    incident_dir: Path
    confirmation_dir: Path

    def ensure_dirs(self) -> None:
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.active_file.parent.mkdir(parents=True, exist_ok=True)
        self.transcript_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        self.incident_dir.mkdir(parents=True, exist_ok=True)
        self.confirmation_dir.mkdir(parents=True, exist_ok=True)

    def log_file(self, run_id: str) -> Path:
        return self.log_dir / f"{run_id}.json"

    def checkpoint_file(self, checkpoint_id: str) -> Path:
        return self.checkpoint_dir / f"{checkpoint_id}.json"

    def incident_file(self, incident_id: str) -> Path:
        return self.incident_dir / f"{incident_id}.json"

    def confirmation_file(self, confirmation_id: str) -> Path:
        return self.confirmation_dir / f"{confirmation_id}.json"

    def describe(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "root": self.root.as_posix(),
            "log_dir": self.log_dir.as_posix(),
            "active_file": self.active_file.as_posix(),
            "transcript_dir": self.transcript_dir.as_posix(),
            "output_dir": self.output_dir.as_posix(),
            "checkpoint_dir": self.checkpoint_dir.as_posix(),
            "incident_dir": self.incident_dir.as_posix(),
            "confirmation_dir": self.confirmation_dir.as_posix(),
        }


def repo_runtime_layout(root: Path) -> RuntimeLayout:
    production_root = root / "production"
    return RuntimeLayout(
        mode="repo_global",
        root=root,
        log_dir=production_root / "session-logs",
        active_file=production_root / "session-state" / "active.md",
        transcript_dir=production_root / "session-transcripts",
        output_dir=production_root / "session-outputs",
        checkpoint_dir=production_root / "checkpoints",
        incident_dir=production_root / "incidents",
        confirmation_dir=production_root / "pending-confirmations",
    )
