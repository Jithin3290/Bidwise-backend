"""
Views package initialization
Import all views for easy access
"""
from .auth_views import (
    GoogleLoginView,
    GetUserView,
    RegisterView,
    LoginView,
    ChangePasswordView,
    google_login,
)
from .mfa_views import (
    MFASetupView,
    MFAVerifySetupView,
    MFAStatusView,
)
from .email_views import (
    SendEmailVerificationView,
    VerifyEmailCodeView,
    resend_verification_email,
)
from .profile_views import (
    CurrentUserProfileView,
    UpdateUserProfileView,
    UserProfileView,
    UpdateProfileCompletionView,
    UserPublicPortfolioView,
)
from .account_views import (
    ManageAccountTypeView,
)
from .user_management_views import (
    UserListView,
    UserEducationViewSet,
    UserExperienceViewSet,
    UserCertificationViewSet,
    UserPortfolioViewSet,
    UserSocialLinkViewSet,
)
from .admin_views import (
    AdminUsersView,
    AssignUserGroupView,
    ToggleUserStatusView,
    UserStatsView,
)
from .service_views import (
    get_user_profile_for_service,
    verify_token_for_service,
    get_users_batch_for_service,
)
from .task_views import (
    check_task_status,
)

__all__ = [
    # Auth
    'GoogleLoginView',
    'GetUserView',
    'RegisterView',
    'LoginView',
    'ChangePasswordView',
    'google_login',
    # MFA
    'MFASetupView',
    'MFAVerifySetupView',
    'MFAStatusView',
    # Email
    'SendEmailVerificationView',
    'VerifyEmailCodeView',
    'resend_verification_email',
    # Profile
    'CurrentUserProfileView',
    'UpdateUserProfileView',
    'UserProfileView',
    'UpdateProfileCompletionView',
    'UserPublicPortfolioView',
    # Account
    'ManageAccountTypeView',
    # User Management
    'UserListView',
    'UserEducationViewSet',
    'UserExperienceViewSet',
    'UserCertificationViewSet',
    'UserPortfolioViewSet',
    'UserSocialLinkViewSet',
    # Admin
    'AdminUsersView',
    'AssignUserGroupView',
    'ToggleUserStatusView',
    'UserStatsView',
    # Service
    'get_user_profile_for_service',
    'verify_token_for_service',
    'get_users_batch_for_service',
    # Tasks
    'check_task_status',
]