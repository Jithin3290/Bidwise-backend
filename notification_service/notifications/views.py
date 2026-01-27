import logging
from .services import MessagingService
from django.db import models
from django.db.models import Q, F
from django.utils import timezone
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from django.db.models import Q
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import (
    Notification, NotificationType, UserNotificationPreference,
    Conversation, Message, ConversationMember,MessageReadStatus
)
from .serializers import (
    NotificationSerializer, NotificationCreateSerializer,
    UserNotificationPreferenceSerializer, ConversationSerializer,
    MessageSerializer, ConversationCreateSerializer, MessageCreateSerializer
)
from .authentication import ServiceAuthentication, JWTAuthentication
from .services import NotificationService, UserService

logger = logging.getLogger(__name__)


class StandardPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100

class StartConversationView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        participant_ids = request.data.get('participant_ids', [])
        conversation_type = request.data.get('type', 'direct')
        title = request.data.get('title', '')
        job_id = request.data.get('job_id')
        bid_id = request.data.get('bid_id')

        if not participant_ids:
            return Response({'error': 'participant_ids required'}, status=status.HTTP_400_BAD_REQUEST)

        user_id = str(request.user.user_id)
        if user_id not in participant_ids:
            participant_ids.append(user_id)

        if conversation_type == 'direct' and len(participant_ids) == 2:
            existing = Conversation.objects.filter(
                participants=participant_ids,
                conversation_type='direct',
                is_active=True
            ).first()
            if existing:
                serializer = ConversationSerializer(existing, context={'request': request})
                return Response(serializer.data)

        conversation = Conversation.objects.create(
            participants=participant_ids,
            conversation_type=conversation_type,
            title=title or f"Conversation with {len(participant_ids)} participants",
            job_id=job_id,
            bid_id=bid_id
        )

        for participant_id in participant_ids:
            ConversationMember.objects.get_or_create(
                conversation=conversation,
                user_id=participant_id
            )

        serializer = ConversationSerializer(conversation, context={'request': request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ConversationParticipantsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):
        try:
            conversation = Conversation.objects.get(
                id=conversation_id,
                participants__contains=[request.user.user_id]
            )
            user_service = UserService()
            participants_data = []
            for participant_id in conversation.participants:
                user_data = user_service.get_user_profile(participant_id)
                if user_data:
                    participants_data.append({
                        'id': participant_id,
                        'username': user_data.get('username', ''),
                        'full_name': user_data.get('full_name', ''),
                        'profile_picture': user_data.get('profile_picture'),
                        'is_online': user_data.get('is_online', False),
                        'last_seen': user_data.get('last_seen')
                    })
            return Response({'participants': participants_data})
        except Conversation.DoesNotExist:
            return Response({'error': 'Conversation not found'}, status=status.HTTP_404_NOT_FOUND)

class UpdateConversationView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, conversation_id):
        try:
            conversation = Conversation.objects.get(
                id=conversation_id,
                participants__contains=[request.user.user_id]
            )
            if 'title' in request.data:
                conversation.title = request.data['title']
            if 'is_active' in request.data:
                conversation.is_active = request.data['is_active']
            conversation.save()
            serializer = ConversationSerializer(conversation, context={'request': request})
            return Response(serializer.data)
        except Conversation.DoesNotExist:
            return Response({'error': 'Conversation not found'}, status=status.HTTP_404_NOT_FOUND)

class EditMessageView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, message_id):
        try:
            message = Message.objects.get(
                id=message_id,
                sender_id=request.user.user_id,
                is_deleted=False
            )
            new_content = request.data.get('content', '').strip()
            if not new_content:
                return Response({'error': 'Content cannot be empty'}, status=status.HTTP_400_BAD_REQUEST)
            message.content = new_content
            message.is_edited = True
            message.save(update_fields=['content', 'is_edited', 'updated_at'])

            messaging_service = MessagingService()
            messaging_service.send_message_update(message, 'edited')

            serializer = MessageSerializer(message)
            return Response(serializer.data)
        except Message.DoesNotExist:
            return Response({'error': 'Message not found'}, status=status.HTTP_404_NOT_FOUND)


class DeleteMessageView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, message_id):
        try:
            message = Message.objects.get(
                id=message_id,
                sender_id=request.user.user_id,
                is_deleted=False
            )
            message.is_deleted = True
            message.save(update_fields=['is_deleted', 'updated_at'])

            messaging_service = MessagingService()
            messaging_service.send_message_update(message, 'deleted')

            return Response({'message': 'Message deleted successfully'})
        except Message.DoesNotExist:
            return Response({'error': 'Message not found'}, status=status.HTTP_404_NOT_FOUND)

class SearchMessagesView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        conversation_id = request.query_params.get('conversation_id')

        if not query:
            return Response({'error': 'Search query required'}, status=status.HTTP_400_BAD_REQUEST)

        user_id = str(request.user.user_id)
        user_conversations = Conversation.objects.filter(
            participants__contains=[user_id],
            is_active=True
        )

        search_filter = Q(conversation__in=user_conversations, is_deleted=False) & Q(content__icontains=query)
        if conversation_id:
            search_filter &= Q(conversation_id=conversation_id)

        messages = Message.objects.filter(search_filter).order_by('-created_at')[:50]
        serializer = MessageSerializer(messages, many=True)
        return Response({
            'query': query,
            'results': serializer.data,
            'count': len(messages)
        })


# ============= NOTIFICATION VIEWS =============
class CreateNotificationView(APIView):
    authentication_classes=[ServiceAuthentication]
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = NotificationCreateSerializer(data=request.data)
        if serializer.is_valid():
            try:
                notification_type = NotificationType.objects.get(
                    name=serializer.validated_data['notification_type']
                )
                notification = Notification.objects.create(
                    recipient_id=serializer.validated_data['recipient_id'],
                    notification_type=notification_type,
                    title=serializer.validated_data['title'],
                    message=serializer.validated_data['message'],
                    data=serializer.validated_data.get('data', {}),
                    priority=serializer.validated_data.get('priority', 'normal'),
                    action_url=serializer.validated_data.get('action_url'),
                    action_text=serializer.validated_data.get('action_text'),
                    expires_at=serializer.validated_data.get('expires_at')
                )
                notification_service = NotificationService()
                notification_service.send_notification(notification)
                return Response({'id': str(notification.id), 'message': 'Notification created successfully'}, status=status.HTTP_201_CREATED)
            except NotificationType.DoesNotExist:
                return Response({'error': f'Notification type "{serializer.validated_data["notification_type"]}" not found'}, status=status.HTTP_400_BAD_REQUEST)
            except Exception as e:
                logger.error(f"Error creating notification: {e}")
                return Response({'error': 'Failed to create notification'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, notification_id=None):

        if not notification_id:
            return Response({'error': 'Notification ID is required'}, status=400)
        try:
            notification = Notification.objects.get(id=notification_id)
            notification.delete()
            return Response({'message': f'Notification {notification_id} deleted successfully'}, status=200)
        except Notification.DoesNotExist:
            return Response({'error': 'Notification not found'}, status=404)
        except Exception as e:
            logger.error(f"Error deleting notification {notification_id}: {e}")
            return Response({'error': 'Failed to delete notification'}, status=500)


class UserNotificationsView(generics.ListAPIView):
    """Get user's notifications"""
    serializer_class = NotificationSerializer
    pagination_class = StandardPagination
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user_id = self.request.user.user_id
        queryset = Notification.objects.filter(recipient_id=user_id)

        # Filter by status
        status_filter = self.request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        # Filter by type
        type_filter = self.request.query_params.get('type')
        if type_filter:
            queryset = queryset.filter(notification_type__name=type_filter)

        # Filter by priority
        priority_filter = self.request.query_params.get('priority')
        if priority_filter:
            queryset = queryset.filter(priority=priority_filter)

        return queryset.order_by('-created_at')


class MarkNotificationReadView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request, notification_id):
        try:
            notification = Notification.objects.get(
                id=notification_id,
                recipient_id=request.user.user_id
            )
            notification.mark_as_read()
            return Response({'message': 'Notification marked as read'})
        except Notification.DoesNotExist:
            return Response({'error': 'Notification not found'}, status=status.HTTP_404_NOT_FOUND)


class MarkAllNotificationsReadView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user_id = request.user.user_id
        Notification.objects.filter(
            recipient_id=user_id,
            status__in=['pending', 'sent', 'delivered']
        ).update(status='read', read_at=timezone.now())
        return Response({'message': 'All notifications marked as read'})


class NotificationStatsView(APIView):
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = request.user.user_id
        total = Notification.objects.filter(recipient_id=user_id).count()
        unread = Notification.objects.filter(recipient_id=user_id, status__in=['pending', 'sent', 'delivered']).count()
        return Response({
            'total_notifications': total,
            'unread_count': unread,
            'read_count': total - unread
        })


# ============= MESSAGING VIEWS =============

class ConversationListView(generics.ListAPIView):
    """List user's conversations"""
    serializer_class = ConversationSerializer
    pagination_class = StandardPagination
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user_id = str(self.request.user.user_id)

        # Get conversations where user is a participant
        queryset = Conversation.objects.filter(
            participants__contains=[user_id],
            is_active=True
        ).order_by('-last_message_at')

        # Filter by type
        conversation_type = self.request.query_params.get('type')
        if conversation_type:
            queryset = queryset.filter(conversation_type=conversation_type)

        # Filter by job/bid/project
        job_id = self.request.query_params.get('job_id')
        if job_id:
            queryset = queryset.filter(job_id=job_id)

        bid_id = self.request.query_params.get('bid_id')
        if bid_id:
            queryset = queryset.filter(bid_id=bid_id)

        return queryset


class ConversationCreateView(generics.CreateAPIView):
    """Create a new conversation"""
    serializer_class = ConversationCreateSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        # Ensure current user is in participants
        user_id = str(self.request.user.user_id)
        participants = serializer.validated_data['participants']

        if user_id not in participants:
            participants.append(user_id)

        conversation = serializer.save(participants=participants)

        # Create conversation members
        for participant_id in participants:
            ConversationMember.objects.get_or_create(
                conversation=conversation,
                user_id=participant_id
            )

        return conversation


class ConversationDetailView(generics.RetrieveAPIView):
    """Get conversation details"""
    serializer_class = ConversationSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        user_id = str(self.request.user.user_id)
        return Conversation.objects.filter(participants__contains=[user_id])


class ConversationMessagesView(generics.ListAPIView):
    """Get messages in a conversation"""
    serializer_class = MessageSerializer
    pagination_class = StandardPagination
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        conversation_id = self.kwargs['conversation_id']
        user_id = str(self.request.user.user_id)

        # Verify user has access to conversation
        try:
            conversation = Conversation.objects.get(
                id=conversation_id,
                participants__contains=[user_id]
            )
        except Conversation.DoesNotExist:
            return Message.objects.none()

        return Message.objects.filter(
            conversation=conversation,
            is_deleted=False
        ).order_by('-created_at')


class SendMessageView(generics.CreateAPIView):
    """Send a message in a conversation"""
    serializer_class = MessageCreateSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        conversation_id = self.kwargs['conversation_id']
        user_id = str(self.request.user.user_id)

        # Verify user has access to conversation
        try:
            conversation = Conversation.objects.get(
                id=conversation_id,
                participants__contains=[user_id]
            )
        except Conversation.DoesNotExist:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Access denied to conversation")

        message = serializer.save(
            conversation=conversation,
            sender_id=user_id
        )

        # Update conversation timestamp
        conversation.last_message_at = message.created_at
        conversation.save(update_fields=['last_message_at'])

        # Update unread counts for other participants
        ConversationMember.objects.filter(
            conversation=conversation
        ).exclude(user_id=user_id).update(
            unread_count=F('unread_count') + 1
        )

        return message


class ConversationStatsView(APIView):
    """Get conversation statistics for user"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = str(request.user.user_id)

        total_conversations = Conversation.objects.filter(
            participants__contains=[user_id],
            is_active=True
        ).count()

        unread_conversations = ConversationMember.objects.filter(
            user_id=user_id,
            unread_count__gt=0,
            conversation__is_active=True
        ).count()

        total_unread_messages = ConversationMember.objects.filter(
            user_id=user_id,
            conversation__is_active=True
        ).aggregate(total=models.Sum('unread_count'))['total'] or 0

        return Response({
            'total_conversations': total_conversations,
            'unread_conversations': unread_conversations,
            'total_unread_messages': total_unread_messages
        })


class MarkConversationReadView(APIView):
    """Mark all messages in a conversation as read"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        user_id = str(request.user.user_id)

        try:
            conversation = Conversation.objects.get(
                id=conversation_id,
                participants__contains=[user_id]
            )

            unread_messages = Message.objects.filter(
                conversation=conversation,
                is_deleted=False
            ).exclude(
                models.Q(sender_id=user_id) |
                models.Q(read_statuses__user_id=user_id)
            )

            for message in unread_messages:
                MessageReadStatus.objects.get_or_create(
                    message=message,
                    user_id=user_id
                )

            member = ConversationMember.objects.filter(
                conversation=conversation,
                user_id=user_id
            ).first()

            if member:
                member.unread_count = 0
                member.last_seen_at = timezone.now()
                member.save(update_fields=['unread_count', 'last_seen_at'])

            return Response({'message': 'Conversation marked as read'})

        except Conversation.DoesNotExist:
            return Response(
                {'error': 'Conversation not found'},
                status=status.HTTP_404_NOT_FOUND
            )

# ============= UTILITY VIEWS =============

class HealthCheckView(APIView):
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'host': request.get_host(),
            'status': 'healthy',
            'service': 'notifications-service',
            'timestamp': timezone.now(),
            'version': '1.0.0',
            "sldfsj":"lsdfjkjfs"
        })


# Add to your existing views.py

from .models import AIConversation, AIMessage
from .serializers import (
    AIConversationSerializer, AIMessageSerializer,
    AIChatRequestSerializer, AIConversationCreateSerializer
)
from .services import AIChatService


# ============= AI CHAT VIEWS =============

class AIChatView(APIView):
    """Send message to AI and get response"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = AIChatRequestSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            ai_service = AIChatService()
            result = ai_service.generate_response(
                user_message=serializer.validated_data['message'],
                user_id=str(request.user.user_id),
                conversation_id=serializer.validated_data.get('conversation_id'),
                system_prompt=serializer.validated_data.get('system_prompt')
            )

            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"AI chat error: {str(e)}")
            return Response(
                {'error': 'Failed to generate AI response'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AIConversationListView(generics.ListAPIView):
    """List user's AI conversations"""
    serializer_class = AIConversationSerializer
    pagination_class = StandardPagination
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AIConversation.objects.filter(
            user_id=str(self.request.user.user_id),
            is_active=True
        ).order_by('-last_message_at')


class AIConversationDetailView(generics.RetrieveAPIView):
    """Get AI conversation details with full message history"""
    serializer_class = AIConversationSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return AIConversation.objects.filter(
            user_id=str(self.request.user.user_id),
            is_active=True
        )


class AIConversationDeleteView(APIView):
    """Delete an AI conversation"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request, conversation_id):
        try:
            ai_service = AIChatService()
            success = ai_service.delete_conversation(
                conversation_id=conversation_id,
                user_id=str(request.user.user_id)
            )

            if success:
                return Response({'message': 'Conversation deleted successfully'})
            else:
                return Response(
                    {'error': 'Conversation not found'},
                    status=status.HTTP_404_NOT_FOUND
                )
        except Exception as e:
            logger.error(f"Error deleting AI conversation: {str(e)}")
            return Response(
                {'error': 'Failed to delete conversation'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class AIConversationStatsView(APIView):
    """Get AI conversation statistics"""
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user_id = str(request.user.user_id)

        conversations = AIConversation.objects.filter(
            user_id=user_id,
            is_active=True
        )

        total_conversations = conversations.count()
        total_tokens = conversations.aggregate(
            total=models.Sum('total_tokens_used')
        )['total'] or 0
        total_messages = conversations.aggregate(
            total=models.Sum('total_messages')
        )['total'] or 0

        return Response({
            'total_conversations': total_conversations,
            'total_tokens_used': total_tokens,
            'total_messages': total_messages,
            'active_conversations': conversations.filter(
                last_message_at__gte=timezone.now() - timezone.timedelta(days=7)
            ).count()
        })