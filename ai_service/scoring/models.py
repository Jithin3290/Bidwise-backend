# scoring/models.py

from django.db import models
from django.contrib.auth.models import AbstractUser
import uuid


# Proxy models - reference your existing users tables
class User(AbstractUser):
    """Proxy to existing users table"""

    class Meta:
        db_table = 'users'
        managed = False  # Don't create this table


class FreelancerProfile(models.Model):
    """Proxy to existing freelancer_profiles table"""
    user = models.OneToOneField('User', on_delete=models.CASCADE,
                                related_name='freelancer_profile_scoring')
    skills = models.JSONField(default=list)
    experience_level = models.CharField(max_length=20)
    years_of_experience = models.PositiveIntegerField(null=True)
    hourly_rate = models.DecimalField(max_digits=10, decimal_places=2, null=True)
    average_rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)
    total_reviews = models.PositiveIntegerField(default=0)
    total_projects_completed = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'freelancer_profiles'
        managed = False  # Don't create this table


# New tables for scoring (will be created)
class FreelancerScore(models.Model):
    """AI-calculated scores for freelancers"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.IntegerField(unique=True, db_index=True)  # Reference to User.id

    # Component Scores (0-100)
    experience_score = models.FloatField(default=0)
    education_score = models.FloatField(default=0)
    review_score = models.FloatField(default=0)
    completion_score = models.FloatField(default=0)
    responsiveness_score = models.FloatField(default=0)
    skills_score = models.FloatField(default=0)

    # Final Score (0-100)
    final_score = models.FloatField(default=0, db_index=True)
    score_tier = models.CharField(max_length=20, default='unrated')  # elite, excellent, good, average, new

    # AI Analysis
    ai_quality_score = models.FloatField(default=0)
    ai_insights = models.TextField(blank=True, null=True)
    strengths = models.JSONField(default=list)
    improvements = models.JSONField(default=list)

    # Metadata
    calculation_version = models.CharField(max_length=10, default='1.0')
    last_calculated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_freelancer_scores'
        ordering = ['-final_score']
        indexes = [
            models.Index(fields=['user_id', 'final_score']),
            models.Index(fields=['score_tier', 'final_score']),
        ]

    def __str__(self):
        return f"Score for User {self.user_id}: {self.final_score}"

    def get_tier(self):
        """Calculate tier based on score"""
        if self.final_score >= 90:
            return 'elite'
        elif self.final_score >= 80:
            return 'excellent'
        elif self.final_score >= 70:
            return 'good'
        elif self.final_score >= 50:
            return 'average'
        else:
            return 'new'


class JobMatch(models.Model):
    """Store job-freelancer semantic matches"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    job_id = models.CharField(max_length=100, db_index=True)
    user_id = models.IntegerField(db_index=True)

    # Match Scores
    semantic_similarity = models.FloatField(default=0)
    skill_match_percentage = models.FloatField(default=0)
    combined_score = models.FloatField(default=0, db_index=True)

    # Match Details
    matched_skills = models.JSONField(default=list)
    missing_skills = models.JSONField(default=list)
    match_explanation = models.TextField(blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField(null=True)  # Cache expiry

    class Meta:
        db_table = 'ai_job_matches'
        ordering = ['-combined_score']
        unique_together = ['job_id', 'user_id']
        indexes = [
            models.Index(fields=['job_id', 'combined_score']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"Match: Job {self.job_id} - User {self.user_id}"


class ScoreHistory(models.Model):
    """Track score changes over time"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user_id = models.IntegerField(db_index=True)
    score = models.FloatField()
    score_breakdown = models.JSONField(default=dict)
    reason = models.CharField(max_length=200, blank=True)  # e.g., "new review", "profile update"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'ai_score_history'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user_id', 'created_at']),
        ]