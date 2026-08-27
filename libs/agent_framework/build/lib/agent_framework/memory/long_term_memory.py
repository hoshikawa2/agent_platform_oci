from __future__ import annotations
import logging
from .long_term_extractor import extract_long_term_memory
from .long_term_store import create_long_term_memory_store

logger = logging.getLogger('agent_framework.memory.long_term')

class LongTermMemoryManager:
    def __init__(self, settings, store=None, telemetry=None):
        self.settings = settings
        self.store = store or create_long_term_memory_store(settings)
        self.telemetry = telemetry

    @property
    def enabled(self):
        return bool(getattr(self.settings, 'ENABLE_LONG_TERM_MEMORY', False))

    def identity(self, state):
        context = state.get('context') or {}
        session = context.get('session') or {}
        business = context.get('business_context') or state.get('business_context') or {}
        metadata = session.get('metadata') or {}
        tenant = str(state.get('tenant_id') or session.get('tenant_id') or 'default')
        agent = str(state.get('agent_id') or state.get('route') or session.get('active_agent') or 'default')
        subject = business.get('customer_key') or state.get('customer_key') or context.get('user_id') or session.get('user_id') or metadata.get('customer_key')
        return tenant, agent, str(subject) if subject else None

    async def load(self, state):
        if not self.enabled:
            return []
        tenant, agent, subject = self.identity(state)
        if not subject:
            return []
        try:
            return await self.store.search(tenant_id=tenant, agent_id=agent, subject_key=subject, limit=int(getattr(self.settings, 'LONG_TERM_MEMORY_MAX_CONTEXT_ITEMS', 20)))
        except Exception:
            logger.exception('Falha não crítica ao carregar LTM')
            return []

    async def persist_turn(self, state):
        if not self.enabled or not bool(getattr(self.settings, 'LONG_TERM_MEMORY_AUTO_EXTRACT', True)):
            return {'saved': 0, 'enabled': self.enabled}
        tenant, agent, subject = self.identity(state)
        if not subject:
            return {'saved': 0, 'warning': 'customer_key ausente'}
        text = str(state.get('sanitized_input') or state.get('user_text') or '')
        candidates = extract_long_term_memory(text, float(getattr(self.settings, 'LONG_TERM_MEMORY_MIN_CONFIDENCE', 0.70)))
        try:
            saved = await self.store.upsert_many(tenant_id=tenant, agent_id=agent, subject_key=subject, items=candidates, source_session_id=str(state.get('conversation_key') or state.get('session_id') or ''), source_message_id=str((state.get('context') or {}).get('message_id') or ''))
            return {'saved': len(saved), 'items': [item.to_dict() for item in saved]}
        except Exception as exc:
            logger.exception('Falha não crítica ao persistir LTM')
            return {'saved': 0, 'error': str(exc)}

    def render(self, items):
        if not items:
            return ''
        lines = ['Memórias duráveis relevantes do usuário atual:']
        lines.extend(f'- {item.key}: {item.value}' for item in items)
        lines.extend(['Use somente estas memórias; não invente lembranças.', 'A mensagem atual prevalece se houver conflito.'])
        return '\n'.join(lines)

def create_long_term_memory_manager(settings, telemetry=None):
    return LongTermMemoryManager(settings, telemetry=telemetry)
