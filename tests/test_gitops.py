"""Tests für ``core.gitops`` — clone/pull/status/dirty gegen ein tmp-git-repo.

Läuft tkinter-frei und ohne Netzwerk: clone-Quelle ist ein lokales bare Repo
unter ``tmp_path``. Die Geschwister-Pfade werden über ``paths.launcher_root``
auf ein Umbrella unter ``tmp_path`` gebogen — echte Isolation.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from core import gitops, paths


def _git(args: list[str], cwd: Path) -> None:
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True
    )


def _make_remote(tmp_path: Path) -> Path:
    """Legt ein bare Repo mit einem Commit an; liefert seinen Pfad."""
    remote = tmp_path / "remote.git"
    _git(["init", "--bare", "-b", "main", str(remote)], tmp_path)

    work = tmp_path / "remote-work"
    work.mkdir()
    _git(["init", "-b", "main", str(work)], work)
    _git(["config", "user.email", "t@t.test"], work)
    _git(["config", "user.name", "Test"], work)
    (work / "README.md").write_text("# test\n", encoding="utf-8")
    _git(["add", "."], work)
    _git(["commit", "-m", "init"], work)
    _git(["remote", "add", "origin", str(remote)], work)
    _git(["push", "origin", "main"], work)
    return remote


@pytest.fixture
def umbrella(tmp_path: Path, monkeypatch) -> Path:
    """Umbrella-Layout: ``tmp_path/sba-launcher`` → siblings via ``../<name>``."""
    launcher = tmp_path / "sba-launcher"
    launcher.mkdir()
    monkeypatch.setattr(paths, "launcher_root", lambda: launcher)
    return tmp_path


# --- status / is_dirty ----------------------------------------------------

def test_status_nicht_installiert(umbrella: Path) -> None:
    st = gitops.status("ausleihe-ausgabe")
    assert not st.installed
    assert not st.dirty
    assert st.branch is None
    assert st.error is None


def test_is_dirty_false_wenn_nicht_installiert(umbrella: Path) -> None:
    assert gitops.is_dirty("ausleihe-ausgabe") is False


# --- clone ----------------------------------------------------------------

def test_clone_installiert_repo(umbrella: Path, tmp_path: Path) -> None:
    remote = _make_remote(tmp_path)
    target = gitops.clone("ausleihe-ausgabe", url=str(remote))
    assert paths.exists("ausleihe-ausgabe")
    assert (target / "README.md").is_file()
    st = gitops.status("ausleihe-ausgabe")
    assert st.installed
    assert st.branch == "main"
    assert not st.dirty
    assert st.error is None


def test_clone_lehnt_ab_wenn_ziel_nicht_leer(umbrella: Path, tmp_path: Path) -> None:
    remote = _make_remote(tmp_path)
    repo = paths.sibling("ausleihe-ausgabe")
    repo.mkdir(parents=True)
    (repo / "etwas").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        gitops.clone("ausleihe-ausgabe", url=str(remote))


def test_clone_default_url_aus_repo_urls(umbrella: Path, monkeypatch) -> None:
    """clone() defaultet auf REPO_URLS — hier durch eine Fake-URL umgelenkt."""
    remote = _make_remote(umbrella)
    # Default-URL auf das lokale bare umlenken, damit kein Netzwerk nötig.
    monkeypatch.setitem(gitops.REPO_URLS, "ausleihe-ausgabe", str(remote))
    gitops.clone("ausleihe-ausgabe")
    assert paths.exists("ausleihe-ausgabe")


# --- dirty-Erkennung ------------------------------------------------------

def test_is_dirty_true_nach_aenderung(umbrella: Path, tmp_path: Path) -> None:
    remote = _make_remote(tmp_path)
    gitops.clone("ausleihe-ausgabe", url=str(remote))
    assert gitops.is_dirty("ausleihe-ausgabe") is False
    (paths.sibling("ausleihe-ausgabe") / "README.md").write_text(
        "# geändert\n", encoding="utf-8"
    )
    assert gitops.is_dirty("ausleihe-ausgabe") is True


# --- pull -----------------------------------------------------------------

def test_pull_up_to_date(umbrella: Path, tmp_path: Path) -> None:
    remote = _make_remote(tmp_path)
    gitops.clone("ausleihe-ausgabe", url=str(remote))
    gitops.pull("ausleihe-ausgabe")
    # --ff-only auf aktuellem Stand → keine Änderung, Repo bleibt clean.
    assert gitops.is_dirty("ausleihe-ausgabe") is False


def test_pull_hebt_wenn_nicht_installiert(umbrella: Path) -> None:
    with pytest.raises(FileNotFoundError):
        gitops.pull("ausleihe-ausgabe")


def test_pull_holt_neuen_commit(umbrella: Path, tmp_path: Path) -> None:
    remote = _make_remote(tmp_path)
    gitops.clone("ausleihe-ausgabe", url=str(remote))

    # Neuen Commit ins Remote pushen (über das work-Repo).
    work = tmp_path / "remote-work"
    (work / "neu.txt").write_text("neu\n", encoding="utf-8")
    _git(["add", "."], work)
    _git(["commit", "-m", "zwei"], work)
    _git(["push", "origin", "main"], work)

    gitops.pull("ausleihe-ausgabe")
    geholt = (paths.sibling("ausleihe-ausgabe") / "neu.txt").read_text(encoding="utf-8")
    assert geholt.strip() == "neu"


# --- current_branch / REPO_URLS -------------------------------------------

def test_current_branch_nicht_installiert_ist_none(umbrella: Path) -> None:
    assert gitops.current_branch("ausleihe-ausgabe") is None


def test_current_branch_main_nach_clone(umbrella: Path, tmp_path: Path) -> None:
    remote = _make_remote(tmp_path)
    gitops.clone("ausleihe-ausgabe", url=str(remote))
    assert gitops.current_branch("ausleihe-ausgabe") == "main"


def test_repo_urls_abgedeckt_und_https() -> None:
    for name in paths.SIBLING_REPOS:
        assert name in gitops.REPO_URLS
        assert gitops.REPO_URLS[name].startswith("https://github.com/")


# --- clone-Fehler / broken .git -------------------------------------------


def test_clone_fehlschlag_hebt_und_räumt_auf(umbrella: Path, tmp_path: Path) -> None:
    # Ungültige URL → clone scheitert → RuntimeError + Ziel aufgeräumt.
    with pytest.raises(RuntimeError, match="clone fehlgeschlagen"):
        gitops.clone("ausleihe-ausgabe", url=str(tmp_path / "nicht-vorhanden.git"))
    assert not paths.sibling("ausleihe-ausgabe").exists()


def test_status_broken_git_liefert_error(umbrella: Path) -> None:
    # Repo-Verzeichnis mit .git, aber kein gültiges Git-Repo → error gesetzt.
    repo = paths.sibling("ausleihe-ausgabe")
    (repo / ".git").mkdir(parents=True)
    st = gitops.status("ausleihe-ausgabe")
    assert st.installed
    assert st.error is not None
