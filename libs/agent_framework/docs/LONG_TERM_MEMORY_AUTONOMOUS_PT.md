### Long-Term Memory no Oracle Autonomous Database

### Ativação

```env
ENABLE_LONG_TERM_MEMORY=true
LONG_TERM_MEMORY_PROVIDER=autonomous

ADB_USER=ADMIN
ADB_PASSWORD=<senha>
ADB_DSN=<service_name_do_autonomous>
ADB_WALLET_LOCATION=/caminho/para/wallet
ADB_WALLET_PASSWORD=<senha_wallet_se_aplicavel>
ADB_TABLE_PREFIX=AGENTFW

# Opcional. O padrão é ${ADB_TABLE_PREFIX}_LONG_TERM_MEMORY.
LONG_TERM_MEMORY_ORACLE_TABLE=AGENTFW_LONG_TERM_MEMORY
```

Também é aceito `LONG_TERM_MEMORY_PROVIDER=oracle`.

### Dependência

```bash
pip install oracledb
```

### Inicialização do schema

Na primeira operação, o provider cria automaticamente a tabela e o índice. O usuário configurado em `ADB_USER` precisa de permissão para criar tabela e índice. Se o schema for provisionado previamente por DBA, a inicialização reconhece os objetos existentes.

### Identidade e isolamento

A chave lógica é composta por:

```text
tenant_id + agent_id + subject_key + category + memory_key
```

Na integração atual, `subject_key` é derivado do `customer_key`.

### Teste

1. Inicie o backend com provider `autonomous`.
2. Grave fatos na sessão A.
3. Abra a sessão B com o mesmo `customer_key`.
4. Confirme a recuperação.
5. Reinicie o backend e repita a consulta.
6. Consulte a tabela `AGENTFW_LONG_TERM_MEMORY` no Autonomous Database.

```sql
SELECT TENANT_ID, AGENT_ID, SUBJECT_KEY, CATEGORY, MEMORY_KEY,
       MEMORY_VALUE, CONFIDENCE, UPDATED_AT
FROM AGENTFW_LONG_TERM_MEMORY
ORDER BY UPDATED_AT DESC;
```

### Observações

- O provider usa `python-oracledb` em thin mode.
- As operações síncronas são executadas com `asyncio.to_thread`.
- Wallet é opcional quando a conexão TLS sem wallet estiver configurada.
- SQLite e InMemory continuam disponíveis para desenvolvimento e testes.
