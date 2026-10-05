import json

from personality.engine import PersonalityEngine


def test_personality_config_loads(tmp_path):
    path = tmp_path / "personality.json"
    path.write_text(json.dumps({"identity": {"name": "TESTE", "language": "pt-BR"}}), encoding="utf-8")
    engine = PersonalityEngine(path)
    assert engine.config["identity"]["name"] == "TESTE"


def test_system_prompt_incorporates_identity():
    prompt = PersonalityEngine().system_prompt()
    assert "JARVIS" in prompt and "pt-BR" in prompt


def test_voice_response_stays_concise():
    prompt = PersonalityEngine().system_prompt(response_mode="voice")
    assert "curta e natural" in prompt
    assert "sem Markdown" in prompt
