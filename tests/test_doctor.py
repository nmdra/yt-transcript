import subprocess
from collections import namedtuple
from types import SimpleNamespace

from yt_transcript import doctor


def test_all_checks_mocked(monkeypatch):
    calls = []
    monkeypatch.setattr(doctor.shutil, "which", lambda name: name)
    monkeypatch.setattr(
        doctor.metadata,
        "version",
        lambda name: "0.8.0" if name == "yt-dlp-ejs" else "2.3.0",
    )
    monkeypatch.setattr(
        doctor.metadata,
        "requires",
        lambda name: ['yt-dlp-ejs==0.8.0; extra == "default"'],
    )

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return subprocess.CompletedProcess(
            argv, 0, "deno 2.3.0" if argv[0] == "deno" else "1.0.4", ""
        )

    monkeypatch.setattr(doctor.subprocess, "run", run)
    report = doctor.run_doctor()
    assert report.healthy
    assert len(calls) == 2
    assert "--offline" in calls[1][0] and "--no-extensions" in calls[1][0]
    assert all(call[1]["timeout"] == 5 for call in calls)
    calls.clear()
    assert doctor.run_doctor(include_pi=False).healthy
    assert len(calls) == 1 and calls[0][0][0] == "deno"


def test_user_selected_python_baseline(monkeypatch):
    version = namedtuple("Version", "major minor micro")
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)
    monkeypatch.setattr(doctor.metadata, "version", lambda name: "0.8.0")
    monkeypatch.setattr(doctor.metadata, "requires", lambda name: [])
    for micro, expected in [(6, "error"), (7, "ok")]:
        monkeypatch.setattr(
            doctor, "sys", SimpleNamespace(version_info=version(3, 14, micro))
        )
        report = doctor.run_doctor(include_pi=False)
        assert report.checks[0].name == "Python"
        assert report.checks[0].status == expected


def test_multiple_failures(monkeypatch):
    monkeypatch.setattr(doctor.shutil, "which", lambda name: None)

    def missing(name):
        raise doctor.metadata.PackageNotFoundError(name)

    monkeypatch.setattr(doctor.metadata, "version", missing)
    monkeypatch.setattr(doctor.metadata, "requires", missing)
    report = doctor.run_doctor()
    assert not report.healthy
    assert sum(check.status == "error" for check in report.checks) >= 5
    assert "overall: error" in doctor.render_doctor(report)
