from types import SimpleNamespace

import pytest

from agent_framework.rag.rag_service import RagService


def _settings(**overrides):
    data = dict(
        RAG_PROVIDER="kbdb", RAG_TOP_K=5,
        KBDB_DB_USER="kb_user", KBDB_DB_PASSWORD="kb_pwd", KBDB_DB_DSN="kb_tp",
        KBDB_DB_WALLET_LOCATION=None, KBDB_DB_WALLET_PASSWORD=None,
        ADB_USER=None, ADB_PASSWORD=None, ADB_DSN=None,
        ADB_WALLET_LOCATION=None, ADB_WALLET_PASSWORD=None,
        KBDB_SEARCH_TYPE="hybrid", KBDB_NODE_EXPANSION=True,
        KBDB_NODE_MAX_RELATED=8, KBDB_GRAPH_CROSS_REF=False,
        KBDB_MAX_CROSS_REF_HOPS=1, KBDB_DOCUMENT_TYPE="customer_safe",
        KBDB_METADATA_JSON=None, KBDB_MIN_SCORE=None,
    )
    data.update(overrides)
    return SimpleNamespace(**data)


@pytest.mark.asyncio
async def test_kbdb_provider_adapts_serving_envelope(monkeypatch):
    service = RagService(_settings())

    def fake_search(query, k):
        return {
            "search_type": "hybrid", "confidence": "high", "low_confidence": False,
            "top_score": 78.4, "warnings": [],
            "seeds": [{"unit_id": 11, "rank": 1, "score": 78.4}],
            "units": [
                {"unit_id": 10, "content": "passo anterior", "provenance": "parent"},
                {"unit_id": 11, "content": "resposta principal", "provenance": "seed"},
            ],
            "documents": [{"document_id": 7, "title": "Politica"}],
        }

    monkeypatch.setattr(service._kbdb, "_search_sync", fake_search)
    result = await service.retrieve("qual a regra?", namespace="billing_agent")

    assert [d.id for d in result.documents] == ["10", "11"]
    assert result.documents[1].score == 78.4
    assert result.metadata["provider"] == "kbdb"
    assert result.metadata["confidence"] == "high"
    assert "resposta principal" in result.as_prompt_context()


@pytest.mark.asyncio
async def test_kbdb_provider_is_serving_only():
    service = RagService(_settings())
    with pytest.raises(RuntimeError, match="serving-only"):
        await service.add_documents(["texto"])


def test_kbdb_connection_uses_same_wallet_semantics_without_adb_fallback(monkeypatch):
    import sys
    from agent_framework.rag.kbdb_service import KbdbRagService

    captured = {}

    class Defaults:
        fetch_lobs = True

    class Connection:
        def close(self):
            captured["closed"] = True

    class FakeOracleDb:
        defaults = Defaults()

        @staticmethod
        def connect(**kwargs):
            captured.update(kwargs)
            return Connection()

    monkeypatch.setitem(sys.modules, "oracledb", FakeOracleDb)
    settings = _settings(
        KBDB_DB_USER="kb_user",
        KBDB_DB_PASSWORD="kb_pwd",
        KBDB_DB_DSN="kb_tp",
        KBDB_DB_WALLET_LOCATION="/wallet/kb",
        KBDB_DB_WALLET_PASSWORD="wallet_pwd",
        ADB_USER="framework_user",
        ADB_PASSWORD="framework_pwd",
        ADB_DSN="framework_high",
        ADB_WALLET_LOCATION="/wallet/framework",
        ADB_WALLET_PASSWORD="framework_wallet_pwd",
    )

    service = KbdbRagService(settings)
    with service._connect():
        pass

    assert captured["user"] == "kb_user"
    assert captured["password"] == "kb_pwd"
    assert captured["dsn"] == "kb_tp"
    assert captured["config_dir"] == "/wallet/kb"
    assert captured["wallet_location"] == "/wallet/kb"
    assert captured["wallet_password"] == "wallet_pwd"
    assert captured["closed"] is True


def test_kbdb_does_not_fallback_to_framework_adb_credentials():
    from agent_framework.rag.kbdb_service import KbdbRagService

    settings = _settings(
        KBDB_DB_USER=None,
        KBDB_DB_PASSWORD=None,
        KBDB_DB_DSN=None,
        ADB_USER="framework_user",
        ADB_PASSWORD="framework_pwd",
        ADB_DSN="framework_high",
    )
    with pytest.raises(RuntimeError, match="KBDB_DB_USER"):
        KbdbRagService(settings)
