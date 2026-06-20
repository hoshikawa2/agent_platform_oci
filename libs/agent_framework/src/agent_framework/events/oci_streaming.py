import json, base64, logging
logger=logging.getLogger('agent_framework.streaming')

class EventPublisher:
    async def publish(self, event_type: str, payload: dict): ...

class NoopEventPublisher(EventPublisher):
    async def publish(self, event_type, payload):
        logger.info('event.noop %s %s', event_type, payload)

class OCIStreamingPublisher(EventPublisher):
    def __init__(self, settings):
        import oci
        config = oci.config.from_file(settings.OCI_CONFIG_FILE, settings.OCI_PROFILE)
        self.client = oci.streaming.StreamClient(config, service_endpoint=settings.OCI_STREAM_ENDPOINT)
        self.stream_id = settings.OCI_STREAM_OCID
        self.partition_key = settings.OCI_STREAM_PARTITION_KEY
    async def publish(self, event_type, payload):
        import oci
        body = json.dumps({'type': event_type, 'payload': payload}, default=str).encode()
        entry = oci.streaming.models.PutMessagesDetailsEntry(key=self.partition_key.encode(), value=body)
        details = oci.streaming.models.PutMessagesDetails(messages=[entry])
        self.client.put_messages(self.stream_id, details)

def create_event_publisher(settings):
    if settings.ENABLE_OCI_STREAMING and settings.OCI_STREAM_ENDPOINT and settings.OCI_STREAM_OCID:
        return OCIStreamingPublisher(settings)
    return NoopEventPublisher()
