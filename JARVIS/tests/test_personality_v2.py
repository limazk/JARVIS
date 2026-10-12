import json

from personality.engine import PersonalityEngine


def test_traits_change_the_actual_prompt(tmp_path):
    path = tmp_path / "personality.json"
    path.write_text(json.dumps({
        "personality": {"humor": 0.0, "sarcasm": 0.9, "empathy": 0.1}
    }), encoding="utf-8")
    prompt = PersonalityEngine(path, current_mode="STUDY").system_prompt()
    assert "Evite piadas desnecessárias" in prompt
    assert "Sarcasmo discreto" in prompt
    assert "Ensine com exemplos" in prompt


def test_trait_values_are_clamped_and_modes_active(tmp_path):
    path = tmp_path / "personality.json"
    path.write_text('{"personality":{"initiative":9,"verbosity":-3}}', encoding="utf-8")
    engine = PersonalityEngine(path, current_mode="FOCUS")
    assert engine.config["personality"]["initiative"] == 1
    assert engine.config["personality"]["verbosity"] == 0
    assert "próxima ação por vez" in engine.system_prompt()
    engine.set_mode("PROGRAMMING")
    assert "comandos verificáveis" in engine.system_prompt()


def test_invalid_config_falls_back(tmp_path):
    path = tmp_path / "personality.json"
    path.write_text("[]", encoding="utf-8")
    assert PersonalityEngine(path).config["identity"]["name"] == "JARVIS"
