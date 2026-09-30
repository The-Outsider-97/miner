from utils.repository_state import benchmark_database_path, dependency_status


def test_configured_dependency_revisions_match_checked_out_submodules():
    status = dependency_status()
    assert status["slai"]["revision_matches"] is True
    assert status["harnyx"]["revision_matches"] is True
    assert status["slai"]["actual_commit"] == status["slai"]["expected_commit"]
    assert status["harnyx"]["actual_commit"] == status["harnyx"]["expected_commit"]


def test_benchmark_database_path_uses_project_configuration():
    path = benchmark_database_path()
    assert path.name == "miner_benchmarks.sqlite3"
    assert path.parts[-4:] == (
        "benchmarks",
        "harnyx",
        "results",
        "miner_benchmarks.sqlite3",
    )
