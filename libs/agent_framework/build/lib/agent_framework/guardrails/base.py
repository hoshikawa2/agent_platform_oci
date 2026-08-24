from pydantic import BaseModel, Field
from typing import Any

class RailDecision(BaseModel):
    code: str
    allowed: bool = True
    reason: str = ''
    sanitized_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class Guardrail:
    code = 'BASE'
    stage = 'input'
    async def evaluate(self, text: str, context: dict[str, Any]) -> RailDecision:
        return RailDecision(code=self.code, allowed=True)
