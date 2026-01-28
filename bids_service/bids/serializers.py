# bids/serializers.py
from rest_framework import serializers
from decimal import Decimal
from django.conf import settings
from .models import (
    Bid, BidMilestone, BidAttachment, BidMessage,
    FreelancerBidProfile, JobBidSummary, Payment
)
from .utils import validate_positive,validate_proposal_length
# ---------------------------
# Milestone Serializer
# ---------------------------
class BidMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = BidMilestone
        fields = [
            'id', 'title', 'description', 'amount',
            'estimated_delivery_days', 'order', 'is_completed',
            'completed_at', 'approved_by_client', 'approved_at'
        ]
        read_only_fields = ['id', 'is_completed', 'completed_at', 'approved_by_client', 'approved_at']

    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    estimated_delivery_days = serializers.IntegerField()

    def validate_amount(self, value):
        return validate_positive(value, "Milestone amount")

    def validate_estimated_delivery_days(self, value):
        return validate_positive(value, "Estimated delivery days")

# ---------------------------
# Attachment Serializer
# ---------------------------
class BidAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()
    file_size_formatted = serializers.SerializerMethodField()

    class Meta:
        model = BidAttachment
        fields = [
            'id', 'file', 'file_url', 'filename', 'file_type',
            'file_size', 'file_size_formatted', 'description', 'uploaded_at'
        ]
        read_only_fields = ['id', 'file_size', 'uploaded_at']

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            return request.build_absolute_uri(obj.file.url) if request else obj.file.url
        return None

    def get_file_size_formatted(self, obj):
        size = obj.file_size or 0
        for unit in ['B', 'KB', 'MB', 'GB']:
            if size < 1024.0:
                return f"{size:.1f} {unit}"
            size /= 1024.0
        return f"{size:.1f} TB"

# ---------------------------
# Bid Message Serializer
# ---------------------------
class BidMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = BidMessage
        fields = ['id', 'sender_id', 'sender_type', 'message', 'is_read', 'read_at', 'created_at']
        read_only_fields = ['id', 'sender_id', 'sender_type', 'is_read', 'read_at', 'created_at']

# ---------------------------
# Freelancer Profile Serializer
# ---------------------------
class FreelancerBidProfileSerializer(serializers.ModelSerializer):
    full_name = serializers.SerializerMethodField()
    success_rate = serializers.SerializerMethodField()

    class Meta:
        model = FreelancerBidProfile
        fields = [
            'freelancer_id', 'username', 'first_name', 'last_name', 'full_name',
            'profile_picture_url', 'location', 'title', 'bio', 'skills',
            'hourly_rate', 'total_bids', 'accepted_bids', 'completed_projects',
            'average_rating', 'acceptance_rate', 'completion_rate',
            'on_time_delivery_rate', 'success_rate', 'is_verified', 'is_premium'
        ]

    def get_full_name(self, obj):
        return f"{obj.first_name} {obj.last_name}".strip()

    def get_success_rate(self, obj):
        if obj.total_bids > 0:
            acceptance = Decimal(str(obj.acceptance_rate))
            completion = Decimal(str(obj.completion_rate))
            return round((acceptance * Decimal('0.4') + completion * Decimal('0.6')), 2)
        return Decimal('0.00')

# ---------------------------
# Bid Create Serializer
# ---------------------------
class BidCreateSerializer(serializers.ModelSerializer):
    milestones = BidMilestoneSerializer(many=True, required=False)

    class Meta:
        model = Bid
        fields = [
            'job_id', 'bid_type', 'amount', 'hourly_rate', 'estimated_hours',
            'currency', 'proposal', 'estimated_delivery', 'questions', 'milestones'
        ]

    def validate_proposal(self, value):
        return validate_proposal_length(value)

    def validate_estimated_delivery(self, value):
        return validate_positive(value, "Estimated delivery")

    def validate(self, data):
        bid_type = data.get('bid_type')
        amount = data.get('amount')
        hourly_rate = data.get('hourly_rate')
        estimated_hours = data.get('estimated_hours')
        milestones = data.get('milestones', [])

        if bid_type == 'fixed':
            validate_positive(amount, "Amount")
        elif bid_type == 'hourly':
            validate_positive(hourly_rate, "Hourly rate")
            validate_positive(estimated_hours, "Estimated hours")
        elif bid_type == 'milestone':
            if not milestones:
                raise serializers.ValidationError("At least one milestone is required for milestone bids")
            max_milestones = getattr(settings, 'MAX_MILESTONES_PER_BID', 10)
            if len(milestones) > max_milestones:
                raise serializers.ValidationError(f"Cannot have more than {max_milestones} milestones")
            total_milestone_amount = sum(Decimal(str(m.get('amount', 0))) for m in milestones)
            if amount and abs(total_milestone_amount - Decimal(str(amount))) > Decimal('0.01'):
                raise serializers.ValidationError("Total milestone amount must equal bid amount")
        return data

    def create(self, validated_data):
        milestones_data = validated_data.pop('milestones', [])
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['freelancer_id'] = request.user.user_id
        bid = Bid.objects.create(**validated_data)
        for milestone in milestones_data:
            BidMilestone.objects.create(bid=bid, **milestone)
        return bid

# ---------------------------
# Bid Update Serializer
# ---------------------------
class BidUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bid
        fields = ['proposal', 'estimated_delivery', 'questions', 'total_amount', 'hourly_rate', 'estimated_hours']

    def validate(self, data):
        if self.instance and self.instance.status != 'pending':
            raise serializers.ValidationError("Can only update pending bids")
        return data

# ---------------------------
# Bid List Serializer
# ---------------------------
class BidListSerializer(serializers.ModelSerializer):
    freelancer_profile = FreelancerBidProfileSerializer(read_only=True)
    total_amount = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    milestones_count = serializers.SerializerMethodField()
    attachments_count = serializers.SerializerMethodField()

    class Meta:
        model = Bid
        fields = [
            'id', 'job_id', 'freelancer_id', 'bid_type', 'amount',
            'hourly_rate', 'estimated_hours', 'total_amount', 'currency',
            'proposal', 'estimated_delivery', 'status', 'is_featured',
            'created_at', 'expires_at', 'is_expired', 'client_viewed_at',
            'views_count', 'milestones_count', 'attachments_count',
            'freelancer_profile'
        ]

    def get_milestones_count(self, obj):
        return obj.milestones.count()

    def get_attachments_count(self, obj):
        return obj.attachments.count()

# ---------------------------
# Bid Detail Serializer
# ---------------------------
class BidDetailSerializer(serializers.ModelSerializer):
    freelancer_profile = FreelancerBidProfileSerializer(read_only=True)
    milestones = BidMilestoneSerializer(many=True, read_only=True)
    attachments = BidAttachmentSerializer(many=True, read_only=True)
    messages = BidMessageSerializer(many=True, read_only=True)
    total_amount = serializers.ReadOnlyField()
    is_expired = serializers.ReadOnlyField()
    can_be_edited = serializers.SerializerMethodField()
    can_be_withdrawn = serializers.SerializerMethodField()

    class Meta:
        model = Bid
        fields = [
            'id', 'job_id', 'freelancer_id', 'bid_type', 'amount',
            'hourly_rate', 'estimated_hours', 'total_amount', 'currency',
            'proposal', 'estimated_delivery', 'questions', 'status',
            'is_featured', 'created_at', 'updated_at', 'expires_at',
            'is_expired', 'accepted_at', 'rejected_at', 'client_viewed_at',
            'client_rating', 'client_feedback', 'views_count',
            'can_be_edited', 'can_be_withdrawn', 'freelancer_profile',
            'milestones', 'attachments', 'messages'
        ]

    def get_can_be_edited(self, obj):
        return obj.status == 'pending' and not obj.is_expired

    def get_can_be_withdrawn(self, obj):
        return obj.status == 'pending'

# ---------------------------
# Bid Status Update Serializer
# ---------------------------
class BidStatusUpdateSerializer(serializers.ModelSerializer):
    feedback = serializers.CharField(required=False, allow_blank=True)

    class Meta:
        model = Bid
        fields = ['status', 'feedback']

    def validate_status(self, value):
        if self.instance:
            allowed_transitions = {
                'pending': ['accepted', 'rejected'],
                'accepted': [],
                'rejected': [],
                'withdrawn': [],
                'expired': [],
            }
            if value not in allowed_transitions.get(self.instance.status, []):
                raise serializers.ValidationError(f"Cannot change status from {self.instance.status} to {value}")
        return value

    def update(self, instance, validated_data):
        status = validated_data.get('status')
        feedback = validated_data.get('feedback', '')
        if status == 'accepted':
            instance.accept()
        elif status == 'rejected':
            instance.reject(feedback)
        return instance

# ---------------------------
# Job Bid Summary Serializer
# ---------------------------
class JobBidSummarySerializer(serializers.ModelSerializer):
    acceptance_rate = serializers.SerializerMethodField()

    class Meta:
        model = JobBidSummary
        fields = [
            'job_id', 'total_bids', 'pending_bids', 'accepted_bids',
            'rejected_bids', 'lowest_bid', 'highest_bid', 'average_bid',
            'average_delivery_time', 'fastest_delivery', 'acceptance_rate',
            'popular_skills', 'last_updated'
        ]

    def get_acceptance_rate(self, obj):
        if obj.total_bids > 0:
            return round((Decimal(obj.accepted_bids) / Decimal(obj.total_bids)) * Decimal('100'), 2)
        return Decimal('0.00')

# ---------------------------
# Bid Statistics Serializer
# ---------------------------
class BidStatsSerializer(serializers.Serializer):
    total_bids = serializers.IntegerField()
    pending_bids = serializers.IntegerField()
    accepted_bids = serializers.IntegerField()
    rejected_bids = serializers.IntegerField()
    withdrawn_bids = serializers.IntegerField()
    acceptance_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    average_bid_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    total_potential_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    recent_activity = serializers.ListField()

# ---------------------------
# Freelancer Dashboard Serializer
# ---------------------------
class FreelancerDashboardSerializer(serializers.Serializer):
    total_bids = serializers.IntegerField()
    pending_bids = serializers.IntegerField()
    accepted_bids = serializers.IntegerField()
    acceptance_rate = serializers.DecimalField(max_digits=5, decimal_places=2)
    total_potential_earnings = serializers.DecimalField(max_digits=12, decimal_places=2)
    average_bid_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    recent_bids = BidListSerializer(many=True)
    profile_views = serializers.IntegerField()
    response_rate = serializers.DecimalField(max_digits=5, decimal_places=2)

# ---------------------------
# Client Bid Management Serializer
# ---------------------------
class ClientBidManagementSerializer(serializers.Serializer):
    job_id = serializers.CharField()
    job_title = serializers.CharField()
    total_bids = serializers.IntegerField()
    new_bids = serializers.IntegerField()
    quality_score = serializers.DecimalField(max_digits=3, decimal_places=1)
    average_bid = serializers.DecimalField(max_digits=12, decimal_places=2)
    top_bids = BidListSerializer(many=True)


class PaymentSerializer(serializers.ModelSerializer):
    """Serializer for Payment model"""

    class Meta:
        model = Payment
        fields = [
            'id', 'bid', 'razorpay_order_id', 'razorpay_payment_id',
            'amount', 'currency', 'payment_method', 'status',
            'client_id', 'freelancer_id', 'description', 'receipt_number',
            'created_at', 'updated_at', 'completed_at'
        ]
        read_only_fields = [
            'id', 'razorpay_order_id', 'receipt_number',
            'created_at', 'updated_at', 'completed_at'
        ]


class CreatePaymentOrderSerializer(serializers.Serializer):
    """Serializer for creating payment order"""

    bid_id = serializers.UUIDField()

    def validate_bid_id(self, value):
        """Validate bid exists and is accepted"""
        try:
            bid = Bid.objects.get(id=value)

            if bid.status != 'accepted':
                raise serializers.ValidationError("Can only make payment for accepted bids")

            # Check if payment already exists
            existing_payment = Payment.objects.filter(
                bid=bid,
                status__in=['completed', 'processing']
            ).exists()

            if existing_payment:
                raise serializers.ValidationError("Payment already exists for this bid")

            return value

        except Bid.DoesNotExist:
            raise serializers.ValidationError("Bid not found")


class VerifyPaymentSerializer(serializers.Serializer):
    """Serializer for verifying payment"""

    razorpay_order_id = serializers.CharField(max_length=100)
    razorpay_payment_id = serializers.CharField(max_length=100)
    razorpay_signature = serializers.CharField(max_length=255)
    payment_id = serializers.UUIDField()


class BidListSerializer(serializers.ModelSerializer):
    """Serializer for listing bids with freelancer details"""

    freelancer_profile = serializers.SerializerMethodField()
    job_title = serializers.CharField(read_only=True, required=False)
    job_budget = serializers.CharField(read_only=True, required=False)
    has_payment = serializers.SerializerMethodField()
    payment_status = serializers.SerializerMethodField()

    class Meta:
        model = Bid
        fields = [
            'id', 'job_id', 'job_title', 'job_budget', 'freelancer_id',
            'bid_type', 'amount', 'hourly_rate', 'estimated_hours',
            'total_amount', 'currency', 'proposal', 'estimated_delivery',
            'status', 'created_at', 'updated_at', 'accepted_at',
            'freelancer_profile', 'client_viewed_at',
            'has_payment', 'payment_status'
        ]

    def get_freelancer_profile(self, obj):
        if hasattr(obj, 'freelancer_profile') and obj.freelancer_profile:
            return {
                'user_id': obj.freelancer_profile.freelancer_id,
                'username': obj.freelancer_profile.username,
                'first_name': obj.freelancer_profile.first_name,
                'last_name': obj.freelancer_profile.last_name,
                'profile_picture_url': obj.freelancer_profile.profile_picture_url,
                'title': obj.freelancer_profile.title,
                'location': obj.freelancer_profile.location,
                'average_rating': float(obj.freelancer_profile.average_rating or 0),
                'total_bids': obj.freelancer_profile.total_bids,
                'completed_projects': obj.freelancer_profile.completed_projects,
                'acceptance_rate': float(obj.freelancer_profile.acceptance_rate or 0),
                'is_verified': obj.freelancer_profile.is_verified,
            }
        return None

    def get_has_payment(self, obj):
        """Check if bid has any completed payment"""
        return obj.payments.filter(status='completed').exists()

    def get_payment_status(self, obj):
        """Get payment status"""
        completed_payment = obj.payments.filter(status='completed').first()
        if completed_payment:
            return 'completed'

        pending_payment = obj.payments.filter(status__in=['pending', 'processing']).first()
        if pending_payment:
            return 'processing'

        return 'not_started'


class FreelancerAcceptedBidSerializer(serializers.ModelSerializer):
    """Serializer for freelancer's accepted bids"""

    job_title = serializers.CharField(read_only=True, required=False)
    job_description = serializers.CharField(read_only=True, required=False)
    job_budget = serializers.CharField(read_only=True, required=False)
    client_name = serializers.CharField(read_only=True, required=False)
    client_email = serializers.EmailField(read_only=True, required=False)
    client_location = serializers.CharField(read_only=True, required=False)
    has_payment = serializers.SerializerMethodField()
    payment_details = serializers.SerializerMethodField()

    class Meta:
        model = Bid
        fields = [
            'id', 'job_id', 'job_title', 'job_description', 'job_budget',
            'client_name', 'client_email', 'client_location',
            'bid_type', 'amount', 'hourly_rate', 'estimated_hours',
            'total_amount', 'currency', 'proposal', 'estimated_delivery',
            'status', 'created_at', 'updated_at', 'accepted_at',
             'has_payment', 'payment_details'
        ]

    def get_has_payment(self, obj):
        """Check if bid has completed payment"""
        return obj.payments.filter(status='completed').exists()

    def get_payment_details(self, obj):
        """Get payment details if exists"""
        completed_payment = obj.payments.filter(status='completed').first()
        if completed_payment:
            return {
                'payment_id': str(completed_payment.id),
                'amount': float(completed_payment.amount),
                'currency': completed_payment.currency,
                'receipt_number': completed_payment.receipt_number,
                'payment_method': completed_payment.payment_method,
                'completed_at': completed_payment.completed_at,
                'created_at': completed_payment.created_at
            }
        return None

