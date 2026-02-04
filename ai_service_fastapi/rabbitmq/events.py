# rabbitmq/events.py - Event Type Definitions

from enum import Enum


class EventType(str, Enum):
    """RabbitMQ event types for the AI service"""
    
    # Incoming events (consumed by AI service)
    FREELANCER_REGISTERED = "freelancer.registered"
    FREELANCER_UPDATED = "freelancer.updated"
    FREELANCER_DELETED = "freelancer.deleted"
    JOB_POSTED = "job.posted"
    
    # Outgoing events (published by AI service)
    SCORE_CALCULATED = "score.calculated"
    MATCHES_FOUND = "matches.found"
    FREELANCER_INDEXED = "freelancer.indexed"
    FREELANCER_INDEX_FAILED = "freelancer.index_failed"


# Queue definitions
QUEUES = {
    "ai.freelancer.index": {
        "routing_keys": [
            EventType.FREELANCER_REGISTERED,
            EventType.FREELANCER_UPDATED,
            EventType.FREELANCER_DELETED,
        ],
        "durable": True,
    },
    "ai.job.match": {
        "routing_keys": [EventType.JOB_POSTED],
        "durable": True,
    },
}

# Exchange name
EXCHANGE_NAME = "bidwise"
