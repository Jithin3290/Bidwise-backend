"""
Bids views package initialization
Import all views for easy access
"""
from .public_views import (
    JobBidsListView,
    BidDetailView,
    JobBidSummaryView,
    HealthCheckView,
)
from .freelancer_views import (
    FreelancerBidsListView,
    CreateBidView,
    UpdateBidView,
    WithdrawBidView,
    FreelancerDashboardView,
)
from .client_views import (
    ClientBidManagementView,
    UpdateBidStatusView,
)
from .attachment_views import (
    BidAttachmentView,
)
from .statistics_views import (
    BidStatisticsView,
)
from .notification_views import (
    simple_notification_test,
    send_bid_reminder_notifications,
    test_bid_notifications,
    debug_notification_detailed,
)
from .payment_views import CreatePaymentOrderView,VerifyPaymentView,PaymentDetailsView,BidPaymentsListView,PaymentWebhookView,ClientAcceptedBidsView,FreelancerAcceptedBidsView,FreelancerDashboardStatsView

__all__ = [
    # Public
    'JobBidsListView',
    'BidDetailView',
    'JobBidSummaryView',
    'HealthCheckView',
    # Freelancer
    'FreelancerBidsListView',
    'CreateBidView',
    'UpdateBidView',
    'WithdrawBidView',
    'FreelancerDashboardView',
    # Client
    'ClientBidManagementView',
    'UpdateBidStatusView',
    # Attachments
    'BidAttachmentView',
    # Statistics
    'BidStatisticsView',
    # Notifications
    'simple_notification_test',
    'send_bid_reminder_notifications',
    'test_bid_notifications',
    'debug_notification_detailed',
    'CreatePaymentOrderView',
    'VerifyPaymentView',
    'PaymentDetailsView',
    'BidPaymentsListView',
    'PaymentWebhookView',
    'ClientAcceptedBidsView',
    'FreelancerAcceptedBidsView',
    'FreelancerDashboardStatsView',
]