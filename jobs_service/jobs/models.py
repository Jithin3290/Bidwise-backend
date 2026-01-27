# jobs/models.py
from django.db import models
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
import uuid


class JobCategory(models.Model):
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True, help_text="Icon class name")
    is_active = models.BooleanField(default=True)
    display_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name_plural = "Job Categories"
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class Skill(models.Model):
    name = models.CharField(max_length=100, unique=True)
    category = models.CharField(max_length=50, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Job(models.Model):
    JOB_STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('published', 'Published'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('paused', 'Paused'),
    ]

    JOB_TYPE_CHOICES = [
        ('fixed', 'Fixed Price'),
        ('hourly', 'Hourly'),
        ('milestone', 'Milestone Based'),
    ]

    EXPERIENCE_LEVEL_CHOICES = [
        ('entry', 'Entry Level'),
        ('intermediate', 'Intermediate'),
        ('expert', 'Expert'),
        ('any', 'Any Level'),
    ]

    DURATION_CHOICES = [
        ('less_than_week', 'Less than a week'),
        ('1_to_4_weeks', '1 to 4 weeks'),
        ('1_to_3_months', '1 to 3 months'),
        ('3_to_6_months', '3 to 6 months'),
        ('more_than_6_months', 'More than 6 months'),
    ]

    # Primary Information
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    client_id = models.CharField(max_length=100, help_text="Client ID from Users Service")
    title = models.CharField(max_length=200)
    description = models.TextField()
    category = models.ForeignKey(JobCategory, on_delete=models.SET_NULL, null=True, blank=True)
    skills = models.ManyToManyField(Skill, blank=True)

    # Job Configuration
    job_type = models.CharField(max_length=20, choices=JOB_TYPE_CHOICES)
    experience_level = models.CharField(max_length=20, choices=EXPERIENCE_LEVEL_CHOICES, default='any')
    estimated_duration = models.CharField(max_length=30, choices=DURATION_CHOICES, blank=True)

    # Budget Information
    budget_min = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], null=True,
                                     blank=True)
    budget_max = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)], null=True,
                                     blank=True)
    hourly_rate_min = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)], null=True,
                                          blank=True)
    hourly_rate_max = models.DecimalField(max_digits=8, decimal_places=2, validators=[MinValueValidator(0)], null=True,
                                          blank=True)
    currency = models.CharField(max_length=3, default='USD')

    # Project Details
    remote_allowed = models.BooleanField(default=True)
    location = models.CharField(max_length=200, blank=True)
    timezone_preference = models.CharField(max_length=50, blank=True)
    languages_required = models.JSONField(default=list, blank=True)

    # Status and Metadata
    status = models.CharField(max_length=20, choices=JOB_STATUS_CHOICES, default='draft')
    is_featured = models.BooleanField(default=False)
    is_urgent = models.BooleanField(default=False)
    deadline = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    published_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

    # Analytics
    views_count = models.PositiveIntegerField(default=0)
    applications_count = models.PositiveIntegerField(default=0)
    saves_count = models.PositiveIntegerField(default=0)

    # SEO and Search
    slug = models.SlugField(max_length=250, blank=True)
    tags = models.JSONField(default=list, blank=True)
    search_keywords = models.TextField(blank=True, help_text="Auto-generated for search")

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            models.Index(fields=['category', 'status']),
            models.Index(fields=['client_id', 'status']),
            models.Index(fields=['job_type', 'status']),
            models.Index(fields=['published_at']),
            models.Index(fields=['is_featured', 'is_urgent']),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_status_display()})"

    def clean(self):
        # Budget validation
        if self.job_type == 'fixed' or self.job_type == 'milestone':
            if not self.budget_min or not self.budget_max:
                raise ValidationError("Budget range is required for fixed/milestone jobs")
            if self.budget_max < self.budget_min:
                raise ValidationError("Maximum budget must be greater than minimum budget")

        elif self.job_type == 'hourly':
            if not self.hourly_rate_min or not self.hourly_rate_max:
                raise ValidationError("Hourly rate range is required for hourly jobs")
            if self.hourly_rate_max < self.hourly_rate_min:
                raise ValidationError("Maximum hourly rate must be greater than minimum")

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.title)[:250]

        # Generate search keywords
        self.search_keywords = f"{self.title} {self.description}".lower()

        super().save(*args, **kwargs)


class JobAttachment(models.Model):
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='job_attachments/%Y/%m/%d/')
    filename = models.CharField(max_length=255)
    file_size = models.PositiveIntegerField(default=0)  # Add default
    file_type = models.CharField(max_length=50, blank=True)
    description = models.CharField(max_length=500, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def save(self, *args, **kwargs):
        if self.file:
            if not self.filename:
                self.filename = self.file.name
            if not self.file_size:
                self.file_size = self.file.size
            if not self.file_type and '.' in self.file.name:
                self.file_type = self.file.name.split('.')[-1].lower()
        super().save(*args, **kwargs)


class JobMilestone(models.Model):
    """For milestone-based jobs"""
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='milestones')
    title = models.CharField(max_length=200)
    description = models.TextField()
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    due_date = models.DateTimeField(null=True, blank=True)
    order = models.PositiveIntegerField()
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['order']
        unique_together = ['job', 'order']

    def __str__(self):
        return f"{self.job.title} - Milestone {self.order}: {self.title}"


class JobView(models.Model):
    """Track job views for analytics"""
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='job_views')
    viewer_id = models.CharField(max_length=100, null=True, blank=True)  # User ID or anonymous
    ip_address = models.GenericIPAddressField()
    user_agent = models.TextField(blank=True)
    referrer = models.URLField(blank=True)
    viewed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=['job', 'viewed_at']),
            models.Index(fields=['viewer_id', 'viewed_at']),
        ]


class JobSave(models.Model):
    """Track saved jobs by users"""
    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name='job_saves')
    user_id = models.CharField(max_length=100)  # User ID from Users Service
    saved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['job', 'user_id']
        indexes = [
            models.Index(fields=['user_id', 'saved_at']),
        ]