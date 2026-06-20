from __future__ import annotations
from datetime import datetime
from evaluator.collectors.base import ConversationCollector
from evaluator.core.models import ConversationRecord, ConversationMessage

class MockCollector(ConversationCollector):
    async def collect(self, period_start: datetime, period_end: datetime, agent_aliases: set[str] | None=None, limit: int | None=None):
        agent = next(iter(agent_aliases), 'telecom_contas') if agent_aliases else 'telecom_contas'
        return [ConversationRecord(trace_id='mock-trace-1', session_id='mock-session-1', message_id='mock-message-1', agent_id=agent, channel='web', input_text='quero minha fatura', output_text='Sua fatura está em aberto no valor de R$ 120.', messages=[ConversationMessage(role='user', content='quero minha fatura'), ConversationMessage(role='assistant', content='Sua fatura está em aberto no valor de R$ 120.')], metadata={'mock': True})]
