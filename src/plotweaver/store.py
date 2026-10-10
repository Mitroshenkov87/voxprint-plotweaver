"""One folder per book: JSON artefacts, a checkpoint, and the SQLite canon."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from plotweaver.atomic import read_json, write_json, write_text
from plotweaver.domain import BookRequest, request_from_dict, request_to_dict


class Checkpoint:
    """Steps that finished. A crash before mark() runs the step again."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.finished: list[str] = []
        if path.is_file():
            payload = read_json(path)
            if isinstance(payload, dict):
                raw = payload.get("finished") or []
                if isinstance(raw, list):
                    self.finished = [str(item) for item in raw]

    def done(self, step_id: str) -> bool:
        return step_id in self.finished

    def mark(self, step_id: str) -> None:
        if step_id not in self.finished:
            self.finished.append(step_id)
        write_json(self.path, {"finished": self.finished})


class Project:
    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def open_or_create(cls, root: Path, request: BookRequest) -> Project:
        root.mkdir(parents=True, exist_ok=True)
        project = cls(root)
        if not project.request_path.is_file():
            write_json(project.request_path, request_to_dict(request))
            project.set_status("created", None)
        return project

    @property
    def request_path(self) -> Path:
        return self.root / "project.json"

    @property
    def artefacts(self) -> Path:
        return self.root / "artefacts"

    @property
    def export_dir(self) -> Path:
        return self.root / "export"

    def request(self) -> BookRequest:
        payload = read_json(self.request_path)
        if not isinstance(payload, dict):
            raise TypeError("project.json is not an object")
        return request_from_dict(payload)

    def save_request(self, request: BookRequest) -> None:
        write_json(self.request_path, request_to_dict(request))

    def checkpoint(self) -> Checkpoint:
        return Checkpoint(self.root / "checkpoint.json")

    def status(self) -> dict[str, Any]:
        path = self.root / "status.json"
        if not path.is_file():
            return {"state": "created", "gate": None, "approved": []}
        payload = read_json(path)
        if isinstance(payload, dict):
            return payload
        return {"state": "created", "gate": None, "approved": []}

    def set_status(self, state: str, gate: str | None) -> None:
        current = self.status()
        approved = current.get("approved") if isinstance(current.get("approved"), list) else []
        write_json(self.root / "status.json", {"state": state, "gate": gate, "approved": approved})

    def approved_gates(self) -> set[str]:
        raw = self.status().get("approved")
        if not isinstance(raw, list):
            return set()
        return {str(item) for item in raw}

    def approve_gate(self, gate: str) -> None:
        current = self.status()
        raw = current.get("approved")
        approved = [str(item) for item in raw] if isinstance(raw, list) else []
        if gate not in approved:
            approved.append(gate)
        write_json(
            self.root / "status.json",
            {
                "state": str(current.get("state") or "created"),
                "gate": current.get("gate"),
                "approved": approved,
            },
        )

    def write_artefact(self, relative: str, payload: Any) -> None:
        write_json(self.artefacts / relative, payload)

    def read_artefact(self, relative: str) -> Any:
        return read_json(self.artefacts / relative)

    def write_raw(self, step_id: str, text: str) -> None:
        safe = step_id.replace(":", "-")
        write_text(self.root / "raw" / f"{safe}.txt", text)

    def canon(self) -> Canon:
        return Canon(self.root / "canon.sqlite")


class Canon:
    """Characters, facts, timeline, threads, knowledge. Each fact keeps its chapter."""

    def __init__(self, path: Path) -> None:
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path)
        self._db.execute("PRAGMA journal_mode=WAL")
        self._db.executescript(
            """
            CREATE TABLE IF NOT EXISTS characters (
                name TEXT PRIMARY KEY,
                gender TEXT,
                role TEXT,
                goals TEXT,
                secrets TEXT,
                voice TEXT,
                arc TEXT,
                pronunciation TEXT,
                source TEXT
            );
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY,
                text TEXT NOT NULL,
                chapter_id TEXT,
                paragraph INTEGER
            );
            CREATE TABLE IF NOT EXISTS timeline (
                id INTEGER PRIMARY KEY,
                chapter_id TEXT,
                description TEXT
            );
            CREATE TABLE IF NOT EXISTS threads (
                id INTEGER PRIMARY KEY,
                chapter_id TEXT,
                description TEXT,
                status TEXT
            );
            CREATE TABLE IF NOT EXISTS knowledge (
                id INTEGER PRIMARY KEY,
                chapter_id TEXT,
                character_name TEXT,
                fact TEXT
            );
            """
        )
        self._db.commit()

    def close(self) -> None:
        self._db.close()

    def __enter__(self) -> Canon:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def seed_characters(self, characters: list[dict[str, Any]], source: str) -> None:
        for character in characters:
            name = str(character.get("name") or "").strip()
            if not name:
                continue
            self._db.execute(
                """
                INSERT INTO characters
                    (name, gender, role, goals, secrets, voice, arc, pronunciation, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(name) DO UPDATE SET
                    gender = excluded.gender,
                    role = excluded.role,
                    goals = excluded.goals,
                    secrets = excluded.secrets,
                    voice = excluded.voice,
                    arc = excluded.arc,
                    pronunciation = excluded.pronunciation,
                    source = excluded.source
                """,
                (
                    name,
                    str(character.get("gender") or ""),
                    str(character.get("role") or ""),
                    str(character.get("goals") or ""),
                    str(character.get("secrets") or ""),
                    str(character.get("voice") or ""),
                    str(character.get("arc") or ""),
                    str(character.get("pronunciation") or ""),
                    source,
                ),
            )
        self._db.commit()

    def names(self) -> list[str]:
        rows = self._db.execute("SELECT name FROM characters ORDER BY name").fetchall()
        return [str(row[0]) for row in rows]

    def pronunciations(self) -> list[tuple[str, str]]:
        rows = self._db.execute(
            "SELECT name, pronunciation FROM characters WHERE pronunciation != ''"
        ).fetchall()
        pairs: list[tuple[str, str]] = []
        for name, spoken in rows:
            surface = str(name)
            stressed = str(spoken)
            pairs.append((surface, stressed))
            given = surface.split()[0] if surface.split() else ""
            spoken_given = stressed.split()[0] if stressed.split() else ""
            if given and spoken_given and given != spoken_given:
                pairs.append((given, spoken_given))
        pairs.sort(key=lambda item: len(item[0]), reverse=True)
        return pairs

    def characters(self) -> list[dict[str, str]]:
        """Story-bible characters in insertion order."""
        rows = self._db.execute(
            """
            SELECT name, gender, role, goals, secrets, voice, arc, pronunciation
            FROM characters ORDER BY rowid
            """
        ).fetchall()
        keys = ("name", "gender", "role", "goals", "secrets", "voice", "arc", "pronunciation")
        return [{key: str(row[index]) for index, key in enumerate(keys)} for row in rows]

    def commit_extraction(self, chapter_id: str, payload: dict[str, Any]) -> None:
        for fact in _dicts(payload.get("facts")):
            self._db.execute(
                "INSERT INTO facts (text, chapter_id, paragraph) VALUES (?, ?, ?)",
                (str(fact.get("text") or ""), chapter_id, int(fact.get("paragraph") or 0)),
            )
        for event in _dicts(payload.get("timeline")):
            self._db.execute(
                "INSERT INTO timeline (chapter_id, description) VALUES (?, ?)",
                (chapter_id, str(event.get("description") or "")),
            )
        for thread in _dicts(payload.get("threads")):
            self._db.execute(
                "INSERT INTO threads (chapter_id, description, status) VALUES (?, ?, ?)",
                (
                    chapter_id,
                    str(thread.get("description") or ""),
                    str(thread.get("status") or "open"),
                ),
            )
        for item in _dicts(payload.get("knowledge")):
            self._db.execute(
                "INSERT INTO knowledge (chapter_id, character_name, fact) VALUES (?, ?, ?)",
                (chapter_id, str(item.get("character") or ""), str(item.get("fact") or "")),
            )
        self._db.commit()


def _dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]
