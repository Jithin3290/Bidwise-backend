# notifications/services.py - Enhanced with caching
import os
for var in ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy',
            'ALL_PROXY', 'all_proxy', 'NO_PROXY', 'no_proxy']:
    os.environ.pop(var, None)
import logging
import os

import httpx
import requests
import hashlib
from typing import Dict, List, Optional, Any
from django.conf import settings
from django.core.cache import cache
from django.utils import timezone
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
from .models import Notification, UserNotificationPreference, NotificationChannel

logger = logging.getLogger(__name__)


class CacheManager:
    """Centralized cache management"""

    @staticmethod
    def get_cache_key(*parts):
        """Generate cache key from parts"""
        return ":".join(str(part) for part in parts)

    @staticmethod
    def get_hash_key(data: str) -> str:
        """Generate hash for cache key"""
        return hashlib.md5(data.encode()).hexdigest()[:12]

    @staticmethod
    def invalidate_pattern(pattern: str):
        """Invalidate cache keys matching pattern"""
        try:
            cache.delete_pattern(pattern)
        except AttributeError:
            # Fallback for cache backends that don't support delete_pattern
            logger.warning(f"Cache backend doesn't support pattern deletion: {pattern}")


class NotificationService:
    """Service for handling notifications with caching"""

    def __init__(self):
        self.channel_layer = get_channel_layer()
        self.cache_timeout = getattr(settings, 'NOTIFICATION_CACHE_TIMEOUT', 1800)  # 30 minutes

    def send_notification(self, notification):
        """Send notification via all configured channels"""
        try:
            # Cache key for user preferences
            user_prefs_key = CacheManager.get_cache_key("user_prefs", notification.recipient_id,
                                                        notification.notification_type.id)
            preferences = cache.get(user_prefs_key)

            if preferences is None:
                # Get user preferences
                preferences = UserNotificationPreference.objects.filter(
                    user_id=notification.recipient_id,
                    notification_type=notification.notification_type,
                    is_enabled=True
                ).prefetch_related('channels')

                # Cache preferences
                cache.set(user_prefs_key, list(preferences), timeout=self.cache_timeout)

            if preferences:
                # Use user preferences
                channels_to_use = []
                for pref in preferences:
                    channels_to_use.extend(pref.channels.filter(is_active=True))
            else:
                # Use default channels for notification type
                default_channels_key = CacheManager.get_cache_key("default_channels", notification.notification_type.id)
                channels_to_use = cache.get(default_channels_key)

                if channels_to_use is None:
                    channels_to_use = notification.notification_type.default_channels.filter(is_active=True)
                    cache.set(default_channels_key, list(channels_to_use), timeout=3600)  # Cache for 1 hour

            # Send via each channel
            for channel in channels_to_use:
                if channel.name == 'web':
                    self._send_web_notification(notification)
                elif channel.name == 'email':
                    self._send_email_notification(notification)
                elif channel.name == 'sms':
                    self._send_sms_notification(notification)
                elif channel.name == 'push':
                    self._send_push_notification(notification)

            # Mark as sent
            notification.mark_as_sent()

            # Invalidate user notification caches
            self._invalidate_user_notification_cache(notification.recipient_id)

        except Exception as e:
            logger.error(f"Error sending notification {notification.id}: {e}")

    def _send_web_notification(self, notification):
        """Send web notification via WebSocket"""
        if self.channel_layer:
            try:
                notification_data = {
                    'id': str(notification.id),
                    'title': notification.title,
                    'message': notification.message,
                    'type': notification.notification_type.name,
                    'priority': notification.priority,
                    'status': notification.status,
                    'data': notification.data,
                    'action_url': notification.action_url,
                    'action_text': notification.action_text,
                    'created_at': notification.created_at.isoformat(),
                }

                async_to_sync(self.channel_layer.group_send)(
                    f"notifications_{notification.recipient_id}",
                    {
                        'type': 'notification_message',
                        'notification': notification_data
                    }
                )

                logger.info(f"Web notification sent to user {notification.recipient_id}")

            except Exception as e:
                logger.error(f"Error sending web notification: {e}")

    def _send_email_notification(self, notification):
        """Send email notification with caching"""
        try:
            # Get user email from cache first
            user_service = UserService()
            user_data = user_service.get_user_profile(notification.recipient_id)

            if user_data and user_data.get('email'):
                from django.core.mail import send_mail
                from django.template.loader import render_to_string

                # Cache email template rendering
                template_cache_key = CacheManager.get_cache_key(
                    "email_template",
                    notification.notification_type.name,
                    CacheManager.get_hash_key(str(notification.data))
                )

                html_message = cache.get(template_cache_key)
                if html_message is None:
                    html_message = render_to_string('notifications/ email_notification.html', {
                        'notification': notification,
                        'user_data': user_data
                    })
                    cache.set(template_cache_key, html_message, timeout=3600)

                send_mail(
                    subject=notification.title,
                    message=notification.message,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[user_data['email']],
                    html_message=html_message,
                    fail_silently=False
                )

                logger.info(f"Email notification sent to {user_data['email']}")

        except Exception as e:
            logger.error(f"Error sending email notification: {e}")

    def _send_sms_notification(self, notification):
        """Send SMS notification"""
        # Implement SMS sending logic here
        # This would integrate with services like Twilio, AWS SNS, etc.
        pass

    def _send_push_notification(self, notification):
        """Send push notification"""
        # Implement push notification logic here
        # This would integrate with Firebase, APNS, etc.
        pass

    def _invalidate_user_notification_cache(self, user_id):
        """Invalidate all notification-related caches for a user"""
        patterns = [
            f"user_{user_id}_notifications_*",
            f"user_{user_id}_notification_stats*",
            f"user_prefs_{user_id}_*"
        ]
        for pattern in patterns:
            CacheManager.invalidate_pattern(pattern)


class UserService:
    """Service to communicate with Users microservice with caching"""

    def __init__(self):
        self.base_url = getattr(settings, 'USERS_SERVICE_URL', 'http://users_service:8000')
        self.service_token = getattr(settings, 'SERVICE_TOKEN', 'secure-service-token-123')
        self.timeout = 10
        self.cache_timeout = 1800  # 30 minutes for user data

    def get_user_profile(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Get user profile from Users service with caching"""
        cache_key = f"user_profile_{user_id}"
        cached_profile = cache.get(cache_key)

        if cached_profile:
            return cached_profile

        try:
            response = requests.get(
                f"{self.base_url}/api/service/users/{user_id}/profile/",
                headers={
                    'Authorization': f'Bearer {self.service_token}',
                    'Content-Type': 'application/json'
                },
                timeout=self.timeout
            )

            if response.status_code == 200:
                user_data = response.json()
                # Cache user profile data
                cache.set(cache_key, user_data, timeout=self.cache_timeout)
                return user_data
            else:
                logger.error(f"Failed to fetch user {user_id}: {response.status_code}")
                return None

        except requests.RequestException as e:
            logger.error(f"Error fetching user {user_id}: {e}")
            return None

    def get_multiple_user_profiles(self, user_ids: List[str]) -> Dict[str, Dict]:
        """Get multiple user profiles with batch caching"""
        results = {}
        uncached_ids = []

        # Check cache for each user
        for user_id in user_ids:
            cache_key = f"user_profile_{user_id}"
            cached_profile = cache.get(cache_key)
            if cached_profile:
                results[user_id] = cached_profile
            else:
                uncached_ids.append(user_id)

        # Fetch uncached profiles in batch
        if uncached_ids:
            try:
                response = requests.post(
                    f"{self.base_url}/api/service/users/profiles/batch/",
                    headers={
                        'Authorization': f'Bearer {self.service_token}',
                        'Content-Type': 'application/json'
                    },
                    json={'user_ids': uncached_ids},
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    batch_data = response.json()
                    for user_id, user_data in batch_data.items():
                        # Cache each profile
                        cache_key = f"user_profile_{user_id}"
                        cache.set(cache_key, user_data, timeout=self.cache_timeout)
                        results[user_id] = user_data
                else:
                    logger.error(f"Failed to fetch batch users: {response.status_code}")

            except requests.RequestException as e:
                logger.error(f"Error fetching batch users: {e}")

        return results

    def invalidate_user_cache(self, user_id: str):
        """Invalidate user-related cache entries"""
        patterns = [f"user_profile_{user_id}*", f"user_{user_id}_*"]
        for pattern in patterns:
            CacheManager.invalidate_pattern(pattern)


class MessagingService:
    """Service for handling messaging with caching"""

    def __init__(self):
        self.channel_layer = get_channel_layer()
        self.cache_timeout = 300  # 5 minutes for messaging data

    def send_message_notification(self, message):
        """Send real-time message notification with caching"""
        try:
            conversation = message.conversation

            # Cache message data for quick access
            message_cache_key = f"message_{message.id}_data"
            message_data = {
                'id': str(message.id),
                'conversation_id': str(conversation.id),
                'sender_id': message.sender_id,
                'content': message.content,
                'message_type': message.message_type,
                'reply_to': str(message.reply_to.id) if message.reply_to else None,
                'created_at': message.created_at.isoformat(),
                'is_edited': message.is_edited,
            }
            cache.set(message_cache_key, message_data, timeout=self.cache_timeout)

            # Send to conversation group
            async_to_sync(self.channel_layer.group_send)(
                f"conversation_{conversation.id}",
                {
                    'type': 'chat_message',
                    'message': message_data
                }
            )

            # Send to individual messaging groups for offline users
            for participant_id in conversation.participants:
                if str(participant_id) != str(message.sender_id):
                    async_to_sync(self.channel_layer.group_send)(
                        f"messaging_{participant_id}",
                        {
                            'type': 'chat_message',
                            'message': message_data
                        }
                    )

            # Invalidate conversation caches
            self._invalidate_conversation_cache(conversation.id)

            logger.info(f"Real-time message sent to conversation {conversation.id}")

        except Exception as e:
            logger.error(f"Error sending real-time message: {e}")

    def send_message_update(self, message, update_type: str):
        """Send real-time message update (edit/delete)"""
        try:
            conversation = message.conversation

            # Invalidate message cache
            message_cache_key = f"message_{message.id}_data"
            cache.delete(message_cache_key)

            # Prepare update data
            update_data = {
                'message_id': str(message.id),
                'conversation_id': str(conversation.id),
                'update_type': update_type,
                'content': message.content if update_type == 'edited' else None,
                'is_deleted': message.is_deleted,
                'is_edited': message.is_edited,
                'updated_at': message.updated_at.isoformat() if message.updated_at else None
            }

            # Send to conversation group
            async_to_sync(self.channel_layer.group_send)(
                f"conversation_{conversation.id}",
                {
                    'type': 'message_update',
                    'message_id': str(message.id),
                    'update_data': update_data
                }
            )

            # Invalidate related caches
            self._invalidate_conversation_cache(conversation.id)

            # Invalidate search caches for all participants
            for participant_id in conversation.participants:
                search_pattern = f"message_search_{participant_id}_*"
                CacheManager.invalidate_pattern(search_pattern)

            logger.info(f"Message update sent for {message.id}: {update_type}")

        except Exception as e:
            logger.error(f"Error sending message update: {e}")

    def get_conversation_last_messages(self, conversation_ids: List[str]) -> Dict[str, Dict]:
        """Get last messages for multiple conversations with caching"""
        results = {}

        for conversation_id in conversation_ids:
            cache_key = f"conversation_{conversation_id}_last_message"
            cached_message = cache.get(cache_key)

            if cached_message:
                results[conversation_id] = cached_message
            else:
                # Fetch from database
                from .models import Message
                try:
                    last_message = Message.objects.filter(
                        conversation_id=conversation_id,
                        is_deleted=False
                    ).order_by('-created_at').first()

                    if last_message:
                        message_data = {
                            'id': str(last_message.id),
                            'content': last_message.content,
                            'sender_id': last_message.sender_id,
                            'created_at': last_message.created_at.isoformat(),
                            'message_type': last_message.message_type
                        }
                        # Cache for 5 minutes
                        cache.set(cache_key, message_data, timeout=300)
                        results[conversation_id] = message_data

                except Exception as e:
                    logger.error(f"Error fetching last message for conversation {conversation_id}: {e}")

        return results

    def _invalidate_conversation_cache(self, conversation_id):
        """Invalidate conversation-related cache entries"""
        patterns = [
            f"conversation_{conversation_id}_*",
            f"*_conversation_{conversation_id}_*"
        ]
        for pattern in patterns:
            CacheManager.invalidate_pattern(pattern)


class JobService:
    """Service to communicate with Jobs microservice with caching"""

    def __init__(self):
        self.base_url = getattr(settings, 'JOBS_SERVICE_URL', 'http://jobs_service:8001')
        self.service_token = getattr(settings, 'SERVICE_TOKEN', 'secure-service-token-123')
        self.timeout = 10
        self.cache_timeout = 3600  # 1 hour for job data

    def get_job_details(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job details with caching"""
        cache_key = f"job_details_{job_id}"
        cached_job = cache.get(cache_key)

        if cached_job:
            return cached_job

        try:
            response = requests.get(
                f"{self.base_url}/api/service/jobs/{job_id}/",
                headers={
                    'Authorization': f'Bearer {self.service_token}',
                    'Content-Type': 'application/json'
                },
                timeout=self.timeout
            )

            if response.status_code == 200:
                job_data = response.json()
                # Cache job data
                cache.set(cache_key, job_data, timeout=self.cache_timeout)
                return job_data
            else:
                logger.error(f"Failed to fetch job {job_id}: {response.status_code}")
                return None

        except requests.RequestException as e:
            logger.error(f"Error fetching job {job_id}: {e}")
            return None

    def invalidate_job_cache(self, job_id: str):
        """Invalidate job-related cache entries"""
        patterns = [f"job_details_{job_id}*", f"job_{job_id}_*"]
        for pattern in patterns:
            CacheManager.invalidate_pattern(pattern)


class BidService:
    """Service to communicate with Bids microservice with caching"""

    def __init__(self):
        self.base_url = getattr(settings, 'BIDS_SERVICE_URL', 'http://bids_service:8002')
        self.service_token = getattr(settings, 'SERVICE_TOKEN', 'secure-service-token-123')
        self.timeout = 10
        self.cache_timeout = 1800  # 30 minutes for bid data

    def get_bid_details(self, bid_id: str) -> Optional[Dict[str, Any]]:
        """Get bid details with caching"""
        cache_key = f"bid_details_{bid_id}"
        cached_bid = cache.get(cache_key)

        if cached_bid:
            return cached_bid

        try:
            response = requests.get(
                f"{self.base_url}/api/service/bids/{bid_id}/",
                headers={
                    'Authorization': f'Bearer {self.service_token}',
                    'Content-Type': 'application/json'
                },
                timeout=self.timeout
            )

            if response.status_code == 200:
                bid_data = response.json()
                # Cache bid data
                cache.set(cache_key, bid_data, timeout=self.cache_timeout)
                return bid_data
            else:
                logger.error(f"Failed to fetch bid {bid_id}: {response.status_code}")
                return None

        except requests.RequestException as e:
            logger.error(f"Error fetching bid {bid_id}: {e}")
            return None

    def invalidate_bid_cache(self, bid_id: str):
        """Invalidate bid-related cache entries"""
        patterns = [f"bid_details_{bid_id}*", f"bid_{bid_id}_*"]
        for pattern in patterns:
            CacheManager.invalidate_pattern(pattern)


class CacheWarmupService:
    """Service to warm up frequently accessed data"""

    def __init__(self):
        self.user_service = UserService()
        self.messaging_service = MessagingService()

    def warm_up_user_data(self, user_id: str):
        """Pre-cache frequently accessed user data"""
        try:
            # Warm up user profile
            self.user_service.get_user_profile(user_id)

            # Warm up user conversations (SQLite compatible)
            from .models import Conversation
            user_conversations = Conversation.objects.filter(
                members__user_id=user_id,
                is_active=True
            ).values_list('id', flat=True)[:10]  # Top 10 most recent

            # Cache conversation IDs list
            cache_key = f"user_{user_id}_active_conversations"
            cache.set(cache_key, list(user_conversations), timeout=1800)

            # Warm up last messages for these conversations
            self.messaging_service.get_conversation_last_messages(
                [str(conv_id) for conv_id in user_conversations]
            )

            logger.info(f"Warmed up cache for user {user_id}")

        except Exception as e:
            logger.error(f"Error warming up cache for user {user_id}: {e}")

    def warm_up_conversation_data(self, conversation_id: str):
        """Pre-cache frequently accessed conversation data"""
        try:
            from .models import Conversation, Message

            # Get conversation
            conversation = Conversation.objects.get(id=conversation_id)

            # Warm up participant profiles
            self.user_service.get_multiple_user_profiles(conversation.participants)

            # Cache recent messages
            recent_messages = Message.objects.filter(
                conversation=conversation,
                is_deleted=False
            ).order_by('-created_at')[:50]

            messages_data = []
            for message in recent_messages:
                message_data = {
                    'id': str(message.id),
                    'content': message.content,
                    'sender_id': message.sender_id,
                    'created_at': message.created_at.isoformat(),
                    'message_type': message.message_type,
                    'is_edited': message.is_edited
                }
                messages_data.append(message_data)

            cache_key = f"conversation_{conversation_id}_recent_messages"
            cache.set(cache_key, messages_data, timeout=600)

            logger.info(f"Warmed up cache for conversation {conversation_id}")

        except Exception as e:
            logger.error(f"Error warming up cache for conversation {conversation_id}: {e}")

    def cleanup_expired_cache(self):
        """Clean up expired cache entries (can be run as a periodic task)"""
        try:
            # This would depend on your cache backend
            # Redis example:
            from django.core.cache.backends.redis import RedisCache
            if isinstance(cache, RedisCache):
                # Get all keys and check TTL
                # Implementation would depend on specific needs
                pass

        except Exception as e:
            logger.error(f"Error cleaning up cache: {e}")


# Utility functions for cache management
def warm_up_user_cache(user_id: str):
    """Utility function to warm up user cache"""
    warmup_service = CacheWarmupService()
    warmup_service.warm_up_user_data(user_id)


def invalidate_all_user_caches(user_id: str):
    """Invalidate all cache entries for a user"""
    patterns = [
        f"user_{user_id}_*",
        f"user_profile_{user_id}*",
        f"*_{user_id}_*"
    ]
    for pattern in patterns:
        CacheManager.invalidate_pattern(pattern)


# Add to your existing services.py

import httpx
from openai import OpenAI

from .models import (
    Notification, UserNotificationPreference, NotificationChannel,
    AIConversation, AIMessage
)

logger = logging.getLogger(__name__)


# ... your other service classes ...

import google.generativeai as genai


# Remove these lines:
# import httpx
# from openai import OpenAI


class AIChatService:
    """Service for handling AI chat interactions with Google Gemini"""

    def __init__(self):
        if not settings.GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY not configured")

        logger.info("Initializing AIChatService with Google Gemini 2.0")

        # Configure Gemini
        genai.configure(api_key=settings.GEMINI_API_KEY)

        # Use Gemini 2.0 Flash model
        self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
        self.default_temperature = 0.7
        self.default_max_tokens = 8192

        logger.info("AIChatService initialized successfully with Gemini 2.0")

    def get_or_create_conversation(self, user_id, conversation_id=None):
        """Get existing AI conversation or create new one"""
        if conversation_id:
            try:
                conversation = AIConversation.objects.get(
                    id=conversation_id,
                    user_id=user_id,
                    is_active=True
                )
                return conversation
            except AIConversation.DoesNotExist:
                pass

        return AIConversation.objects.create(
            user_id=user_id,
            title=f"AI Chat - {timezone.now().strftime('%Y-%m-%d %H:%M')}",
            model_name='gemini-pro'
        )

    def get_conversation_history(self, conversation):
        """Build message history for Gemini format"""
        messages = AIMessage.objects.filter(
            conversation=conversation
        ).order_by('created_at')

        # Gemini format: list of {'role': 'user'/'model', 'parts': [text]}
        history = []
        for msg in messages:
            if msg.role == 'user':
                history.append({
                    'role': 'user',
                    'parts': [msg.content]
                })
            elif msg.role == 'assistant':
                history.append({
                    'role': 'model',  # Gemini uses 'model' instead of 'assistant'
                    'parts': [msg.content]
                })

        return history

    def generate_response(self, user_message, user_id, conversation_id=None, system_prompt=None):
        """Generate AI response using Gemini and save to database"""
        try:
            conversation = self.get_or_create_conversation(user_id, conversation_id)

            # Save user message
            user_msg = AIMessage.objects.create(
                conversation=conversation,
                role='user',
                content=user_message
            )

            # Build message history
            history = self.get_conversation_history(conversation)

            logger.info(f"Calling Gemini API with {len(history)} messages")

            # Start chat with history
            chat = self.model.start_chat(history=history[:-1] if len(history) > 1 else [])

            # Add system instructions if this is the first message
            prompt = user_message
            if len(history) == 1 and system_prompt:
                prompt = f"{system_prompt}\n\nUser: {user_message}"
            elif len(history) == 1:
                prompt = f"You are a helpful AI assistant for a freelance platform. Help users with their questions about jobs, bids, projects, and general platform usage.\n\nUser: {user_message}"

            # Generate response
            response = chat.send_message(prompt)
            ai_message_content = response.text

            # Gemini doesn't provide token counts in the same way, estimate them
            prompt_tokens = len(prompt.split()) * 1.3  # rough estimate
            completion_tokens = len(ai_message_content.split()) * 1.3
            total_tokens = int(prompt_tokens + completion_tokens)

            # Save AI response
            ai_msg = AIMessage.objects.create(
                conversation=conversation,
                role='assistant',
                content=ai_message_content,
                prompt_tokens=int(prompt_tokens),
                completion_tokens=int(completion_tokens),
                total_tokens=total_tokens
            )

            # Update conversation stats
            conversation.total_tokens_used += total_tokens
            conversation.total_messages += 2
            conversation.last_message_at = timezone.now()
            conversation.save(update_fields=['total_tokens_used', 'total_messages', 'last_message_at'])

            logger.info(f"Response generated successfully: ~{total_tokens} tokens")

            return {
                'conversation_id': str(conversation.id),
                'message': ai_message_content,
                'message_id': str(ai_msg.id),
                'usage': {
                    'prompt_tokens': int(prompt_tokens),
                    'completion_tokens': int(completion_tokens),
                    'total_tokens': total_tokens
                }
            }

        except Exception as e:
            logger.error(f"Error generating AI response: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            raise

    def delete_conversation(self, conversation_id, user_id):
        """Delete an AI conversation"""
        try:
            conversation = AIConversation.objects.get(
                id=conversation_id,
                user_id=user_id
            )
            conversation.is_active = False
            conversation.save(update_fields=['is_active'])
            return True
        except AIConversation.DoesNotExist:
            return False

    def get_user_conversations(self, user_id, limit=20):
        """Get user's AI conversations"""
        return AIConversation.objects.filter(
            user_id=user_id,
            is_active=True
        ).order_by('-last_message_at')[:limit]