"""Provider-selection gating: no implicit default LLM provider."""

import sys
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parents[1]))

import src.host.app as main
from src.host.app import (
    is_provider_selected,
    llm_config_snapshot,
    resolve_llm_provider,
)


def _reset_config(monkeypatch):
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LLM_API_BASE", raising=False)
    monkeypatch.setattr(main, "_LLM_CONFIG_OVERRIDE", {})
    monkeypatch.setattr(main, "_models_cache", None)


def test_no_provider_selected_without_explicit_choice(monkeypatch):
    _reset_config(monkeypatch)
    assert resolve_llm_provider() is None
    assert is_provider_selected() is False
    snapshot = llm_config_snapshot()
    assert snapshot["provider"] is None
    assert snapshot["configured"] is False


def test_env_base_alone_does_not_select_provider(monkeypatch):
    _reset_config(monkeypatch)
    monkeypatch.setenv("LLM_API_BASE", "http://localhost:11434")
    assert resolve_llm_provider() is None
    assert is_provider_selected() is False
    assert llm_config_snapshot()["configured"] is False


def test_env_provider_preselects(monkeypatch):
    _reset_config(monkeypatch)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_API_BASE", "http://localhost:11434")
    assert resolve_llm_provider() == "ollama"
    assert is_provider_selected() is True
    snapshot = llm_config_snapshot()
    assert snapshot["provider"] == "ollama"
    assert snapshot["configured"] is True


def test_settings_override_selects_provider(monkeypatch):
    _reset_config(monkeypatch)
    main._LLM_CONFIG_OVERRIDE["provider"] = "lmstudio"
    main._LLM_CONFIG_OVERRIDE["baseUrl"] = "http://localhost:1234"
    assert resolve_llm_provider() == "lmstudio"
    snapshot = llm_config_snapshot()
    assert snapshot["provider"] == "lmstudio"
    assert snapshot["baseUrl"] == "http://localhost:1234"
    assert snapshot["configured"] is True
