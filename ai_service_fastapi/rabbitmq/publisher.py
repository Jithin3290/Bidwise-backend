# rabbitmq/publisher.py - Event Publisher

import json
import logging
from datetime import datetime
from typing import Optional, Any, Dict

import aio_pika
from aio_pika import Message

from .connection import RabbitMQConnection, get_rabbitmq
from .events import EventType, EXCHANGE_NAME

logger = logging.getLogger(__name__)


class EventPublisher:
    """Publishes events to RabbitMQ"""

    def __init__(self, rabbitmq: RabbitMQConnection):
        self.rabbitmq = rabbitmq

    async def publish(
        self,
        event_type: EventType,
        data: Dict[str, Any],
        correlation_id: Optional[str] = None,
    ) -> bool:
        """
        Publish an event to RabbitMQ
        
        Args:
            event_type: The event type (routing key)
            data: Event payload data
            correlation_id: Optional correlation ID for tracking
            
        Returns:
            True if published successfully
        """
        try:
            if not self.rabbitmq.is_connected:
                logger.warning("RabbitMQ not connected, cannot publish event")
                return False

            # Add metadata to event
            event_data = {
                "event_type": event_type.value,
                "timestamp": datetime.utcnow().isoformat(),
                "data": data,
            }

            # Create message
            message = Message(
                body=json.dumps(event_data).encode(),
                content_type="application/json",
                correlation_id=correlation_id,
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            )

            # Publish to exchange
            await self.rabbitmq.exchange.publish(
                message,
                routing_key=event_type.value,
            )

            logger.info(f"Published event: {event_type.value}")
            logger.debug(f"Event data: {data}")
            return True

        except Exception as e:
            logger.error(f"Failed to publish event {event_type.value}: {e}")
            return False

    async def publish_score_calculated(
        self,
        user_id: int,
        final_score: float,
        tier: str,
    ) -> bool:
        """Publish score calculated event"""
        return await self.publish(
            EventType.SCORE_CALCULATED,
            {
                "user_id": user_id,
                "final_score": final_score,
                "tier": tier,
            },
        )

    async def publish_matches_found(
        self,
        job_id: str,
        client_id: int,
        matches: list,
    ) -> bool:
        """Publish matches found event"""
        top_user_ids = [m["user_id"] for m in matches[:10]]
        return await self.publish(
            EventType.MATCHES_FOUND,
            {
                "job_id": job_id,
                "client_id": client_id,
                "match_count": len(matches),
                "top_user_ids": top_user_ids,
            },
        )

    async def publish_freelancer_indexed(
        self,
        user_id: int,
        success: bool = True,
        error: Optional[str] = None,
    ) -> bool:
        """Publish freelancer indexed event"""
        event_type = EventType.FREELANCER_INDEXED if success else EventType.FREELANCER_INDEX_FAILED
        return await self.publish(
            event_type,
            {
                "user_id": user_id,
                "success": success,
                "error": error,
            },
        )


# Singleton instance
_publisher: Optional[EventPublisher] = None


async def get_publisher() -> EventPublisher:
    """Get or create the event publisher"""
    global _publisher
    if _publisher is None:
        rabbitmq = await get_rabbitmq()
        _publisher = EventPublisher(rabbitmq)
    return _publisher
