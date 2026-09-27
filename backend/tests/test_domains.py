"""Pluggable-domain registry + template domain (no servers spawned, no embedder)."""

import json

from src.domains.physics.tools.kinematics import kinetic_energy, projectile_motion
from src.host import domain_registry
from src.host.domain_registry import get_active_domain, list_domains
from src.host.mcp_pool import MultiMCPClient, ReliabilityMCPClient
from src.knowledge.base import GenericKnowledgeBase, ReliabilityKnowledgeBase


def test_default_domain_is_reliability(monkeypatch):
    monkeypatch.delenv("ACTIVE_DOMAIN", raising=False)
    monkeypatch.delenv("MCP_SERVERS_CONFIG", raising=False)
    domain = get_active_domain()
    assert domain.name == "reliability"
    assert domain.collection == "reliability_knowledge"
    assert "Reliability Copilot" in domain.system_prompt
    assert domain.servers_config.exists()
    assert "reliability" in domain.server_module


def test_physics_domain_resolves(monkeypatch):
    monkeypatch.setenv("ACTIVE_DOMAIN", "physics")
    domain = get_active_domain()
    assert domain.name == "physics"
    assert domain.collection == "physics_knowledge"
    assert "Physics Copilot" in domain.system_prompt
    assert domain.servers_config.exists()
    payload = json.loads(domain.servers_config.read_text(encoding="utf-8"))
    assert "physics-engineering" in payload["mcpServers"]


def test_list_domains_finds_both_packs():
    assert {"reliability", "physics"} <= set(list_domains())


def test_physics_kinematics_numbers():
    flight = projectile_motion(10.0, 45.0)
    assert flight["range_m"] == abs(flight["range_m"])
    assert flight["flight_time_s"] > 0
    assert kinetic_energy(2.0, 3.0)["kinetic_energy_j"] == 9.0


def test_client_alias_and_placeholder_expansion():
    assert ReliabilityMCPClient is MultiMCPClient
    client = MultiMCPClient()
    assert "${PYTHON}" not in client._expand("${PYTHON}")
    assert "src" not in client._expand("${BACKEND_DIR}") or client._expand(
        "${BACKEND_DIR}"
    ).endswith("backend")


def test_knowledge_alias_hierarchy():
    assert issubclass(ReliabilityKnowledgeBase, GenericKnowledgeBase)
    assert domain_registry.DEFAULT_DOMAIN == "reliability"


def test_domain_static_dir_is_backend_static():
    from src.domains.reliability.tools._common import BACKEND_DIR, STATIC_DIR

    assert BACKEND_DIR.name == "backend"
    assert STATIC_DIR == BACKEND_DIR / "static"


def test_plot_image_block_missing_file_returns_none():
    from src.domains.reliability.server import _plot_image_block

    assert _plot_image_block("no_such_plot.png") is None
    assert _plot_image_block("") is None
    assert _plot_image_block("../main.py") is None


def test_analyze_weibull_embeds_plot_image():
    import base64

    from src.domains.reliability.server import _plot_image_block
    from src.domains.reliability.tools._common import STATIC_DIR
    from src.domains.reliability.tools.weibull import analyze_weibull

    result = analyze_weibull([150.0, 180.0, 220.0, 310.0])
    try:
        assert (STATIC_DIR / result["file"]).is_file()
        block = _plot_image_block(result["file"])
        assert block is not None
        assert getattr(block, "type", "") == "image"
        mime = getattr(block, "mimeType", None) or getattr(block, "mime_type", None)
        assert mime == "image/png"
        assert block.data.startswith("iVBOR")  # PNG magic, base64
        base64.b64decode(block.data)  # valid base64
    finally:
        try:
            (STATIC_DIR / result["file"]).unlink()
        except OSError:
            pass
