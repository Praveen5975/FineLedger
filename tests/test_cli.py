import json

from fineledger.cli import main


def test_verify_passes_intact_fails_tampered_and_rejects_missing_or_empty(scenario, tmp_path, capsys):
    path = scenario.path
    assert main(["verify", path]) == 0
    lines = open(path, encoding="utf-8").read().splitlines()
    rec = json.loads(lines[5])
    rec["data"]["gross_mg"] = rec["data"].get("gross_mg", 0) + 1 if "gross_mg" in rec["data"] else None
    rec["data"]["tamper"] = 1
    lines[5] = json.dumps(rec)
    bad = tmp_path / "bad.jsonl"
    bad.write_text("\n".join(lines) + "\n")
    assert main(["verify", str(bad)]) == 1
    assert main(["verify", str(tmp_path / "missing.jsonl")]) == 2  # a missing file must NEVER read as OK
    empty = tmp_path / "empty.jsonl"
    empty.write_text("")
    assert main(["verify", str(empty)]) == 2
