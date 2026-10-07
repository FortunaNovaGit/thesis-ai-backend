import pytest
from pydantic import BaseModel

from app.agents.runtime import _extract_json_value, _validate_agent_json


class Demo(BaseModel):
    name: str
    count: int


def test_extract_plain_json():
    assert _extract_json_value('{"name":"x","count":2}') == {"name": "x", "count": 2}


def test_extract_fenced_json():
    text = '```json\n{"name":"x","count":2}\n```'
    assert _validate_agent_json(text, Demo) == Demo(name="x", count=2)


def test_extract_prefixed_json():
    text = 'Here is the requested object:\n{"name":"x","count":2}'
    assert _validate_agent_json(text, Demo).count == 2


def test_invalid_json_raises():
    with pytest.raises(ValueError):
        _extract_json_value('not json')
