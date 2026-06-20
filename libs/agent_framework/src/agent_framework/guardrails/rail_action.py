from enum import Enum


class RailAction(str, Enum):
    ALLOW = "allow"
    SANITIZE = "sanitize"
    RETRY = "retry"
    BLOCK = "block"
    HANDOVER = "handover"
    OBSERVE = "observe"
