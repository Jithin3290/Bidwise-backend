import uuid
from decimal import Decimal

import pyotp
from django.contrib.auth.models import AbstractUser
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    """Base User model with core fields only"""

    TIMEZONE_CHOICES = (
        ("UTC", "UTC"),
        ("America/New_York", "Eastern Time"),
        ("America/Chicago", "Central Time"),
        ("America/Denver", "Mountain Time"),
        ("America/Los_Angeles", "Pacific Time"),
        ("Europe/London", "London"),
        ("Europe/Berlin", "Berlin"),
        ("Asia/Tokyo", "Tokyo"),
        ("Asia/Shanghai", "Shanghai"),
        ("Asia/Kolkata", "India Standard Time"),
    )

    # Basic Information
    email = models.EmailField(unique=True)
    phone_number = models.CharField(max_length=15, blank=True)
    profile_picture = models.ImageField(upload_to="profiles/", blank=True)
    bio = models.TextField(blank=True, max_length=1000)

    # Location Information
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    timezone = models.CharField(max_length=50, choices=TIMEZONE_CHOICES, default="UTC")

    # Verification status
    is_verified = models.BooleanField(default=False)
    phone_verified = models.BooleanField(default=False)
    identity_verified = models.BooleanField(default=False)

    # Profile completion and activity
    profile_completion_percentage = models.PositiveIntegerField(default=0)
    last_activity = models.DateTimeField(auto_now=True)
    is_featured = models.BooleanField(default=False)
    is_premium = models.BooleanField(default=False)
    premium_expires = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    class Meta:
        db_table = "users"
        indexes = [
            models.Index(fields=["is_active"]),
            models.Index(fields=["created_at"]),
            models.Index(fields=["last_activity"]),
        ]

    def __str__(self):
        return f"{self.email}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}".strip()

    @property
    def is_account_locked(self):
        security_profile = getattr(self, "security_profile", None)
        if security_profile and security_profile.account_locked_until:
            return timezone.now() < security_profile.account_locked_until
        return False

    @property
    def account_types(self):
        """Get all account types for this user"""
        return self.user_account_types.values_list("account_type", flat=True)

    @property
    def is_freelancer(self):
        return "freelancer" in self.account_types

    @property
    def is_client(self):
        return "client" in self.account_types

    @property
    def is_admin(self):
        return "admin" in self.account_types

    def can_login(self):
        """Check if user can login (not locked)"""
        return not self.is_account_locked and self.is_active

    def reset_login_attempts(self):
        """Reset login attempts after successful login"""
        security_profile, created = UserSecurity.objects.get_or_create(user=self)
        security_profile.login_attempts = 0
        security_profile.last_failed_login = None
        security_profile.save(update_fields=["login_attempts", "last_failed_login"])

    def increment_login_attempts(self):
        """Increment login attempts and lock account if needed"""
        security_profile, created = UserSecurity.objects.get_or_create(user=self)
        security_profile.login_attempts += 1
        security_profile.last_failed_login = timezone.now()

        # Lock account for 30 minutes after 5 failed attempts
        if security_profile.login_attempts >= 5:
            security_profile.account_locked_until = timezone.now() + timezone.timedelta(
                minutes=5
            )

        security_profile.save(
            update_fields=[
                "login_attempts",
                "last_failed_login",
                "account_locked_until",
            ]
        )

    def generate_email_verification_token(self):
        """Generate a 6-digit verification code and set expiry"""
        import random
        import string

        security_profile, created = UserSecurity.objects.get_or_create(user=self)
        code = "".join(random.choices(string.digits, k=6))
        security_profile.email_verification_token = code
        security_profile.email_verification_expires = (
            timezone.now() + timezone.timedelta(minutes=15)
        )
        security_profile.save(
            update_fields=["email_verification_token", "email_verification_expires"]
        )
        return code

    def is_email_verification_token_valid(self, token):
        """Check if the provided token is valid and not expired"""
        security_profile = getattr(self, "security_profile", None)
        if (
            not security_profile
            or not security_profile.email_verification_token
            or not security_profile.email_verification_expires
        ):
            return False

        if timezone.now() > security_profile.email_verification_expires:
            return False

        return security_profile.email_verification_token == token

    def clear_email_verification_token(self):
        """Clear the verification token after successful verification"""
        security_profile = getattr(self, "security_profile", None)
        if security_profile:
            security_profile.email_verification_token = ""
            security_profile.email_verification_expires = None
            security_profile.save(
                update_fields=["email_verification_token", "email_verification_expires"]
            )

    def calculate_profile_completion(self):
        """Calculate profile completion percentage based on account types"""
        base_fields = [
            "first_name",
            "last_name",
            "bio",
            "phone_number",
            "profile_picture",
            "country",
            "city",
        ]

        completed_fields = 0
        for field in base_fields:
            value = getattr(self, field, None)
            if value:
                if isinstance(value, list) and len(value) > 0:
                    completed_fields += 1
                elif not isinstance(value, list):
                    completed_fields += 1

        # Add professional profile completion
        professional_profile = getattr(self, "professional_profile", None)
        if professional_profile:
            completed_fields += professional_profile.calculate_completion()

        # Add specific profile completion based on account types
        total_fields = len(base_fields) + 4  # Base + professional fields

        if self.is_freelancer:
            freelancer_profile = getattr(self, "freelancer_profile", None)
            if freelancer_profile:
                completed_fields += freelancer_profile.calculate_completion()
                total_fields += (
                    4  # skills, experience_level, hourly_rate, portfolio_url
                )

        if self.is_client:
            client_profile = getattr(self, "client_profile", None)
            if client_profile:
                completed_fields += client_profile.calculate_completion()
                total_fields += 3  # company_size, industry

        percentage = (
            int((completed_fields / total_fields) * 100) if total_fields > 0 else 0
        )
        self.profile_completion_percentage = percentage
        return percentage


class UserProfessionalProfile(models.Model):
    """Professional information for users"""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="professional_profile"
    )

    # Professional Information
    title = models.CharField(max_length=100, blank=True)
    company_name = models.CharField(max_length=100, blank=True)
    website = models.URLField(blank=True)
    linkedin_url = models.URLField(blank=True)
    github_url = models.URLField(blank=True)
    portfolio_url = models.URLField(blank=True)
    languages_spoken = models.JSONField(default=list, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_professional_profiles"

    def __str__(self):
        return f"Professional Profile - {self.user.email}"

    def calculate_completion(self):
        """Calculate completion score for professional profile"""
        fields_to_check = ["title", "website", "linkedin_url", "languages_spoken"]
        completed_fields = 0

        for field in fields_to_check:
            value = getattr(self, field, None)
            if value:
                if isinstance(value, list) and len(value) > 0:
                    completed_fields += 1
                elif not isinstance(value, list):
                    completed_fields += 1

        return completed_fields


# In users/models.py - Update the UserSecurity class

import base64
import secrets
import string
from io import BytesIO

import pyotp
import qrcode


class UserSecurity(models.Model):
    """Security related information for users"""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="security_profile"
    )

    # Email verification
    email_verification_token = models.CharField(max_length=100, blank=True)
    email_verification_expires = models.DateTimeField(null=True, blank=True)

    # Security fields
    last_login_ip = models.GenericIPAddressField(blank=True, null=True)
    mfa_enabled = models.BooleanField(default=False)
    mfa_secret = models.CharField(
        max_length=32, blank=True, null=True
    )  # Changed from 16 to 32
    mfa_backup_codes = models.JSONField(
        default=list, blank=True, null=True
    )  # Add this field
    login_attempts = models.PositiveIntegerField(default=0)
    last_failed_login = models.DateTimeField(null=True, blank=True)
    account_locked_until = models.DateTimeField(null=True, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_security_profiles"

    def generate_mfa_secret(self):
        """Generate a new MFA secret"""
        self.mfa_secret = pyotp.random_base32()
        self.save(update_fields=["mfa_secret"])
        return self.mfa_secret

    def get_totp_uri(self):
        """Get TOTP URI for QR code generation"""
        if not self.mfa_secret:
            self.generate_mfa_secret()

        totp = pyotp.TOTP(self.mfa_secret)
        return totp.provisioning_uri(name=self.user.email, issuer_name="Kam.Com")

    def generate_qr_code(self):
        """Generate QR code for MFA setup"""
        uri = self.get_totp_uri()
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(uri)
        qr.make(fit=True)

        img = qr.make_image(fill_color="red", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)

        # Convert to base64 for frontend display
        image_data = base64.b64encode(buffer.getvalue()).decode()
        return f"data:image/png;base64,{image_data}"

    def verify_totp(self, token):
        """Verify TOTP token"""
        if not self.mfa_secret:
            return False

        totp = pyotp.TOTP(self.mfa_secret)
        return totp.verify(token, valid_window=1)

    def generate_backup_codes(self):
        """Generate backup codes for MFA"""
        codes = []
        for _ in range(10):
            code = "".join(
                secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8)
            )
            codes.append(code)

        self.mfa_backup_codes = codes
        self.save(update_fields=["mfa_backup_codes"])
        return codes

    def use_backup_code(self, code):
        """Use a backup code and remove it from the list"""
        if code.upper() in self.mfa_backup_codes:
            self.mfa_backup_codes.remove(code.upper())
            self.save(update_fields=["mfa_backup_codes"])
            return True
        return False

    # Keep your existing methods
    def verify_mfa_code(self, code):
        """Verify a TOTP code (legacy method)"""
        return self.verify_totp(code)

    def __str__(self):
        return f"Security Profile - {self.user.email}"


class UserPreferences(models.Model):
    """User preferences and settings"""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="preferences"
    )

    # Preferences
    notification_preferences = models.JSONField(default=dict, blank=True)
    privacy_settings = models.JSONField(default=dict, blank=True)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "user_preferences"

    def __str__(self):
        return f"Preferences - {self.user.email}"


class UserAccountType(models.Model):
    """Many-to-Many relationship model for user account types"""

    USER_TYPES = (
        ("client", "Client"),
        ("freelancer", "Freelancer"),
        ("admin", "Admin"),
    )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="user_account_types"
    )
    account_type = models.CharField(max_length=20, choices=USER_TYPES)
    is_primary = models.BooleanField(default=True)  # Mark primary account type
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ["user", "account_type"]
        db_table = "user_account_types"
        indexes = [
            models.Index(fields=["user", "account_type"]),
            models.Index(fields=["account_type", "is_active"]),
        ]

    def __str__(self):
        return f"{self.user.email} - {self.account_type}"

    def save(self, *args, **kwargs):
        # Ensure only one primary account type per user
        if self.is_primary:
            UserAccountType.objects.filter(user=self.user, is_primary=True).update(
                is_primary=False
            )
        super().save(*args, **kwargs)


class FreelancerProfile(models.Model):
    """Freelancer-specific profile information"""

    EXPERIENCE_LEVELS = (
        ("entry", "Entry Level"),
        ("intermediate", "Intermediate"),
        ("expert", "Expert"),
        ("senior", "Senior"),
    )

    AVAILABILITY_STATUS = (
        ("available", "Available"),
        ("busy", "Busy"),
        ("unavailable", "Unavailable"),
    )

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="freelancer_profile"
    )

    # Skills and Experience
    skills = models.JSONField(default=list, blank=True)
    experience_level = models.CharField(
        max_length=20, choices=EXPERIENCE_LEVELS, blank=True
    )
    years_of_experience = models.PositiveIntegerField(null=True, blank=True)

    # Pricing and Availability
    hourly_rate = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField(max_length=3, default="USD")  # Currency code
    availability_status = models.CharField(
        max_length=20, choices=AVAILABILITY_STATUS, default="available"
    )
    availability_hours_per_week = models.PositiveIntegerField(null=True, blank=True)

    # Rating and Reviews
    average_rating = models.DecimalField(
        max_digits=3,
        decimal_places=2,
        default=Decimal("0.00"),
        validators=[MinValueValidator(0), MaxValueValidator(5)],
    )
    total_reviews = models.PositiveIntegerField(default=0)
    total_projects_completed = models.PositiveIntegerField(default=0)

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "freelancer_profiles"
        indexes = [
            models.Index(fields=["average_rating", "total_reviews"]),
            models.Index(fields=["availability_status"]),
            models.Index(fields=["hourly_rate"]),
        ]

    def __str__(self):
        return f"Freelancer Profile - {self.user.email}"

    def update_rating(self, new_rating):
        """Update average rating when a new review is added"""
        total_rating_points = self.average_rating * self.total_reviews
        total_rating_points += new_rating
        self.total_reviews += 1
        self.average_rating = total_rating_points / self.total_reviews
        self.save(update_fields=["average_rating", "total_reviews"])

    def calculate_completion(self):
        """Calculate completion score for freelancer profile"""
        fields_to_check = ["skills", "experience_level", "hourly_rate"]
        completed_fields = 0

        for field in fields_to_check:
            value = getattr(self, field, None)
            if value:
                if isinstance(value, list) and len(value) > 0:
                    completed_fields += 1
                elif not isinstance(value, list):
                    completed_fields += 1

        # Check if user has portfolio_url in professional profile
        professional_profile = getattr(self.user, "professional_profile", None)
        if professional_profile and professional_profile.portfolio_url:
            completed_fields += 1

        return completed_fields


class ClientProfile(models.Model):
    """Client-specific profile information"""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="client_profile"
    )

    # Company Information
    company_size = models.CharField(max_length=50, blank=True)
    industry = models.CharField(max_length=100, blank=True)

    # Project Statistics
    total_projects_posted = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(
        max_digits=12, decimal_places=2, default=Decimal("0.00")
    )

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "client_profiles"
        indexes = [
            models.Index(fields=["total_projects_posted"]),
            models.Index(fields=["total_spent"]),
        ]

    def __str__(self):
        return f"Client Profile - {self.user.email}"

    def calculate_completion(self):
        """Calculate completion score for client profile"""
        fields_to_check = ["company_size", "industry"]
        completed_fields = 0

        for field in fields_to_check:
            value = getattr(self, field, None)
            if value:
                completed_fields += 1

        return completed_fields


class AdminProfile(models.Model):
    """Admin-specific profile information"""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="admin_profile"
    )

    # Admin permissions and roles
    permissions = models.JSONField(default=dict, blank=True)
    department = models.CharField(max_length=100, blank=True)
    admin_level = models.CharField(
        max_length=50, default="basic"
    )  # basic, advanced, super

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "admin_profiles"

    def __str__(self):
        return f"Admin Profile - {self.user.email}"


class UserEducation(models.Model):
    """Education history for users (mainly freelancers)"""

    freelancer_profile = models.ForeignKey(
        FreelancerProfile, on_delete=models.CASCADE, related_name="education"
    )
    degree = models.CharField(max_length=100)
    field_of_study = models.CharField(max_length=100)
    institution = models.CharField(max_length=200)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # Null if currently studying
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]
        db_table = "user_education"

    def __str__(self):
        return f"{self.degree} at {self.institution}"


class UserExperience(models.Model):
    """Work experience for users (mainly freelancers)"""

    freelancer_profile = models.ForeignKey(
        FreelancerProfile, on_delete=models.CASCADE, related_name="experience"
    )
    title = models.CharField(max_length=100)
    company = models.CharField(max_length=200)
    location = models.CharField(max_length=100, blank=True)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)  # Null if current job
    description = models.TextField(blank=True)
    is_current = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]
        db_table = "user_experience"

    def __str__(self):
        return f"{self.title} at {self.company}"


class UserCertification(models.Model):
    """Certifications for users (mainly freelancers)"""

    freelancer_profile = models.ForeignKey(
        FreelancerProfile, on_delete=models.CASCADE, related_name="certifications"
    )
    name = models.CharField(max_length=200)
    issuing_organization = models.CharField(max_length=200)
    issue_date = models.DateField()
    expiry_date = models.DateField(null=True, blank=True)
    credential_id = models.CharField(max_length=100, blank=True)
    credential_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-issue_date"]
        db_table = "user_certifications"

    def __str__(self):
        return f"{self.name} - {self.issuing_organization}"


class UserPortfolio(models.Model):
    """Portfolio items for freelancers"""

    freelancer_profile = models.ForeignKey(
        FreelancerProfile,
        on_delete=models.CASCADE,
        related_name="portfolio",
        null=True,
        blank=True,
    )
    title = models.CharField(max_length=200)
    description = models.TextField()
    image = models.ImageField(upload_to="portfolio/", blank=True)
    url = models.URLField(blank=True)
    technologies_used = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_featured = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created_at"]
        db_table = "user_portfolio"

    def __str__(self):
        return f"{self.title} by {self.freelancer_profile.user.email}"


class UserSocialLink(models.Model):
    PLATFORM_CHOICES = (
        ("linkedin", "LinkedIn"),
        ("github", "GitHub"),
        ("twitter", "Twitter"),
        ("instagram", "Instagram"),
        ("facebook", "Facebook"),
        ("youtube", "YouTube"),
        ("website", "Personal Website"),
        ("other", "Other"),
    )

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="social_links"
    )
    platform = models.CharField(max_length=20, choices=PLATFORM_CHOICES)
    url = models.URLField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "platform"]
        db_table = "user_social_links"

    def __str__(self):
        return f"{self.user.email} - {self.platform}"
