### Long-Term Memory on Oracle Autonomous Database

### Activation

```env
ENABLE_LONG_TERM_MEMORY=true
LONG_TERM_MEMORY_PROVIDER=autonomous

ADB_USER=ADMIN
ADB_PASSWORD=<password>
ADB_DSN=<autonomous_service_name>
ADB_WALLET_LOCATION=/path/to/wallet
ADB_WALLET_PASSWORD=<wallet_password_if_applicable>
ADB_TABLE_PREFIX=AGENTFW

# Optional. Default: ${ADB_TABLE_PREFIX}_LONG_TERM_MEMORY.
LONG_TERM_MEMORY_ORACLE_TABLE=AGENTFW_LONG_TERM_MEMORY
```

`LONG_TERM_MEMORY_PROVIDER=oracle` is also accepted.

### Dependency

```bash
pip install oracledb
```

### Schema initialization

On the first operation, the provider automatically creates the table and index. The user configured in `ADB_USER` needs permission to create tables and indexes. If a DBA provisions the schema beforehand, initialization accepts the existing objects.

### Identity and isolation

The logical key consists of:

```text
tenant_id + agent_id + subject_key + category + memory_key
```

In the current integration, `subject_key` is derived from `customer_key`.

### Test

1. Start the backend with the `autonomous` provider.
2. Store facts in session A.
3. Open session B with the same `customer_key`.
4. Verify retrieval.
5. Restart the backend and repeat the query.
6. Query `AGENTFW_LONG_TERM_MEMORY` in Autonomous Database.

```sql
SELECT TENANT_ID, AGENT_ID, SUBJECT_KEY, CATEGORY, MEMORY_KEY,
       MEMORY_VALUE, CONFIDENCE, UPDATED_AT
FROM AGENTFW_LONG_TERM_MEMORY
ORDER BY UPDATED_AT DESC;
```

### Notes

- The provider uses `python-oracledb` in thin mode.
- Synchronous operations run through `asyncio.to_thread`.
- A wallet is optional when walletless TLS is configured.
- SQLite and InMemory remain available for development and testing.
