from django.core.management.base import BaseCommand
from ...models import NotificationChannel, NotificationType


class Command(BaseCommand):
    help = 'Set up initial notification channels and types'

    def handle(self, *args, **options):
        self.stdout.write('Setting up notification system...')

        # Create notification channels
        channels_data = [
            ('web', 'Web Notification'),
            ('email', 'Email'),
            ('sms', 'SMS'),
            ('push', 'Push Notification'),
        ]

        created_channels = 0
        for name, display_name in channels_data:
            channel, created = NotificationChannel.objects.get_or_create(
                name=name,
                defaults={'is_active': True}
            )
            if created:
                created_channels += 1
                self.stdout.write(f'✓ Created channel: {display_name}')
            else:
                self.stdout.write(f'  Channel already exists: {display_name}')

        # Create notification types
        types_data = [
            ('new_message', 'New Message', 'You have a new message', 'You received a message from {sender}'),
            ('message_reply', 'Message Reply', 'Someone replied to your message', 'You received a reply from {sender}'),
            ('bid_created', 'New Bid Received', 'New bid received', 'You received a new bid of ${amount} from {freelancer}'),
            ('bid_accepted', 'Bid Accepted', 'Your bid was accepted', 'Congratulations! Your bid of ${amount} was accepted'),
            ('bid_rejected', 'Bid Rejected', 'Your bid was not selected', 'Your bid was not selected for this project'),
            ('bid_withdrawn', 'Bid Withdrawn', 'Bid withdrawn', 'A freelancer withdrew their bid'),
            ('job_published', 'Job Published', 'Job published successfully', 'Your job "{title}" is now live'),
            ('job_updated', 'Job Updated', 'Job updated', 'Job "{title}" has been updated'),
            ('job_expired', 'Job Expired', 'Job expired', 'Your job "{title}" has expired'),
            ('job_completed', 'Job Completed', 'Job completed', 'Job "{title}" has been marked as completed'),
            ('account_verified', 'Account Verified', 'Account verified', 'Your account has been successfully verified'),
            ('profile_updated', 'Profile Updated', 'Profile updated', 'Your profile has been updated'),
            ('payment_received', 'Payment Received', 'Payment received', 'You received a payment of ${amount}'),
            ('system_maintenance', 'System Maintenance', 'System maintenance', 'The system will be under maintenance'),
        ]

        # Get the web channel to set as default
        web_channel = NotificationChannel.objects.get(name='web')
        created_types = 0

        for name, display_name, title, message in types_data:
            notification_type, created = NotificationType.objects.get_or_create(
                name=name,
                defaults={
                    'title_template': title,
                    'message_template': message,
                    'is_active': True
                }
            )
            if created:
                notification_type.default_channels.add(web_channel)
                created_types += 1
                self.stdout.write(f'✓ Created notification type: {display_name}')
            else:
                self.stdout.write(f'  Notification type already exists: {display_name}')

        # Create some test conversations and messages for development
        self.create_test_data()

        self.stdout.write('\n' + '='*60)
        self.stdout.write(self.style.SUCCESS(
            f'✓ Notification system setup complete!\n'
            f'  - Created {created_channels} channels\n'
            f'  - Created {created_types} notification types\n'
            f'  - Created test conversations for development'
        ))
        self.stdout.write('='*60)

    def create_test_data(self):
        """Create test conversations and messages for development"""
        from ...models import Conversation, Message, ConversationMember
        import json

        # Create a test conversation
        conversation, created = Conversation.objects.get_or_create(
            id='550e8400-e29b-41d4-a716-446655440001',  # Fixed UUID for testing
            defaults={
                'participants': ['1', '2'],  # Test user IDs
                'conversation_type': 'general',
                'title': 'Test Conversation',
                'is_active': True
            }
        )

        if created:
            # Create conversation members
            for user_id in ['1', '2']:
                ConversationMember.objects.get_or_create(
                    conversation=conversation,
                    user_id=user_id,
                    defaults={'unread_count': 0}
                )

            # Create some test messages
            test_messages = [
                {'sender_id': '1', 'content': 'Hello! How are you doing?'},
                {'sender_id': '2', 'content': 'Hi there! I\'m doing great, thanks for asking. How about you?'},
                {'sender_id': '1', 'content': 'I\'m good too! Working on this new project. Want to collaborate?'},
                {'sender_id': '2', 'content': 'That sounds interesting! Tell me more about it.'},
            ]

            for msg_data in test_messages:
                Message.objects.create(
                    conversation=conversation,
                    sender_id=msg_data['sender_id'],
                    content=msg_data['content'],
                    message_type='text'
                )

            self.stdout.write('✓ Created test conversation with messages')

        # Create another test conversation with different users
        conversation2, created = Conversation.objects.get_or_create(
            id='550e8400-e29b-41d4-a716-446655440002',
            defaults={
                'participants': ['1', '3'],
                'conversation_type': 'job_inquiry',
                'title': 'Project Discussion',
                'job_id': 'job123',
                'is_active': True
            }
        )

        if created:
            # Create conversation members
            for user_id in ['1', '3']:
                ConversationMember.objects.get_or_create(
                    conversation=conversation2,
                    user_id=user_id,
                    defaults={'unread_count': 0}
                )

            # Create some job-related messages
            job_messages = [
                {'sender_id': '3', 'content': 'I\'m interested in your web development project.'},
                {'sender_id': '1', 'content': 'Great! What\'s your experience with React and Django?'},
                {'sender_id': '3', 'content': 'I have 5 years of experience with both technologies. I can show you some of my previous work.'},
            ]

            for msg_data in job_messages:
                Message.objects.create(
                    conversation=conversation2,
                    sender_id=msg_data['sender_id'],
                    content=msg_data['content'],
                    message_type='text'
                )

            self.stdout.write('✓ Created job inquiry conversation with messages')