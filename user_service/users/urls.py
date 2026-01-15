from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView

from . import views

router = DefaultRouter()
router.register(r"profile/education", views.UserEducationViewSet, basename="education")
router.register(r"profile/experience", views.UserExperienceViewSet, basename="experience")
router.register(r"profile/certifications", views.UserCertificationViewSet, basename="certifications")
router.register(r"profile/portfolio", views.UserPortfolioViewSet, basename="portfolio")
router.register(r"profile/social-links", views.UserSocialLinkViewSet, basename="social-links")


urlpatterns = [
    # Authentication
    path("register/", views.RegisterView.as_view(), name="register"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("google/", views.GoogleLoginView.as_view(), name="google_login"),
    path("google-legacy/", views.google_login, name="google_login_legacy"),
    path("change-password/", views.ChangePasswordView.as_view(), name="change_password"),
    path("user/", views.GetUserView.as_view(), name="user"),
    path("mfa/setup/", views.MFASetupView.as_view(), name="mfa_setup"),
    path("mfa/verify-setup/", views.MFAVerifySetupView.as_view(), name="mfa_verify_setup"),
    path("mfa/status/", views.MFAStatusView.as_view(), name="mfa_status"),

    # Profile Management
    path("users/profile/", views.CurrentUserProfileView.as_view(), name="current_user_profile"),
    path("profile/update/", views.UpdateUserProfileView.as_view(), name="update_user_profile"),
    path("profile/<int:user_id>/", views.UserProfileView.as_view(), name="user_profile"),
    path("profile/completion/update/", views.UpdateProfileCompletionView.as_view(), name="update_profile_completion"),

    # User Search and Listing
    path("users/", views.UserListView.as_view(), name="user_list"),
    path("users/<int:user_id>/portfolio/", views.UserPublicPortfolioView.as_view(), name="user_public_portfolio"),

    # Account Type Management
    path("account-type/manage/", views.ManageAccountTypeView.as_view(), name="manage_account_type"),

    # Admin Views
    path("admin/users/", views.AdminUsersView.as_view(), name="admin_all_users"),
    path("admin/users/assign-group/", views.AssignUserGroupView.as_view(), name="admin_assign_group"),
    path("admin/users/<int:user_id>/toggle-status/", views.ToggleUserStatusView.as_view(), name="admin_toggle_user_status"),
    path("admin/stats/", views.UserStatsView.as_view(), name="admin_user_stats"),

    # Email Verification
    path("verify-email/send/", views.SendEmailVerificationView.as_view(), name="send_email_verification"),
    path("verify-email/", views.VerifyEmailCodeView.as_view(), name="verify_email_code"),
    path("resend-verification/", views.resend_verification_email, name="resend_verification"),

    # Celery Task Utilities
    path("task-status/<str:task_id>/", views.check_task_status, name="check_task_status"),

    # Service-specific endpoints
    path("users/<int:user_id>/profile/", views.get_user_profile_for_service, name="user-profile-service"),
    path("users/batch/", views.get_users_batch_for_service, name="users-batch-service"),

    # JWT Token
    path("verify-token/", TokenObtainPairView.as_view(), name="token_obtain_pair"),

    # Include ViewSet URLs
    path("", include(router.urls)),

    # Captcha
    path("captcha/", include("captcha.urls")),
]
