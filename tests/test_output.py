import os

import pytest

from yt_transcript.errors import AppError
from yt_transcript.output import validate_output, write_output


def test_replace_and_no_replace(tmp_path):
    path = tmp_path / "result"
    write_output(path, b"original")
    with pytest.raises(AppError) as exc:
        write_output(path, b"new", no_clobber=True)
    assert exc.value.info.code == "OUTPUT_EXISTS"
    assert path.read_bytes() == b"original"
    write_output(path, b"new")
    assert path.read_bytes() == b"new"
    assert list(tmp_path.iterdir()) == [path]


def test_symlink(tmp_path):
    path = tmp_path / "result"
    path.symlink_to(tmp_path / "absent")
    with pytest.raises(AppError):
        validate_output(path, no_clobber=True)


def test_race(tmp_path, monkeypatch):
    path = tmp_path / "result"
    link = os.link

    def competing(source, destination):
        path.write_bytes(b"competitor")
        return link(source, destination)

    monkeypatch.setattr(os, "link", competing)
    with pytest.raises(AppError) as exc:
        write_output(path, b"new", no_clobber=True)
    assert exc.value.info.code == "OUTPUT_EXISTS"
    assert path.read_bytes() == b"competitor"
    assert len(list(tmp_path.iterdir())) == 1


def test_link_fail_closed(tmp_path, monkeypatch):
    path = tmp_path / "result"

    def denied(*args):
        raise OSError("secret")

    monkeypatch.setattr(os, "link", denied)
    with pytest.raises(AppError):
        write_output(path, b"new", no_clobber=True)
    assert not list(tmp_path.iterdir())
