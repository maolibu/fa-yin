import io
from pathlib import Path
import tarfile

import pytest

from launcher import safe_extract_tar


def _tar_with_member(path: Path, name: str, data: bytes = b"ok") -> None:
    with tarfile.open(path, "w:gz") as archive:
        info = tarfile.TarInfo(name)
        info.size = len(data)
        archive.addfile(info, io.BytesIO(data))


def test_safe_extract_allows_regular_data(tmp_path: Path):
    archive_path = tmp_path / "safe.tar.gz"
    _tar_with_member(archive_path, "nested/value.txt")
    destination = tmp_path / "out"
    with tarfile.open(archive_path, "r:gz") as archive:
        safe_extract_tar(archive, destination)
    assert (destination / "nested" / "value.txt").read_bytes() == b"ok"


def test_safe_extract_rejects_parent_traversal(tmp_path: Path):
    archive_path = tmp_path / "traversal.tar.gz"
    _tar_with_member(archive_path, "../escape.txt")
    destination = tmp_path / "out"
    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(ValueError, match="越界"):
            safe_extract_tar(archive, destination)
    assert not (tmp_path / "escape.txt").exists()


def test_safe_extract_rejects_links(tmp_path: Path):
    archive_path = tmp_path / "link.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "../outside"
        archive.addfile(info)
    with tarfile.open(archive_path, "r:gz") as archive:
        with pytest.raises(ValueError, match="不允許鏈接"):
            safe_extract_tar(archive, tmp_path / "out")
