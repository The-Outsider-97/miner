import os
from pathlib import Path

import pytest

from artifact_builder import build_artifact


@pytest.mark.integration
@pytest.mark.skipif(os.environ.get("RUN_SLAI_INTEGRATION")!="1",reason="full SLAI dependency environment not requested")
def test_reasoning_agent_starts_via_factory_and_closes():
    from adapters.slai import SlaiRuntime
    with SlaiRuntime(["reasoning"]) as runtime:
        result=runtime.reason("If A implies B and A is true, what follows?")
        snapshot=runtime.snapshot()
    assert isinstance(result,dict)
    assert "reasoning" in snapshot["agents"]
    assert any(item["operation"]=="initialize" for item in snapshot["measurements"])


@pytest.mark.harnyx
@pytest.mark.skipif(os.environ.get("RUN_HARNYX_OFFICIAL")!="1",reason="official Harnyx uv workspace validation not requested")
def test_generated_baseline_passes_official_harnyx_loader(tmp_path: Path):
    result=build_artifact("b0",output_path=tmp_path/"agent.py",manifest_root=tmp_path/"manifests",official_validate=True)
    assert result.official_validation is True
