from __future__ import annotations
from agent_framework.judges.judge import JudgeResult

class ExternalBusinessJudge:
    name = "external_business_quality"
    def __init__(self, threshold=0.5, **kwargs): self.threshold=float(threshold or 0.5)
    def evaluate(self, question, answer, context):
        score = 1.0 if answer and len(answer.strip()) >= 10 else 0.0
        return JudgeResult(name=self.name, score=score, passed=score >= self.threshold, reason="example external judge", metadata={"external": True})
