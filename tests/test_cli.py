import json

from app.cli import _load_game_identifiers_from_input, _merge_identifier_inputs


def test_load_game_identifiers_from_input_reads_jsonl_stage_rows(tmp_path):
    path = tmp_path / "stage.jsonl"
    path.write_text(
        "\n".join(
            [
                json.dumps({"public_id": "alpha-public-id", "title": "Alpha"}),
                json.dumps({"anchor_public_id": "beta-anchor-id"}),
                json.dumps("gamma-direct-id"),
            ]
        ),
        encoding="utf-8",
    )

    identifiers = _load_game_identifiers_from_input(str(path))

    assert identifiers == ["alpha-public-id", "beta-anchor-id", "gamma-direct-id"]


def test_load_game_identifiers_from_input_reads_plaintext(tmp_path):
    path = tmp_path / "games.txt"
    path.write_text(
        "# comment\nalpha-public-id\n\nbeta-public-id\n",
        encoding="utf-8",
    )

    identifiers = _load_game_identifiers_from_input(str(path))

    assert identifiers == ["alpha-public-id", "beta-public-id"]


def test_merge_identifier_inputs_dedupes_casefolded_values():
    merged = _merge_identifier_inputs(
        ["Alpha", "beta"],
        ["alpha", "Gamma"],
    )

    assert merged == ["Alpha", "beta", "Gamma"]
