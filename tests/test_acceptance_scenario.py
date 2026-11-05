import json

import pytest

from shared.acceptance.scenario import load_scenario, turn_expectations


def test_changed_dataset_expectations(tmp_path):
    value = load_scenario()
    value['report_week'] = 202601
    value['turns'][0].update(prompt='Count reviews in week 202601.', week_id=202601)
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    loaded = load_scenario(path)
    expected = turn_expectations(loaded)
    assert expected[0].week_id == 202601
    assert expected[0].prompt == 'Count reviews in week 202601.'
    assert expected[1].require_citation


@pytest.mark.parametrize('patch', [
    {'schema_version': 2}, {'report_week': 202153}, {'report_week': True},
    {'turns': []}, {'citation_text': ' '},
])
def test_invalid_scenario(tmp_path, patch):
    value = {**load_scenario(), **patch}
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError):
        load_scenario(path)


@pytest.mark.parametrize('patch', [
    {'tools': ['unknown']}, {'tools': [['tool_sql']]}, {'tools': ['tool_sql', 'tool_sql']},
    {'week_id': 202600}, {'prompt': ''}, {'status': 'abstained', 'require_citation': True},
])
def test_invalid_turn(tmp_path, patch):
    value = load_scenario()
    value['turns'][0].update(patch)
    path = tmp_path / 'scenario.json'
    path.write_text(json.dumps(value), encoding='utf-8')
    with pytest.raises(ValueError):
        load_scenario(path)
