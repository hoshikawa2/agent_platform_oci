from __future__ import annotations

# Compatibilidade sem quebrar imports existentes: o Supervisor antigo permanece
# em supervisor.py. Este alias documenta o papel correto dele na arquitetura.
from .supervisor import Supervisor as RouterSupervisor, SupervisorPlan

__all__ = ["RouterSupervisor", "SupervisorPlan"]
