"""Setup Piper: no downloads at import, validate checksums and tar safety."""
import hashlib
import io
import tarfile
from pathlib import Path

import pytest

from scripts import setup_piper_voice as setup


class _Response:
    def __init__(self, value):
        self._data = io.BytesIO(value)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self._data.close()

    def read(self, length):
        return self._data.read(length)


def test_download_checks_size_and_hash(monkeypatch, tmp_path):
    expected = b"official voice data"
    monkeypatch.setattr(setup.urllib.request, "urlopen", lambda url, timeout: _Response(expected))
    dst = tmp_path / "voice.onnx"
    setup._download(
        "https://huggingface.co/safe", dst,
        max_size=100, expected_size=len(expected),
        sha256=hashlib.sha256(expected).hexdigest(),
    )
    assert dst.read_bytes() == expected


def test_download_rejects_bad_hash_and_cleans_partial(monkeypatch, tmp_path):
    monkeypatch.setattr(setup.urllib.request, "urlopen", lambda url, timeout: _Response(b"wrong"))
    dest = tmp_path / "voice.onnx"
    with pytest.raises(ValueError, match="SHA-256"):
        setup._download("https://huggingface.co/voice", dest, max_size=100, sha256="0" * 64)
    assert not dest.exists()
    assert not (tmp_path / "voice.onnx.partial").exists()


def test_download_rejects_http(monkeypatch, tmp_path):
    with pytest.raises(ValueError, match="HTTPS"):
        setup._download("http://example.com/model.onnx", tmp_path / "voice", 100)


def _archive(path, member):
    with tarfile.open(path, mode="w:gz") as out:
        data = b"ok"
        item = tarfile.TarInfo(member)
        item.size = len(data)
        out.addfile(item, io.BytesIO(data))


def test_refuses_path_traversal_archive(tmp_path):
    archive = tmp_path / "invalid.tar.gz"
    _archive(archive, "piper/../../escape.sh")
    with pytest.raises(ValueError, match="inesperado"):
        setup._safe_extract_piper(archive, tmp_path / "runtime")
    assert not (tmp_path / "escape.sh").exists()


def test_allows_normal_archive(tmp_path):
    archive = tmp_path / "valid.tar.gz"
    _archive(archive, "piper/README.txt")
    setup._safe_extract_piper(archive, tmp_path / "runtime")
    assert (tmp_path / "runtime/piper/README.txt").read_bytes() == b"ok"
