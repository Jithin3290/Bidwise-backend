# rabbitmq/connection.py - Async RabbitMQ Connection Manager

import asyncio
import logging
from typing import Optional
from contextlib import asynccontextmanager

import aio_pika
from aio_pika import Connection, Channel, Exchange, Queue
from aio_pika.abc import AbstractRobustConnection

from config import get_settings
from .events import EXCHANGE_NAME, QUEUES

logger = logging.getLogger(__name__)


class RabbitMQConnection:
    """Manages async RabbitMQ connections using aio-pika"""

    def __init__(self):
        self.settings = get_settings()
        self._connection: Optional[AbstractRobustConnection] = None
        self._channel: Optional[Channel] = None
        self._exchange: Optional[Exchange] = None
        self._queues: dict[str, Queue] = {}
        self._is_connected = False

    async def connect(self) -> None:
        """Establish connection to RabbitMQ"""
        try:
            # Create robust connection (auto-reconnect)
            self._connection = await aio_pika.connect_robust(
                self.settings.RABBITMQ_URL,
                timeout=30,
            )
            logger.info(f"Connected to RabbitMQ: {self.settings.RABBITMQ_URL}")

            # Create channel
            self._channel = await self._connection.channel()
            await self._channel.set_qos(prefetch_count=self.settings.RABBITMQ_PREFETCH_COUNT)
            logger.info("RabbitMQ channel created")

            # Declare exchange
            self._exchange = await self._channel.declare_exchange(
                EXCHANGE_NAME,
                aio_pika.ExchangeType.TOPIC,
                durable=True,
            )
            logger.info(f"Exchange declared: {EXCHANGE_NAME}")

            # Declare queues and bind them
            await self._setup_queues()
            
            self._is_connected = True

        except Exception as e:
            logger.error(f"Failed to connect to RabbitMQ: {e}")
            self._is_connected = False
            raise

    async def _setup_queues(self) -> None:
        """Declare queues and bind routing keys"""
        for queue_name, config in QUEUES.items():
            queue = await self._channel.declare_queue(
                queue_name,
                durable=config.get("durable", True),
            )
            
            # Bind routing keys
            for routing_key in config.get("routing_keys", []):
                await queue.bind(self._exchange, routing_key.value)
                logger.debug(f"Queue {queue_name} bound to {routing_key.value}")

            self._queues[queue_name] = queue
            logger.info(f"Queue declared: {queue_name}")

    async def disconnect(self) -> None:
        """Close connection"""
        if self._connection and not self._connection.is_closed:
            await self._connection.close()
            logger.info("Disconnected from RabbitMQ")
        self._is_connected = False

    @property
    def is_connected(self) -> bool:
        """Check if connected"""
        return self._is_connected and self._connection and not self._connection.is_closed

    @property
    def channel(self) -> Optional[Channel]:
        """Get the channel"""
        return self._channel

    @property
    def exchange(self) -> Optional[Exchange]:
        """Get the exchange"""
        return self._exchange

    def get_queue(self, queue_name: str) -> Optional[Queue]:
        """Get a queue by name"""
        return self._queues.get(queue_name)

    @asynccontextmanager
    async def get_channel(self):
        """Context manager for getting a channel"""
        if not self.is_connected:
            await self.connect()
        yield self._channel


# Global connection instance
_rabbitmq: Optional[RabbitMQConnection] = None


async def get_rabbitmq() -> RabbitMQConnection:
    """Get or create the RabbitMQ connection"""
    global _rabbitmq
    if _rabbitmq is None:
        _rabbitmq = RabbitMQConnection()
    return _rabbitmq


async def connect_rabbitmq() -> RabbitMQConnection:
    """Connect to RabbitMQ and return the connection"""
    rabbitmq = await get_rabbitmq()
    if not rabbitmq.is_connected:
        await rabbitmq.connect()
    return rabbitmq


async def disconnect_rabbitmq() -> None:
    """Disconnect from RabbitMQ"""
    global _rabbitmq
    if _rabbitmq:
        await _rabbitmq.disconnect()
        _rabbitmq = None
