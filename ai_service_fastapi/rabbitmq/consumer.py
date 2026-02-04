# rabbitmq/consumer.py - Event Consumer

import json
import asyncio
import logging
from typing import Callable, Dict, Any, Optional

from aio_pika import IncomingMessage

from .connection import RabbitMQConnection, get_rabbitmq
from .publisher import get_publisher
from .events import EventType

logger = logging.getLogger(__name__)


class EventConsumer:
    """Consumes and processes events from RabbitMQ"""

    def __init__(self, rabbitmq: RabbitMQConnection):
        self.rabbitmq = rabbitmq
        self._handlers: Dict[str, Callable] = {}
        self._consuming = False
        self._tasks: list = []

    def register_handler(self, event_type: EventType, handler: Callable) -> None:
        """Register a handler for an event type"""
        self._handlers[event_type.value] = handler
        logger.info(f"Registered handler for: {event_type.value}")

    async def _process_message(self, message: IncomingMessage) -> None:
        """Process a single message"""
        async with message.process():
            try:
                body = json.loads(message.body.decode())
                event_type = body.get("event_type")
                data = body.get("data", {})

                logger.info(f"Received event: {event_type}")
                logger.debug(f"Event data: {data}")

                # Find and call handler
                handler = self._handlers.get(event_type)
                if handler:
                    await handler(data)
                else:
                    logger.warning(f"No handler registered for: {event_type}")

            except json.JSONDecodeError as e:
                logger.error(f"Failed to decode message: {e}")
            except Exception as e:
                logger.error(f"Error processing message: {e}")

    async def start_consuming(self, queue_name: str) -> None:
        """Start consuming messages from a queue"""
        if not self.rabbitmq.is_connected:
            logger.error("RabbitMQ not connected, cannot start consuming")
            return

        queue = self.rabbitmq.get_queue(queue_name)
        if not queue:
            logger.error(f"Queue not found: {queue_name}")
            return

        self._consuming = True
        logger.info(f"Starting to consume from: {queue_name}")

        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                if not self._consuming:
                    break
                await self._process_message(message)

    def stop_consuming(self) -> None:
        """Stop consuming messages"""
        self._consuming = False
        logger.info("Stopping consumers")


# ============ Event Handlers ============

async def handle_freelancer_registered(data: Dict[str, Any]) -> None:
    """Handle freelancer.registered event - Index the freelancer"""
    from services.vector_search import get_job_matcher
    from services.scoring_engine import get_scoring_engine
    
    user_id = data.get("user_id")
    if not user_id:
        logger.error("Missing user_id in freelancer.registered event")
        return

    try:
        # Index in vector store
        matcher = get_job_matcher()
        await matcher.index_freelancer(user_id)
        
        # Calculate initial score
        engine = get_scoring_engine()
        score_result = await engine.calculate_final_score(user_id)
        
        # Publish success events
        publisher = await get_publisher()
        await publisher.publish_freelancer_indexed(user_id, success=True)
        await publisher.publish_score_calculated(
            user_id=user_id,
            final_score=score_result["final_score"],
            tier=score_result["tier"],
        )
        
        logger.info(f"Successfully processed freelancer registration: {user_id}")

    except Exception as e:
        logger.error(f"Failed to process freelancer {user_id}: {e}")
        publisher = await get_publisher()
        await publisher.publish_freelancer_indexed(user_id, success=False, error=str(e))


async def handle_freelancer_updated(data: Dict[str, Any]) -> None:
    """Handle freelancer.updated event - Re-index the freelancer"""
    from services.vector_search import get_job_matcher
    from services.scoring_engine import get_scoring_engine
    
    user_id = data.get("user_id")
    if not user_id:
        logger.error("Missing user_id in freelancer.updated event")
        return

    try:
        # Re-index in vector store
        matcher = get_job_matcher()
        await matcher.index_freelancer(user_id)
        
        # Recalculate score (invalidate cache first)
        engine = get_scoring_engine()
        engine.invalidate_cache(user_id)
        score_result = await engine.calculate_final_score(user_id)
        
        # Publish events
        publisher = await get_publisher()
        await publisher.publish_freelancer_indexed(user_id, success=True)
        await publisher.publish_score_calculated(
            user_id=user_id,
            final_score=score_result["final_score"],
            tier=score_result["tier"],
        )
        
        logger.info(f"Successfully processed freelancer update: {user_id}")

    except Exception as e:
        logger.error(f"Failed to update freelancer {user_id}: {e}")


async def handle_freelancer_deleted(data: Dict[str, Any]) -> None:
    """Handle freelancer.deleted event - Remove from index"""
    from services.vector_search import get_job_matcher
    
    user_id = data.get("user_id")
    if not user_id:
        return

    try:
        matcher = get_job_matcher()
        matcher.delete_freelancer(user_id)
        logger.info(f"Removed freelancer from index: {user_id}")
    except Exception as e:
        logger.error(f"Failed to delete freelancer {user_id}: {e}")


async def handle_job_posted(data: Dict[str, Any]) -> None:
    """Handle job.posted event - Find matches and notify"""
    from services.vector_search import get_job_matcher
    
    job_id = data.get("job_id")
    client_id = data.get("client_id")
    job_description = data.get("job_description", "")
    required_skills = data.get("required_skills", [])

    if not job_id or not job_description:
        logger.error("Missing job_id or job_description in job.posted event")
        return

    try:
        # Find matches
        matcher = get_job_matcher()
        matches = matcher.find_best_matches(
            job_description=job_description,
            required_skills=required_skills,
            top_k=20,
        )

        # Publish matches found event
        publisher = await get_publisher()
        await publisher.publish_matches_found(
            job_id=job_id,
            client_id=client_id,
            matches=matches,
        )

        logger.info(f"Found {len(matches)} matches for job {job_id}")

    except Exception as e:
        logger.error(f"Failed to match job {job_id}: {e}")


# ============ Consumer Setup ============

async def setup_consumers(rabbitmq: RabbitMQConnection) -> EventConsumer:
    """Setup and start all consumers"""
    consumer = EventConsumer(rabbitmq)

    # Register handlers
    consumer.register_handler(EventType.FREELANCER_REGISTERED, handle_freelancer_registered)
    consumer.register_handler(EventType.FREELANCER_UPDATED, handle_freelancer_updated)
    consumer.register_handler(EventType.FREELANCER_DELETED, handle_freelancer_deleted)
    consumer.register_handler(EventType.JOB_POSTED, handle_job_posted)

    # Start consuming in background tasks
    asyncio.create_task(consumer.start_consuming("ai.freelancer.index"))
    asyncio.create_task(consumer.start_consuming("ai.job.match"))

    logger.info("All consumers started")
    return consumer
