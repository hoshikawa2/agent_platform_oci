NOC_TRACE_STARTED = "NOC.001"
NOC_INVALID_API_RESPONSE = "NOC.002"
NOC_DATABASE_LATENCY = "NOC.003"
NOC_INCONSISTENT_LLM = "NOC.004"
NOC_FATAL_EXCEPTION = "NOC.005"
NOC_FLOW_LATENCY = "NOC.006"

BASE_NOC_FIELDS = [
    "uraCallId",
    "sessionId",
    "messageId",
    "transcriptionId",
    "gsm",
    "ani",
    "tag",
    "agentId",
    "channelId",
    "eventDate",
    "agentVersion",
]
