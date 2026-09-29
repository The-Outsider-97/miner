from pathlib import Path

from utils.config_loader import get_config_section, load_config

ROOT=Path(__file__).resolve().parents[1]


def test_config_is_sn67_and_pinned():
    config=load_config(); assert get_config_section("project",config=config)["netuid"]==67
    external=get_config_section("external",config=config); assert len(external["slai"]["expected_commit"])==40; assert len(external["harnyx"]["expected_commit"])==40; assert external["harnyx"]["sdk_version"]=="0.1.23"


def test_gitignore_covers_secrets_and_local_evidence():
    text=(ROOT/".gitignore").read_text(encoding="utf-8")
    for pattern in (".env","*.pem","*.key",".bittensor/","*.sqlite3","benchmarks/harnyx/results/"): assert pattern in text
