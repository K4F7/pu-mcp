from pathlib import Path


def test_all_fixtures_are_valid_json(fixture_json):
    fixture_dir = Path(__file__).parent / "fixtures"
    for path in fixture_dir.glob("*.json"):
        assert fixture_json(path.name)["msg"]
