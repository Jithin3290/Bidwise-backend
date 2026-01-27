# jobs/admin.py
from django.contrib import admin
from django.db import models
from django.utils.html import format_html
from django.urls import reverse
from django.db.models import Count
from .models import JobCategory, Skill, Job, JobAttachment, JobMilestone, JobView, JobSave


@admin.register(JobCategory)
class JobCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'jobs_count', 'is_active', 'display_order', 'created_at']
    list_filter = ['is_active', 'created_at']
    search_fields = ['name', 'description']
    list_editable = ['is_active', 'display_order']
    ordering = ['display_order', 'name']

    def jobs_count(self, obj):
        return obj.job_set.filter(status='published').count()

    jobs_count.short_description = 'Published Jobs'

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(
            jobs_count=Count('job', filter=models.Q(job__status='published'))
        )


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'jobs_count', 'is_active', 'created_at']
    list_filter = ['category', 'is_active', 'created_at']
    search_fields = ['name', 'category']
    list_editable = ['is_active']
    ordering = ['category', 'name']

    def jobs_count(self, obj):
        return obj.job_set.filter(status='published').count()

    jobs_count.short_description = 'Jobs Using Skill'


class JobAttachmentInline(admin.TabularInline):
    model = JobAttachment
    extra = 0
    readonly_fields = ['file_size', 'file_type', 'uploaded_at']
    fields = ['filename', 'file', 'description', 'file_size', 'file_type', 'uploaded_at']


class JobMilestoneInline(admin.TabularInline):
    model = JobMilestone
    extra = 0
    fields = ['order', 'title', 'description', 'amount', 'due_date', 'is_completed']
    ordering = ['order']


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = [
        'title', 'client_id_display', 'category', 'job_type', 'status',
        'budget_display', 'views_count', 'applications_count', 'created_at'
    ]
    list_filter = [
        'status', 'job_type', 'experience_level', 'category',
        'remote_allowed', 'is_featured', 'is_urgent', 'created_at'
    ]
    search_fields = ['title', 'description', 'client_id', 'search_keywords']
    readonly_fields = [
        'id', 'client_id', 'views_count', 'applications_count', 'saves_count',
        'created_at', 'updated_at', 'published_at', 'closed_at', 'slug'
    ]
    filter_horizontal = ['skills']
    date_hierarchy = 'created_at'
    ordering = ['-created_at']
    inlines = [JobAttachmentInline, JobMilestoneInline]

    fieldsets = (
        ('Basic Information', {
            'fields': ('id', 'client_id', 'title', 'description', 'category', 'skills')
        }),
        ('Job Configuration', {
            'fields': ('job_type', 'experience_level', 'estimated_duration')
        }),
        ('Budget Information', {
            'fields': ('budget_min', 'budget_max', 'hourly_rate_min', 'hourly_rate_max', 'currency')
        }),
        ('Location & Remote', {
            'fields': ('remote_allowed', 'location', 'timezone_preference', 'languages_required')
        }),
        ('Status & Features', {
            'fields': ('status', 'is_featured', 'is_urgent', 'deadline')
        }),
        ('SEO & Search', {
            'fields': ('slug', 'tags', 'search_keywords'),
            'classes': ('collapse',)
        }),
        ('Analytics', {
            'fields': ('views_count', 'applications_count', 'saves_count'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at', 'published_at', 'closed_at'),
            'classes': ('collapse',)
        }),
    )

    def client_id_display(self, obj):
        return format_html(
            '<a href="#" title="Client ID: {}">{}</a>',
            obj.client_id,
            obj.client_id[:8] + '...' if len(obj.client_id) > 8 else obj.client_id
        )

    client_id_display.short_description = 'Client'

    def budget_display(self, obj):
        if obj.job_type == 'hourly':
            if obj.hourly_rate_min and obj.hourly_rate_max:
                return f"${obj.hourly_rate_min}-${obj.hourly_rate_max}/hr"
        else:
            if obj.budget_min and obj.budget_max:
                return f"${obj.budget_min:,.0f}-${obj.budget_max:,.0f}"
        return "Not specified"

    budget_display.short_description = 'Budget'

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('category').prefetch_related('skills')

    actions = ['mark_as_featured', 'mark_as_urgent', 'publish_jobs', 'pause_jobs']

    def mark_as_featured(self, request, queryset):
        updated = queryset.update(is_featured=True)
        self.message_user(request, f'{updated} jobs marked as featured.')

    mark_as_featured.short_description = "Mark selected jobs as featured"

    def mark_as_urgent(self, request, queryset):
        updated = queryset.update(is_urgent=True)
        self.message_user(request, f'{updated} jobs marked as urgent.')

    mark_as_urgent.short_description = "Mark selected jobs as urgent"

    def publish_jobs(self, request, queryset):
        from django.utils import timezone
        updated = queryset.filter(status='draft').update(
            status='published',
            published_at=timezone.now()
        )
        self.message_user(request, f'{updated} jobs published.')

    publish_jobs.short_description = "Publish selected draft jobs"

    def pause_jobs(self, request, queryset):
        updated = queryset.filter(status='published').update(status='paused')
        self.message_user(request, f'{updated} jobs paused.')

    pause_jobs.short_description = "Pause selected published jobs"


@admin.register(JobAttachment)
class JobAttachmentAdmin(admin.ModelAdmin):
    list_display = ['filename', 'job_title', 'file_size_display', 'file_type', 'uploaded_at']
    list_filter = ['file_type', 'uploaded_at']
    search_fields = ['filename', 'job__title', 'description']
    readonly_fields = ['file_size', 'file_type', 'uploaded_at']
    date_hierarchy = 'uploaded_at'

    def job_title(self, obj):
        return obj.job.title

    job_title.short_description = 'Job'

    def file_size_display(self, obj):
        if obj.file_size < 1024:
            return f"{obj.file_size} B"
        elif obj.file_size < 1024 * 1024:
            return f"{obj.file_size / 1024:.1f} KB"
        else:
            return f"{obj.file_size / (1024 * 1024):.1f} MB"

    file_size_display.short_description = 'Size'


@admin.register(JobMilestone)
class JobMilestoneAdmin(admin.ModelAdmin):
    list_display = ['title', 'job_title', 'order', 'amount', 'due_date', 'is_completed']
    list_filter = ['is_completed', 'due_date', 'created_at']
    search_fields = ['title', 'description', 'job__title']
    list_editable = ['is_completed']
    ordering = ['job', 'order']

    def job_title(self, obj):
        return obj.job.title

    job_title.short_description = 'Job'


@admin.register(JobView)
class JobViewAdmin(admin.ModelAdmin):
    list_display = ['job_title', 'viewer_id', 'ip_address', 'viewed_at']
    list_filter = ['viewed_at']
    search_fields = ['job__title', 'viewer_id', 'ip_address']
    readonly_fields = ['job', 'viewer_id', 'ip_address', 'user_agent', 'referrer', 'viewed_at']
    date_hierarchy = 'viewed_at'

    def job_title(self, obj):
        return obj.job.title

    job_title.short_description = 'Job'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(JobSave)
class JobSaveAdmin(admin.ModelAdmin):
    list_display = ['job_title', 'user_id', 'saved_at']
    list_filter = ['saved_at']
    search_fields = ['job__title', 'user_id']
    readonly_fields = ['job', 'user_id', 'saved_at']
    date_hierarchy = 'saved_at'

    def job_title(self, obj):
        return obj.job.title

    job_title.short_description = 'Job'


# Admin site customization
admin.site.site_header = 'Jobs Service Administration'
admin.site.site_title = 'Jobs Service Admin'
admin.site.index_title = 'Welcome to Jobs Service Administration'


# Custom admin views for analytics
class JobsAnalyticsAdmin(admin.ModelAdmin):
    """Custom admin view for job analytics"""

    def changelist_view(self, request, extra_context=None):
        from django.db.models import Count, Avg, Sum
        from django.utils import timezone
        from datetime import timedelta

        # Calculate analytics data
        now = timezone.now()
        last_30_days = now - timedelta(days=30)

        analytics_data = {
            'total_jobs': Job.objects.count(),
            'published_jobs': Job.objects.filter(status='published').count(),
            'jobs_last_30_days': Job.objects.filter(created_at__gte=last_30_days).count(),
            'total_views': Job.objects.aggregate(Sum('views_count'))['views_count__sum'] or 0,
            'avg_budget': Job.objects.filter(budget_max__isnull=False).aggregate(Avg('budget_max'))[
                              'budget_max__avg'] or 0,
            'top_categories': JobCategory.objects.annotate(
                job_count=Count('job', filter=models.Q(job__status='published'))
            ).order_by('-job_count')[:5],
            'top_skills': Skill.objects.annotate(
                job_count=Count('job', filter=models.Q(job__status='published'))
            ).order_by('-job_count')[:10],
        }

        extra_context = extra_context or {}
        extra_context['analytics_data'] = analytics_data

        return super().changelist_view(request, extra_context=extra_context)