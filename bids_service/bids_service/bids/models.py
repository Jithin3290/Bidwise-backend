# bids/models.py
import uuid
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.utils import timezone
from decimal import Decimal


class Bid(models.Model):
    """Main bid/application model"""

    BID_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('accepted', 'Accepted'),
        ('rejected', 'Rejected'),
        ('withdrawn', 'Withdrawn'),
        ('expired', 'Expired'),
    ]

    BID_TYPE_CHOICES = [
        ('fixed', 'Fixed Price'),
        ('hourly', 'Hourly Rate'),
        ('milestone', 'Milestone Based'),
    ]

    # Primary identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_id = models.CharField(max_length=100, help_text="Job ID from Jobs Service")
    freelancer_id = models.CharField(max_length=100, help_text="Freelancer ID from Users Service")

    # Bid details
    bid_type = models.CharField(max_length=20, choices=BID_TYPE_CHOICES)
    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
        null=True,
        blank=True
    )
    hourly_rate = models.DecimalField(
        max_digits=8,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('1.00'))],
        null=True,
        blank=True
    )
    estimated_hours = models.PositiveIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, default='USD')

    # Proposal and timeline
    proposal = models.TextField(help_text="Freelancer's proposal/cover letter")
    estimated_delivery = models.PositiveIntegerField(
        help_text="Estimated delivery in days"
    )
    questions = models.JSONField(
        default=list,
        blank=True,
        help_text="Freelancer's questions to client"
    )

    # Status and metadata
    status = models.CharField(max_length=20, choices=BID_STATUS_CHOICES, default='pending')
    is_featured = models.BooleanField(default=False)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    rejected_at = models.DateTimeField(null=True, blank=True)

    # Client interaction
    client_viewed_at = models.DateTimeField(null=True, blank=True)
    client_rating = models.PositiveIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    client_feedback = models.TextField(blank=True)

    # Analytics
    views_count = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'bids'
        unique_together = ['job_id', 'freelancer_id']
        indexes = [
            models.Index(fields=['job_id', 'status']),
            models.Index(fields=['freelancer_id', 'status']),
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['created_at']),
            models.Index(fields=['expires_at']),
        ]
        ordering = ['-created_at']

    def __str__(self):
        return f"Bid {self.id} - Job {self.job_id} by Freelancer {self.freelancer_id}"

    def clean(self):
        """Validate bid data based on type"""
        if self.bid_type == 'fixed' and not self.amount:
            raise ValidationError("Amount is required for fixed price bids")

        if self.bid_type == 'hourly':
            if not self.hourly_rate:
                raise ValidationError("Hourly rate is required for hourly bids")
            if not self.estimated_hours:
                raise ValidationError("Estimated hours required for hourly bids")

        if self.bid_type == 'milestone' and not self.amount:
            raise ValidationError("Total amount is required for milestone bids")

    def save(self, *args, **kwargs):
        # Set expiry date if not set
        if not self.expires_at:
            from django.conf import settings
            expiry_days = getattr(settings, 'BID_EXPIRY_DAYS', 30)
            self.expires_at = timezone.now() + timezone.timedelta(days=expiry_days)

        # Calculate total for hourly bids
        if self.bid_type == 'hourly' and self.hourly_rate and self.estimated_hours:
            self.amount = self.hourly_rate * self.estimated_hours

        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        """Check if bid has expired"""
        return self.expires_at and timezone.now() > self.expires_at

    @property
    def total_amount(self):
        """Get total amount for the bid"""
        if self.bid_type == 'hourly' and self.hourly_rate and self.estimated_hours:
            return self.hourly_rate * self.estimated_hours
        return self.amount or Decimal('0.00')

    def accept(self):
        """Accept the bid"""
        self.status = 'accepted'
        self.accepted_at = timezone.now()
        self.save()

    def reject(self, feedback=None):
        """Reject the bid"""
        self.status = 'rejected'
        self.rejected_at = timezone.now()
        if feedback:
            self.client_feedback = feedback
        self.save()

    def withdraw(self):
        """Withdraw the bid (freelancer action)"""
        if self.status == 'pending':
            self.status = 'withdrawn'
            self.save()
        else:
            raise ValidationError("Can only withdraw pending bids")


class BidMilestone(models.Model):
    """Milestones for milestone-based bids"""

    bid = models.ForeignKey(Bid, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=200)
    description = models.TextField()
    amount = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))]
    )
    estimated_delivery_days = models.PositiveIntegerField()
    order = models.PositiveIntegerField()

    # Status tracking
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    approved_by_client = models.BooleanField(default=False)
    approved_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bid_milestones'
        unique_together = ['bid', 'order']
        ordering = ['order']

    def __str__(self):
        return f"Milestone {self.order}: {self.title} - ${self.amount}"


class BidAttachment(models.Model):
    """File attachments for bids (portfolio, documents, etc.)"""

    ATTACHMENT_TYPE_CHOICES = [
        ('portfolio', 'Portfolio Item'),
        ('document', 'Document'),
        ('certificate', 'Certificate'),
        ('reference', 'Reference'),
        ('other', 'Other'),
    ]

    bid = models.ForeignKey(Bid, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='bid_attachments/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    file_type = models.CharField(max_length=20, choices=ATTACHMENT_TYPE_CHOICES, default='document')
    file_size = models.PositiveIntegerField(default=0)
    description = models.CharField(max_length=500, blank=True)

    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bid_attachments'

    def __str__(self):
        return f"Attachment: {self.filename}"

    def save(self, *args, **kwargs):
        if self.file:
            if not self.filename:
                self.filename = self.file.name
            if not self.file_size:
                self.file_size = self.file.size
        super().save(*args, **kwargs)


class BidMessage(models.Model):
    """Messages between client and freelancer regarding a bid"""

    bid = models.ForeignKey(Bid, on_delete=models.CASCADE, related_name='messages')
    sender_id = models.CharField(max_length=100, help_text="User ID from Users Service")
    sender_type = models.CharField(max_length=20, choices=[('client', 'Client'), ('freelancer', 'Freelancer')])
    message = models.TextField()

    # Message metadata
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bid_messages'
        ordering = ['created_at']

    def __str__(self):
        return f"Message from {self.sender_type} at {self.created_at}"

    def mark_as_read(self):
        """Mark message as read"""
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=['is_read', 'read_at'])


class BidView(models.Model):
    """Track bid views by clients"""

    bid = models.ForeignKey(Bid, on_delete=models.CASCADE, related_name='bid_views')
    viewer_id = models.CharField(max_length=100, help_text="Client ID from Users Service")
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)

    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'bid_views'
        indexes = [
            models.Index(fields=['bid', 'viewed_at']),
            models.Index(fields=['viewer_id', 'viewed_at']),
        ]

    def __str__(self):
        return f"Bid {self.bid.id} viewed by {self.viewer_id}"


class BidStatistics(models.Model):
    """Aggregate statistics for bids (for analytics)"""

    # Date for statistics
    date = models.DateField(unique=True)

    # Daily totals
    total_bids_created = models.PositiveIntegerField(default=0)
    total_bids_accepted = models.PositiveIntegerField(default=0)
    total_bids_rejected = models.PositiveIntegerField(default=0)
    total_bids_withdrawn = models.PositiveIntegerField(default=0)

    # Average values
    average_bid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    average_hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    average_delivery_time = models.FloatField(default=0)  # in days

    # Top categories by bid count
    top_categories = models.JSONField(default=list, blank=True)
    top_skills = models.JSONField(default=list, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'bid_statistics'
        ordering = ['-date']

    def __str__(self):
        return f"Bid Statistics for {self.date}"


class FreelancerBidProfile(models.Model):
    """Cached freelancer profile data for bid display"""

    freelancer_id = models.CharField(max_length=100, unique=True)

    # Basic info (cached from Users Service)
    username = models.CharField(max_length=150)
    first_name = models.CharField(max_length=150)
    last_name = models.CharField(max_length=150)
    profile_picture_url = models.URLField(blank=True, null=True)
    location = models.CharField(max_length=200, blank=True)
    timezone = models.CharField(max_length=50, blank=True)

    # Professional info
    title = models.CharField(max_length=200, blank=True)
    bio = models.TextField(blank=True)
    skills = models.JSONField(default=list, blank=True)
    hourly_rate = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # Statistics
    total_bids = models.PositiveIntegerField(default=0)
    accepted_bids = models.PositiveIntegerField(default=0)
    completed_projects = models.PositiveIntegerField(default=0)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    total_earnings = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Success metrics
    acceptance_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # percentage
    completion_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # percentage
    on_time_delivery_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)  # percentage

    # Verification status
    is_verified = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)

    # Cache metadata
    last_updated = models.DateTimeField(auto_now=True)
    cache_expires_at = models.DateTimeField()

    class Meta:
        db_table = 'freelancer_bid_profiles'

    def __str__(self):
        return f"Bid Profile for {self.username}"

    def is_cache_valid(self):
        """Check if cached data is still valid"""
        return timezone.now() < self.cache_expires_at

    def update_statistics(self):
        """Update freelancer statistics based on bids"""
        bids = Bid.objects.filter(freelancer_id=self.freelancer_id)

        self.total_bids = bids.count()
        self.accepted_bids = bids.filter(status='accepted').count()

        if self.total_bids > 0:
            self.acceptance_rate = (self.accepted_bids / self.total_bids) * 100

        # Update cache expiry
        self.cache_expires_at = timezone.now() + timezone.timedelta(hours=6)
        self.save()


class JobBidSummary(models.Model):
    """Cached summary of bids for each job"""

    job_id = models.CharField(max_length=100, unique=True)

    # Bid counts
    total_bids = models.PositiveIntegerField(default=0)
    pending_bids = models.PositiveIntegerField(default=0)
    accepted_bids = models.PositiveIntegerField(default=0)
    rejected_bids = models.PositiveIntegerField(default=0)

    # Bid amount statistics
    lowest_bid = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    highest_bid = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    average_bid = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    # Time statistics
    average_delivery_time = models.FloatField(null=True, blank=True)  # in days
    fastest_delivery = models.PositiveIntegerField(null=True, blank=True)  # in days

    # Top freelancer skills for this job
    popular_skills = models.JSONField(default=list, blank=True)

    # Cache metadata
    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'job_bid_summaries'

    def __str__(self):
        return f"Bid Summary for Job {self.job_id}"

    def refresh_summary(self):
        """Refresh the summary based on current bids"""
        bids = Bid.objects.filter(job_id=self.job_id)

        self.total_bids = bids.count()
        self.pending_bids = bids.filter(status='pending').count()
        self.accepted_bids = bids.filter(status='accepted').count()
        self.rejected_bids = bids.filter(status='rejected').count()

        if bids.exists():
            amounts = bids.filter(amount__isnull=False).values_list('amount', flat=True)
            if amounts:
                self.lowest_bid = min(amounts)
                self.highest_bid = max(amounts)
                self.average_bid = sum(amounts) / len(amounts)

            # Calculate average delivery time
            delivery_times = bids.values_list('estimated_delivery', flat=True)
            if delivery_times:
                self.average_delivery_time = sum(delivery_times) / len(delivery_times)
                self.fastest_delivery = min(delivery_times)

        self.save()


class Payment(models.Model):
    """Payment model for bid payments"""

    PAYMENT_STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('razorpay', 'Razorpay'),
        ('card', 'Card'),
        ('upi', 'UPI'),
        ('netbanking', 'Net Banking'),
        ('wallet', 'Wallet'),
    ]

    # Primary identifiers
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    bid = models.ForeignKey(Bid, on_delete=models.PROTECT, related_name='payments')

    # Razorpay details
    razorpay_order_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    razorpay_payment_id = models.CharField(max_length=100, unique=True, null=True, blank=True)
    razorpay_signature = models.CharField(max_length=255, null=True, blank=True)

    # Payment details
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default='INR')
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES, default='razorpay')
    status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default='pending')

    # User details
    client_id = models.CharField(max_length=100, help_text="Client ID from Users Service")
    freelancer_id = models.CharField(max_length=100, help_text="Freelancer ID from Users Service")

    # Additional details
    description = models.TextField(blank=True)
    receipt_number = models.CharField(max_length=100, unique=True)
    notes = models.JSONField(default=dict, blank=True)

    # Metadata
    payment_data = models.JSONField(default=dict, blank=True, help_text="Raw payment gateway response")
    error_message = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    failed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'payments'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['bid', 'status']),
            models.Index(fields=['client_id', 'status']),
            models.Index(fields=['razorpay_payment_id']),
            models.Index(fields=['razorpay_order_id']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Payment {self.id} - {self.amount} {self.currency} - {self.status}"

    def generate_receipt_number(self):
        """Generate unique receipt number"""
        import random
        import string
        timestamp = timezone.now().strftime('%Y%m%d%H%M%S')
        random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        return f"PAY-{timestamp}-{random_str}"

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = self.generate_receipt_number()
        super().save(*args, **kwargs)

    def mark_completed(self):
        """Mark payment as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save(update_fields=['status', 'completed_at', 'updated_at'])

    def mark_failed(self, error_message=''):
        """Mark payment as failed"""
        self.status = 'failed'
        self.failed_at = timezone.now()
        self.error_message = error_message
        self.save(update_fields=['status', 'failed_at', 'error_message', 'updated_at'])

