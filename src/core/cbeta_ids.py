"""CBETA Bookcase work/file ID parsing shared by reader, ETL, and tests.

Bookcase names have the form ``{canon}{volume}n{work}_{juan}.xml``.  Both
the canon and the work identifier can contain letters, for example:

* ``CC001n0001_001.xml``
* ``J37nB392_001.xml``
* ``TX00na001_001.xml``
* ``T47n1987A_001.xml``

Parsing is deliberately anchored.  A partial match must never silently turn
``T1987A`` and ``T1987B`` into the same work.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable


_WORK_RE = re.compile(r"[A-Za-z]*\d+[A-Za-z]*")
_BOOKCASE_ID_RE = re.compile(
    r"(?P<canon>[A-Z]+)"
    r"(?P<volume>\d+)"
    r"n"
    r"(?P<work>[A-Za-z]*\d+[A-Za-z]*)"
    r"(?:_(?P<juan>\d+))?"
)

T0220_SUBWORK_IDS = frozenset(f"T0220{letter}" for letter in "abcdefghijklmno")


@dataclass(frozen=True, slots=True)
class BookcaseId:
    """A parsed Bookcase file/work identifier."""

    canon: str
    volume: str
    work: str
    juan: int | None = None

    @property
    def file_id(self) -> str:
        """Volume-qualified XML ID, such as ``J37nB392``."""
        return f"{self.canon}{self.volume}n{self.work}"

    @property
    def sutra_id(self) -> str:
        """Stable work ID used by navigation/search, such as ``JB392``."""
        return f"{self.canon}{self.work}"

    @property
    def volume_id(self) -> str:
        return f"{self.canon}{self.volume}"

    @property
    def filename(self) -> str:
        if self.juan is None:
            return f"{self.file_id}.xml"
        return f"{self.file_id}_{self.juan:03d}.xml"


def parse_bookcase_id(value: str | Path, *, require_juan: bool = False) -> BookcaseId:
    """Parse a Bookcase filename, stem, or XML ID using a full match.

    ``ValueError`` is raised for every unsupported or partially matched value.
    """
    text = Path(value).name if isinstance(value, Path) else str(value).rsplit("/", 1)[-1]
    if text.lower().endswith(".xml"):
        text = text[:-4]
    match = _BOOKCASE_ID_RE.fullmatch(text)
    if match is None:
        raise ValueError(f"invalid CBETA Bookcase ID: {value!s}")
    juan_text = match.group("juan")
    if require_juan and juan_text is None:
        raise ValueError(f"Bookcase filename has no juan suffix: {value!s}")
    return BookcaseId(
        canon=match.group("canon"),
        volume=match.group("volume"),
        work=match.group("work"),
        juan=int(juan_text) if juan_text is not None else None,
    )


def try_parse_bookcase_id(
    value: str | Path, *, require_juan: bool = False
) -> BookcaseId | None:
    try:
        return parse_bookcase_id(value, require_juan=require_juan)
    except ValueError:
        return None


def discover_bookcase_xml_files(xml_root: str | Path) -> list[Path]:
    """Return every valid Bookcase XML below ``xml_root``.

    Any ``*.xml`` with an unsupported name fails the scan instead of being
    silently omitted.
    """
    root = Path(xml_root)
    files = sorted(root.rglob("*.xml"))
    invalid = [path for path in files if try_parse_bookcase_id(path, require_juan=True) is None]
    if invalid:
        sample = ", ".join(str(path) for path in invalid[:5])
        raise ValueError(f"{len(invalid)} invalid Bookcase XML filename(s): {sample}")
    return files


def split_sutra_id(value: str, canon_codes: Iterable[str]) -> tuple[str, str]:
    """Split a navigation work ID using known canon codes.

    Known codes remove the ambiguity between multi-letter canons (``GA``) and
    uppercase work prefixes (``J`` + ``B392``).
    """
    for canon in sorted(set(canon_codes), key=lambda code: (-len(code), code)):
        if value.startswith(canon):
            work = value[len(canon):]
            if _WORK_RE.fullmatch(work):
                return canon, work
    raise ValueError(f"cannot split CBETA sutra ID with known canons: {value}")


def filename_matches_xml_id(filename_id: BookcaseId, xml_id: BookcaseId) -> bool:
    """Validate the sole known Bookcase filename/XML-ID normalization.

    CBETA stores the 600 files of ``T0220a`` through ``T0220o`` under base
    filenames ``T05n0220`` through ``T07n0220``.  Every other file must have
    an exact volume-qualified ID match.
    """
    if filename_id.file_id == xml_id.file_id:
        return True
    return (
        filename_id.canon == xml_id.canon
        and filename_id.volume == xml_id.volume
        and filename_id.sutra_id == "T0220"
        and xml_id.sutra_id in T0220_SUBWORK_IDS
    )
