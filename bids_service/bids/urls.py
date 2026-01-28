# bids/urls.py
from django.urls import path

from . import views
from .views import CreatePaymentOrderView, VerifyPaymentView, PaymentDetailsView, BidPaymentsListView, \
    PaymentWebhookView, ClientAcceptedBidsView, FreelancerAcceptedBidsView, FreelancerDashboardStatsView

# Removed app_name to avoid namespace conflict
# app_name = 'bids'

urlpatterns = [
    # ============= HEALTH CHECK =============
    path("health/", views.HealthCheckView.as_view(), name="bids-health-check"),
    # ============= PUBLIC ENDPOINTS =============
    # Job Bids
    path(
        "jobs/<str:job_id>/bids/", views.JobBidsListView.as_view(), name="job-bids-list"
    ),
    path(
        "jobs/<str:job_id>/summary/", views.JobBidSummaryView.as_view(), name="job-bid-summary"
    ),
    # Bid Details
    path("<uuid:bid_id>/", views.BidDetailView.as_view(), name="bid-detail"),
    # ============= FREELANCER ENDPOINTS =============
    # Bid Management
    path(
        "freelancer/bids/",
        views.FreelancerBidsListView.as_view(),
        name="freelancer-bids-list",
    ),
    path("freelancer/bids/create/", views.CreateBidView.as_view(), name="create-bid"),
    path(
        "freelancer/bids/<uuid:pk>/update/",
        views.UpdateBidView.as_view(),
        name="update-bid",
    ),
    path(
        "freelancer/bids/<uuid:pk>/withdraw/",
        views.WithdrawBidView.as_view(),
        name="withdraw-bid",
    ),
    # Bid Attachments
    path(
        "freelancer/bids/<uuid:bid_id>/attachments/",
        views.BidAttachmentView.as_view(),
        name="upload-bid-attachment",
    ),
    path(
        "freelancer/bids/<uuid:bid_id>/attachments/<int:attachment_id>/",
        views.BidAttachmentView.as_view(),
        name="delete-bid-attachment",
    ),
    # Freelancer Dashboard
    path(
        "freelancer/dashboard/", views.FreelancerDashboardView.as_view(), name="freelancer-dashboard"
    ),

    # ============= CLIENT ENDPOINTS =============

    # Bid Management
    path(
        "client/dashboard/",
        views.ClientBidManagementView.as_view(),
        name="client-bid-management",
    ),
    path(
        "client/bids/<uuid:bid_id>/status/",
        views.UpdateBidStatusView.as_view(),
        name="update-bid-status",
    ),
    # ============= STATISTICS ENDPOINTS =============
    path("statistics/", views.BidStatisticsView.as_view(), name="bid-statistics"),



    path('notifications/test-all/', views.test_bid_notifications, name='test_bid_notifications'),
    path('notifications/debug-detailed/', views.debug_notification_detailed, name='debug_notification_detailed'),
    path('payments/create-order/', CreatePaymentOrderView.as_view(), name='create-payment-order'),
    path('payments/verify/', VerifyPaymentView.as_view(), name='verify-payment'),
    path('payments/<uuid:payment_id>/', PaymentDetailsView.as_view(), name='payment-details'),
    path('<uuid:bid_id>/payments/', BidPaymentsListView.as_view(), name='bid-payments'),
    path('payments/webhook/', PaymentWebhookView.as_view(), name='payment-webhook'),
    path('client-accepted-bids/', ClientAcceptedBidsView.as_view(), name='client-accepted-bids'),
    path('freelancer-accepted-bids/', FreelancerAcceptedBidsView.as_view(), name='freelancer-accepted-bids'),
    path('freelancer-dashboard-stats/', FreelancerDashboardStatsView.as_view(), name='freelancer-dashboard-stats'),
]
