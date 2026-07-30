from types import SimpleNamespace

from agent_framework.memory.long_term_store import (
    InMemoryLongTermMemoryStore,
    OracleAutonomousLongTermMemoryStore,
    SQLiteLongTermMemoryStore,
    create_long_term_memory_store,
)


def settings(provider: str):
    return SimpleNamespace(
        LONG_TERM_MEMORY_PROVIDER=provider,
        LONG_TERM_MEMORY_SQLITE_PATH=":memory:",
        LONG_TERM_MEMORY_TABLE="agentfw_long_term_memory",
        LONG_TERM_MEMORY_ORACLE_TABLE=None,
        ADB_USER="user",
        ADB_PASSWORD="password",
        ADB_DSN="service_high",
        ADB_WALLET_LOCATION=None,
        ADB_WALLET_PASSWORD=None,
        ADB_TABLE_PREFIX="AGENTFW",
    )


def test_factory_memory():
    assert isinstance(create_long_term_memory_store(settings("memory")), InMemoryLongTermMemoryStore)


def test_factory_sqlite():
    assert isinstance(create_long_term_memory_store(settings("sqlite")), SQLiteLongTermMemoryStore)


def test_factory_autonomous():
    store = create_long_term_memory_store(settings("autonomous"))
    assert isinstance(store, OracleAutonomousLongTermMemoryStore)
    assert store.table == "AGENTFW_LONG_TERM_MEMORY"


def test_factory_oracle_alias():
    assert isinstance(
        create_long_term_memory_store(settings("oracle")),
        OracleAutonomousLongTermMemoryStore,
    )
