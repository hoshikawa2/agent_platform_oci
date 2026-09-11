from types import SimpleNamespace
from contextlib import contextmanager

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
        KBDB_IDENTIFY_DOCUMENT=True, KBDB_STORE_QUERY=True, KBDB_IDENTIFY_TOP_N=3,
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


def test_kbdb_discovers_number_flags_and_clob_output(monkeypatch):
    import sys
    from agent_framework.rag.kbdb_service import KbdbRagService

    captured = {}

    class Var:
        def __init__(self, value=None):
            self.value = value

        def getvalue(self):
            return self.value

    class Cursor:
        def execute(self, statement):
            captured["signature_query"] = statement

        def fetchall(self):
            names = [
                ("P_SEARCH_TYPE", "VARCHAR2"), ("P_QUERY", "VARCHAR2"),
                ("P_TOP_K", "NUMBER"), ("P_NODE_EXPANSION", "NUMBER"),
                ("P_NODE_MAX_RELATED", "NUMBER"), ("P_DOCUMENT_TYPE", "VARCHAR2"),
                ("P_METADATA", "CLOB"), ("P_IDENTIFY_DOCUMENT", "NUMBER"),
                ("P_STORE_QUERY", "NUMBER"), ("P_IDENTIFY_TOP_N", "NUMBER"),
                ("P_RESULT", "CLOB"),
            ]
            return [
                (name, index, "OUT" if index == 11 else "IN", data_type, None)
                for index, (name, data_type) in enumerate(names, start=1)
            ]

        def var(self, data_type, size=None):
            captured["out_type"] = data_type
            return Var('{"units": [], "seeds": []}')

        def callproc(self, name, binds):
            captured["procedure"] = name
            captured["binds"] = binds

    class Connection:
        def cursor(self):
            return Cursor()

    class FakeOracleDb:
        DB_TYPE_JSON = "JSON"
        DB_TYPE_CLOB = "CLOB"
        DB_TYPE_VARCHAR = "VARCHAR"

    service = KbdbRagService(_settings())

    @contextmanager
    def connect():
        yield Connection()

    monkeypatch.setitem(sys.modules, "oracledb", FakeOracleDb)
    monkeypatch.setattr(service, "_connect", connect)

    result = service._search_sync("como funciona?", 5)

    assert result == {"units": [], "seeds": []}
    assert captured["procedure"] == "PKG_KB_SERVING.search_knowledge_base"
    assert captured["binds"][3] == 1
    assert captured["binds"][7:10] == [1, 1, 3]
    assert captured["out_type"] == "CLOB"
