"""The claims register: every public fact, once, by id.

Templates render claims by id. The build fails on an unknown id, a retired
claim, or a register that breaks the contract below. Every error message
names the claim id (or the entry number when the id itself is the problem),
and load errors start with the file path.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Mapping

import yaml

REQUIRED_KEYS = ("id", "text", "source", "updated", "status")
OPTIONAL_KEYS = ("short",)
STATUSES = ("live", "retired")
FORMS = ("full", "short")
ID_PATTERN = re.compile(r"[a-z0-9][a-z0-9-]{1,60}")
EM_DASH = chr(0x2014)


class ClaimError(Exception):
    """The register is invalid, or a claim cannot be rendered. The message names the claim id."""


@dataclass(frozen=True)
class Claim:
    id: str
    text: str
    short: str | None
    source: str
    updated: datetime.date
    status: str


@dataclass(frozen=True, eq=False)
class ClaimRegister:
    """An immutable set of claims plus `used`, the ids rendered so far in this build."""

    path: Path
    claims: Mapping[str, Claim]
    used: set[str] = field(default_factory=set)

    @classmethod
    def load(cls, path: Path) -> ClaimRegister:
        """Load and validate a register. An empty file or `[]` is an empty register."""
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as err:
            raise ClaimError(f"{path}: cannot read file ({err})") from err
        try:
            data = yaml.safe_load(raw)
        except yaml.YAMLError as err:
            raise ClaimError(f"{path}: not valid YAML ({err})") from err
        if data is None:
            data = []
        if not isinstance(data, list):
            raise ClaimError(f"{path}: the register must be a YAML list of claims")
        claims: dict[str, Claim] = {}
        for number, entry in enumerate(data, start=1):
            claim = _parse_claim(entry, number, path)
            if claim.id in claims:
                raise ClaimError(f"{path}: claim '{claim.id}' is defined more than once")
            claims[claim.id] = claim
        return cls(path=Path(path), claims=MappingProxyType(claims))

    def ids(self) -> frozenset[str]:
        """Every id in the register, live and retired."""
        return frozenset(self.claims)

    def get(self, id: str) -> Claim:
        """The live claim with this id. Unknown and retired ids raise ClaimError."""
        claim = self.claims.get(id) if isinstance(id, str) else None
        if claim is None:
            raise ClaimError(f"{self.path}: claim '{id}' is not in the register")
        if claim.status == "retired":
            raise ClaimError(f"{self.path}: claim '{id}' is retired and cannot be used")
        return claim

    def text(self, id: str, form: str = "full") -> str:
        """Render a claim in its full or short form, and record the id as used."""
        claim = self.get(id)
        if form not in FORMS:
            raise ClaimError(f"{self.path}: claim '{id}': form must be 'full' or 'short', not {form!r}")
        if form == "short":
            if claim.short is None:
                raise ClaimError(f"{self.path}: claim '{id}' has no short form")
            rendered = claim.short
        else:
            rendered = claim.text
        self.used.add(id)
        return rendered


def _parse_claim(entry: object, number: int, path: Path) -> Claim:
    if not isinstance(entry, dict):
        raise ClaimError(f"{path}: claim #{number} must be a mapping with keys {', '.join(REQUIRED_KEYS)}")
    id = _claim_id(entry, number, path)
    _check_keys(entry, id, path)
    text = _string(entry, "text", id, path)
    short = None if entry.get("short") is None else _string(entry, "short", id, path)
    for key, value in (("text", text), ("short", short)):
        if value is not None and EM_DASH in value:
            raise ClaimError(f"{path}: claim '{id}': '{key}' contains an em dash")
    return Claim(
        id=id,
        text=text,
        short=short,
        source=_string(entry, "source", id, path),
        updated=_date(entry, id, path),
        status=_status(entry, id, path),
    )


def _claim_id(entry: dict, number: int, path: Path) -> str:
    if "id" not in entry:
        raise ClaimError(f"{path}: claim #{number} is missing required key(s): id")
    value = entry["id"]
    if not isinstance(value, str) or not ID_PATTERN.fullmatch(value):
        raise ClaimError(
            f"{path}: claim #{number}: id {value!r} must be a string of lowercase letters, "
            "digits and hyphens, 2 to 61 characters, starting with a letter or digit"
        )
    return value


def _check_keys(entry: dict, id: str, path: Path) -> None:
    missing = [key for key in REQUIRED_KEYS if key not in entry]
    if missing:
        raise ClaimError(f"{path}: claim '{id}' is missing required key(s): {', '.join(missing)}")
    unknown = sorted(str(key) for key in entry if key not in REQUIRED_KEYS + OPTIONAL_KEYS)
    if unknown:
        raise ClaimError(f"{path}: claim '{id}' has unknown key(s): {', '.join(unknown)}")


def _string(entry: dict, key: str, id: str, path: Path) -> str:
    value = entry[key]
    if not isinstance(value, str) or not value.strip():
        raise ClaimError(f"{path}: claim '{id}': '{key}' must be a non-empty string")
    return value


def _date(entry: dict, id: str, path: Path) -> datetime.date:
    value = entry["updated"]
    # datetime is a date subclass, so check the exact type.
    if type(value) is not datetime.date:
        raise ClaimError(f"{path}: claim '{id}': 'updated' must be a date written YYYY-MM-DD")
    return value


def _status(entry: dict, id: str, path: Path) -> str:
    value = entry["status"]
    if not isinstance(value, str) or value not in STATUSES:
        raise ClaimError(f"{path}: claim '{id}': 'status' must be one of {', '.join(STATUSES)}")
    return value
