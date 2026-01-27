# jobs/serializers.py
from rest_framework import serializers
from django.utils import timezone
from .models import Job, JobCategory, Skill, JobAttachment, JobMilestone, JobSave




class SkillSerializer(serializers.ModelSerializer):
    class Meta:
        model = Skill
        fields = ['id', 'name', 'category']


class JobCategorySerializer(serializers.ModelSerializer):
    jobs_count = serializers.SerializerMethodField()

    class Meta:
        model = JobCategory
        fields = ['id', 'name', 'description', 'icon', 'jobs_count']

    def get_jobs_count(self, obj):
        return obj.job_set.filter(status='published').count()


class JobAttachmentSerializer(serializers.ModelSerializer):
    file_url = serializers.SerializerMethodField()

    class Meta:
        model = JobAttachment
        fields = ['id', 'filename', 'file_url', 'file_size', 'file_type', 'description', 'uploaded_at']
        read_only_fields = ['file_size', 'file_type', 'uploaded_at']

    def get_file_url(self, obj):
        if obj.file:
            request = self.context.get('request')
            if request:
                return request.build_absolute_uri(obj.file.url)
            return obj.file.url
        return None


class JobMilestoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = JobMilestone
        fields = ['id', 'title', 'description', 'amount', 'due_date', 'order', 'is_completed', 'completed_at']
        read_only_fields = ['completed_at']

# jobs/serializers.py

class ClientInfoSerializer(serializers.Serializer):
    id = serializers.CharField(required=False, allow_null=True)
    username = serializers.CharField(required=False, allow_null=True, default='')
    first_name = serializers.CharField(required=False, allow_null=True, default='')
    last_name = serializers.CharField(required=False, allow_null=True, default='')
    profile_picture = serializers.URLField(required=False, allow_null=True)
    rating = serializers.DecimalField(max_digits=3, decimal_places=2, required=False, allow_null=True, default=0)
    total_spent = serializers.DecimalField(max_digits=12, decimal_places=2, required=False, allow_null=True, default=0)
    jobs_posted = serializers.IntegerField(required=False, default=0)
    member_since = serializers.DateTimeField(required=False, allow_null=True)
    location = serializers.CharField(required=False, allow_blank=True, default='')
    is_verified = serializers.BooleanField(required=False, default=False)

class JobListSerializer(serializers.ModelSerializer):
    """Minimal job info for listing pages"""
    category = JobCategorySerializer(read_only=True)
    skills = SkillSerializer(many=True, read_only=True)
    client_info = ClientInfoSerializer(read_only=True)
    budget_display = serializers.SerializerMethodField()
    time_posted = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            'id', 'title', 'description', 'client_info', 'category', 'skills',
            'job_type', 'experience_level', 'estimated_duration',
            'budget_display', 'remote_allowed', 'location', 'is_featured', 'is_urgent',
            'created_at', 'time_posted', 'views_count', 'applications_count',
            'deadline', 'is_saved','status',
        ]

    def get_budget_display(self, obj):
        if obj.job_type == 'hourly':
            if obj.hourly_rate_min and obj.hourly_rate_max:
                return f"${obj.hourly_rate_min}-${obj.hourly_rate_max}/hr"
            return "Hourly rate not specified"
        else:
            if obj.budget_min and obj.budget_max:
                return f"${obj.budget_min:,.0f}-${obj.budget_max:,.0f}"
            return "Budget not specified"

    def get_time_posted(self, obj):
        now = timezone.now()
        diff = now - obj.created_at

        if diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        else:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"

    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user_id'):
            return JobSave.objects.filter(job=obj, user_id=request.user_id).exists()
        return False


class JobDetailSerializer(serializers.ModelSerializer):
    """Complete job information"""
    category = JobCategorySerializer(read_only=True)
    skills = SkillSerializer(many=True, read_only=True)
    attachments = JobAttachmentSerializer(many=True, read_only=True)
    milestones = JobMilestoneSerializer(many=True, read_only=True)
    client_info = ClientInfoSerializer(read_only=True)
    budget_display = serializers.SerializerMethodField()
    time_posted = serializers.SerializerMethodField()
    is_saved = serializers.SerializerMethodField()
    similar_jobs_count = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            'id', 'title', 'description', 'client_info', 'category', 'skills',
            'job_type', 'experience_level', 'estimated_duration',
            'budget_display', 'currency', 'remote_allowed', 'location', 'timezone_preference',
            'languages_required', 'is_featured', 'is_urgent', 'deadline',
            'status',  # ADD THIS FIELD
            'created_at', 'published_at', 'time_posted', 'views_count', 'applications_count',
            'attachments', 'milestones', 'is_saved', 'similar_jobs_count', 'tags'
        ]

    def get_budget_display(self, obj):
        if obj.job_type == 'hourly':
            if obj.hourly_rate_min and obj.hourly_rate_max:
                return f"${obj.hourly_rate_min}-${obj.hourly_rate_max}/hr"
        else:
            if obj.budget_min and obj.budget_max:
                return f"${obj.budget_min:,.0f}-${obj.budget_max:,.0f}"
        return "Budget not specified"

    def get_time_posted(self, obj):
        now = timezone.now()
        diff = now - obj.created_at

        if diff.days > 7:
            return obj.created_at.strftime("%B %d, %Y")
        elif diff.days > 0:
            return f"{diff.days} day{'s' if diff.days > 1 else ''} ago"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours} hour{'s' if hours > 1 else ''} ago"
        else:
            minutes = diff.seconds // 60
            return f"{minutes} minute{'s' if minutes > 1 else ''} ago"

    def get_is_saved(self, obj):
        request = self.context.get('request')
        if request and hasattr(request, 'user_id'):
            return JobSave.objects.filter(job=obj, user_id=request.user_id).exists()
        return False

    def get_similar_jobs_count(self, obj):
        if obj.category:
            return Job.objects.filter(
                category=obj.category,
                status='published'
            ).exclude(id=obj.id).count()
        return 0


class JobCreateUpdateSerializer(serializers.ModelSerializer):
    """Serializer for creating and updating jobs"""
    skill_ids = serializers.ListField(
        child=serializers.IntegerField(),
        write_only=True,
        required=False
    )
    milestones = JobMilestoneSerializer(many=True, required=False)

    class Meta:
        model = Job
        fields = [
            'title', 'description', 'category', 'skill_ids', 'job_type',
            'experience_level', 'estimated_duration', 'budget_min', 'budget_max',
            'hourly_rate_min', 'hourly_rate_max', 'currency', 'remote_allowed',
            'location', 'timezone_preference', 'languages_required',
            'is_urgent', 'deadline', 'tags', 'milestones','status','id',
        ]

    def validate(self, data):
        job_type = data.get('job_type')

        # Budget validation based on job type
        if job_type == 'hourly':
            if not data.get('hourly_rate_min') or not data.get('hourly_rate_max'):
                raise serializers.ValidationError(
                    "Hourly rate range is required for hourly jobs"
                )
            if data.get('hourly_rate_max', 0) < data.get('hourly_rate_min', 0):
                raise serializers.ValidationError(
                    "Maximum hourly rate must be greater than minimum"
                )
        else:
            if not data.get('budget_min') or not data.get('budget_max'):
                raise serializers.ValidationError(
                    "Budget range is required for fixed price and milestone jobs"
                )
            if data.get('budget_max', 0) < data.get('budget_min', 0):
                raise serializers.ValidationError(
                    "Maximum budget must be greater than minimum budget"
                )

        # Milestone validation
        if job_type == 'milestone':
            milestones = data.get('milestones', [])
            if not milestones:
                raise serializers.ValidationError(
                    "At least one milestone is required for milestone-based jobs"
                )

            total_milestone_amount = sum(m.get('amount', 0) for m in milestones)
            budget_max = data.get('budget_max', 0)

            if abs(total_milestone_amount - budget_max) > 0.01:  # Allow small floating point differences
                raise serializers.ValidationError(
                    "Total milestone amount must equal the maximum budget"
                )

        return data

    def create(self, validated_data):
        skill_ids = validated_data.pop('skill_ids', [])
        milestones_data = validated_data.pop('milestones', [])

        # Remove the hardcoded client_id - it should come from the view
        # The view will pass the authenticated user's ID
        # validated_data['client_id'] = 4  # ❌ Remove this line

        job = Job.objects.create(**validated_data)

        # Add skills
        if skill_ids:
            skills = Skill.objects.filter(id__in=skill_ids, is_active=True)
            job.skills.set(skills)

        # Create milestones
        for milestone_data in milestones_data:
            JobMilestone.objects.create(job=job, **milestone_data)

        return job

    def update(self, instance, validated_data):
        skill_ids = validated_data.pop('skill_ids', None)
        milestones_data = validated_data.pop('milestones', None)

        # Update job fields
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()

        # Update skills
        if skill_ids is not None:
            skills = Skill.objects.filter(id__in=skill_ids, is_active=True)
            instance.skills.set(skills)

        # Update milestones
        if milestones_data is not None:
            # Remove existing milestones
            instance.milestones.all().delete()
            # Create new milestones
            for milestone_data in milestones_data:
                JobMilestone.objects.create(job=instance, **milestone_data)

        return instance


class JobStatusUpdateSerializer(serializers.ModelSerializer):
    """Serializer for updating job status"""

    class Meta:
        model = Job
        fields = ['status']

    def validate_status(self, value):
        instance = self.instance
        if not instance:
            return value

        current_status = instance.status

        # Define allowed status transitions
        allowed_transitions = {
            'draft': ['published', 'cancelled'],
            'published': ['in_progress', 'paused', 'cancelled'],
            'in_progress': ['completed', 'paused', 'cancelled'],
            'paused': ['published', 'in_progress', 'cancelled'],
            'completed': [],  # Final state
            'cancelled': []  # Final state
        }

        if value not in allowed_transitions.get(current_status, []):
            raise serializers.ValidationError(
                f"Cannot change status from '{current_status}' to '{value}'"
            )

        return value

    def update(self, instance, validated_data):
        new_status = validated_data.get('status')

        # Set timestamps based on status
        if new_status == 'published' and instance.status == 'draft':
            instance.published_at = timezone.now()
        elif new_status in ['completed', 'cancelled']:
            instance.closed_at = timezone.now()

        return super().update(instance, validated_data)


class JobSaveSerializer(serializers.ModelSerializer):
    """Serializer for saving/unsaving jobs"""

    class Meta:
        model = JobSave
        fields = ['job', 'saved_at']
        read_only_fields = ['saved_at']

    def create(self, validated_data):
        validated_data['user_id'] = self.context['request'].user_id
        return super().create(validated_data)


class JobStatsSerializer(serializers.Serializer):
    """Serializer for job statistics"""
    total_jobs = serializers.IntegerField()
    published_jobs = serializers.IntegerField()
    draft_jobs = serializers.IntegerField()
    in_progress_jobs = serializers.IntegerField()
    completed_jobs = serializers.IntegerField()
    cancelled_jobs = serializers.IntegerField()
    total_views = serializers.IntegerField()
    total_applications = serializers.IntegerField()
    average_budget = serializers.DecimalField(max_digits=12, decimal_places=2)
    recent_activity = serializers.ListField(child=serializers.DictField())