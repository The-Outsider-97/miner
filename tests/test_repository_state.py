from pathlib import Path

import miner.utils.repository_state as repository_state
from miner.utils.miner_errors import ExternalDependencyError
from miner.utils.repository_state import benchmark_database_path, dependency_status


def test_configured_dependency_revisions_match_checked_out_submodules():
    status = dependency_status()
    assert status["slai"]["revision_matches"] is True
    assert status["harnyx"]["revision_matches"] is True
    assert status["slai"]["revision_state"] == "matching"
    assert status["harnyx"]["revision_state"] == "matching"
    assert status["slai"]["actual_commit"] == status["slai"]["expected_commit"]
    assert status["harnyx"]["actual_commit"] == status["harnyx"]["expected_commit"]


def _config(*, slai_expected: str, harnyx_expected: str = "harnyx-pin") -> dict:
    return {
        "external": {
            "slai": {
                "path": "external/slai",
                "expected_commit": slai_expected,
            },
            "harnyx": {
                "path": "external/harnyx",
                "expected_commit": harnyx_expected,
            },
        }
    }


def _mock_dependency_git(
    monkeypatch,
    tmp_path: Path,
    *,
    slai_actual: str = "slai-pin",
    slai_clean: bool = True,
) -> None:
    monkeypatch.setattr(repository_state, "PROJECT_ROOT", tmp_path)

    roots = {
        "slai": tmp_path / "external" / "slai",
        "harnyx": tmp_path / "external" / "harnyx",
    }
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(
        repository_state,
        "require_external_repository",
        lambda name, sentinel: roots[name],
    )
    monkeypatch.setattr(
        repository_state,
        "git_head",
        lambda path: (
            slai_actual
            if path == roots["slai"]
            else "harnyx-pin"
            if path == roots["harnyx"]
            else "miner-head"
        ),
    )
    monkeypatch.setattr(
        repository_state,
        "git_is_clean",
        lambda path: slai_clean if path == roots["slai"] else True,
    )


def test_matching_revision_with_modified_worktree_remains_degraded(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _mock_dependency_git(
        monkeypatch,
        tmp_path,
        slai_actual="slai-pin",
        slai_clean=False,
    )

    status = dependency_status(_config(slai_expected="slai-pin"))

    assert status["slai"]["status"] == "degraded"
    assert status["slai"]["revision_state"] == "matching"
    assert status["slai"]["revision_matches"] is True
    assert status["slai"]["worktree_state"] == "modified"
    assert status["slai"]["pinned"] is False





def test_matching_clean_revision_is_ready(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _mock_dependency_git(
        monkeypatch,
        tmp_path,
        slai_actual="slai-pin",
        slai_clean=True,
    )

    status = dependency_status(_config(slai_expected="slai-pin"))

    assert status["slai"]["status"] == "ready"
    assert status["slai"]["revision_state"] == "matching"
    assert status["slai"]["worktree_state"] == "clean"
    assert status["slai"]["pinned"] is True


def test_actual_revision_mismatch_remains_degraded(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _mock_dependency_git(
        monkeypatch,
        tmp_path,
        slai_actual="different-revision",
        slai_clean=True,
    )

    status = dependency_status(_config(slai_expected="slai-pin"))

    assert status["slai"]["status"] == "degraded"
    assert status["slai"]["revision_state"] == "mismatch"
    assert status["slai"]["revision_matches"] is False
    assert status["slai"]["pinned"] is False


def test_missing_expected_revision_is_unresolved_not_mismatch(
    monkeypatch,
    tmp_path: Path,
) -> None:
    _mock_dependency_git(
        monkeypatch,
        tmp_path,
        slai_actual="slai-pin",
        slai_clean=True,
    )

    status = dependency_status(_config(slai_expected=""))

    assert status["slai"]["status"] == "degraded"
    assert status["slai"]["revision_state"] == "unresolved"
    assert status["slai"]["revision_matches"] is False
    assert status["slai"]["pinned"] is False


def test_unavailable_dependency_reports_unavailable_revision(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(repository_state, "PROJECT_ROOT", tmp_path)

    def unavailable(name: str, sentinel: str) -> Path:
        if name == "slai":
            raise ExternalDependencyError("SLAI source unavailable")
        root = tmp_path / "external" / name
        root.mkdir(parents=True, exist_ok=True)
        return root

    monkeypatch.setattr(repository_state, "require_external_repository", unavailable)
    monkeypatch.setattr(
        repository_state,
        "git_head",
        lambda path: "harnyx-pin" if path.name == "harnyx" else "miner-head",
    )
    monkeypatch.setattr(repository_state, "git_is_clean", lambda path: True)

    status = dependency_status(_config(slai_expected="slai-pin"))

    assert status["slai"]["status"] == "unavailable"
    assert status["slai"]["actual_commit"] is None
    assert status["slai"]["revision_state"] == "unavailable"
    assert status["slai"]["worktree_state"] == "unavailable"
    assert status["slai"]["pinned"] is False


def test_benchmark_database_path_uses_project_configuration():
    path = benchmark_database_path()
    assert path.name == "miner_benchmarks.sqlite3"
    assert path.parts[-4:] == (
        "benchmarks",
        "harnyx",
        "results",
        "miner_benchmarks.sqlite3",
    )
