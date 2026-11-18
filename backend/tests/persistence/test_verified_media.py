import hashlib
import os


def test_download_is_fully_verified_even_when_metadata_and_samples_match(monkeypatch, tmp_path):
    size = 2 * 1024 * 1024
    good = bytes(size)
    sha = hashlib.sha256(good).hexdigest()
    target = tmp_path / "weight"
    target.write_bytes(good)
    assert assets._verified(target, size, sha)
    stamp = target.stat()
    with target.open("r+b") as stream:
        stream.seek(12000)
        stream.write(b"X")
    os.utime(target, ns=(stamp.st_atime_ns, stamp.st_mtime_ns))
    assert not assets._verified(target, size, sha, downloaded=True)
    assert not target.with_name(".weight.verified.json").exists()

import pytest

from neveai.utils import pinned_media_asset as assets


def test_first_install_mirror_recovery_and_warm_offline(monkeypatch, tmp_path):
    value = b"test fixture"
    sha = hashlib.sha256(value).hexdigest()
    calls = []
    def download(**kwargs):
        calls.append(kwargs["revision"])
        (tmp_path / "mesh.bin").write_bytes(b"x"*len(value) if kwargs["revision"] == "a" else value)
    monkeypatch.setattr(assets, "hf_hub_download", download)
    args = (tmp_path, "mesh.bin", len(value), sha, [("origin", "a"), ("mirror", "b")])
    target = assets.ensure_pinned_asset(*args)
    assert calls == ["a","b"] and target.read_bytes() == value
    assert assets.ensure_pinned_asset(*args) == target and calls == ["a","b"]
    target.write_bytes(b"!"*len(value))
    os.utime(target, (100,100))
    assert assets.ensure_pinned_asset(*args).read_bytes() == value
    assert calls == ["a","b","a","b"]


def test_bad_weights_never_accepted(monkeypatch, tmp_path):
    monkeypatch.setattr(assets, "hf_hub_download", lambda **kwargs: (tmp_path/"m").write_bytes(b"bad"))
    with pytest.raises(RuntimeError):
        assets.ensure_pinned_asset(tmp_path, "m", 3, "0"*64, [("mirror","fixed")])
    assert not list(tmp_path.glob("*.verified.json"))
