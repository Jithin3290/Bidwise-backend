# bids/filters.py
import django_filters
from django.db.models import Q
from .models import Bid


class BidFilter(django_filters.FilterSet):
    """Filter set for bid queries"""

    # FIXED: Status filters - now handles comma-separated values
    status = django_filters.CharFilter(
        method='filter_status',
        help_text="Filter by bid status (supports comma-separated values)"
    )

    # Bid type filters
    bid_type = django_filters.ChoiceFilter(
        choices=Bid.BID_TYPE_CHOICES,
        help_text="Filter by bid type"
    )

    # Amount range filters
    min_amount = django_filters.NumberFilter(
        field_name='amount',
        lookup_expr='gte',
        help_text="Minimum bid amount"
    )
    max_amount = django_filters.NumberFilter(
        field_name='amount',
        lookup_expr='lte',
        help_text="Maximum bid amount"
    )

    # Hourly rate filters
    min_hourly_rate = django_filters.NumberFilter(
        field_name='hourly_rate',
        lookup_expr='gte',
        help_text="Minimum hourly rate"
    )
    max_hourly_rate = django_filters.NumberFilter(
        field_name='hourly_rate',
        lookup_expr='lte',
        help_text="Maximum hourly rate"
    )

    # Delivery time filters
    max_delivery_time = django_filters.NumberFilter(
        field_name='estimated_delivery',
        lookup_expr='lte',
        help_text="Maximum delivery time in days"
    )

    # Date filters
    created_after = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='gte',
        help_text="Bids created after this date"
    )
    created_before = django_filters.DateTimeFilter(
        field_name='created_at',
        lookup_expr='lte',
        help_text="Bids created before this date"
    )

    # Freelancer filters
    freelancer_id = django_filters.CharFilter(
        help_text="Filter by freelancer ID"
    )

    # Job filters
    job_id = django_filters.CharFilter(
        help_text="Filter by job ID"
    )

    # Featured bids
    is_featured = django_filters.BooleanFilter(
        help_text="Filter featured bids"
    )

    # Client viewed status
    client_viewed = django_filters.BooleanFilter(
        field_name='client_viewed_at',
        lookup_expr='isnull',
        exclude=True,
        help_text="Filter bids viewed by client"
    )

    # Search in proposal
    search = django_filters.CharFilter(
        method='filter_search',
        help_text="Search in bid proposals"
    )

    class Meta:
        model = Bid
        fields = [
            'status', 'bid_type', 'min_amount', 'max_amount',
            'min_hourly_rate', 'max_hourly_rate', 'max_delivery_time',
            'created_after', 'created_before', 'freelancer_id',
            'job_id', 'is_featured', 'client_viewed', 'search'
        ]

    def filter_status(self, queryset, name, value):
        """
        Handle comma-separated status values from frontend
        Supports both single values and comma-separated multiple values
        """
        if not value:
            return queryset

        # Split comma-separated values and clean them
        status_list = [status.strip() for status in value.split(',') if status.strip()]

        # Get valid status choices from the model
        valid_statuses = [choice[0] for choice in Bid.BID_STATUS_CHOICES]

        # Filter out invalid status values
        status_list = [s for s in status_list if s in valid_statuses]

        if status_list:
            return queryset.filter(status__in=status_list)

        return queryset

    def filter_search(self, queryset, name, value):
        """Search in proposal text"""
        if value:
            return queryset.filter(
                Q(proposal__icontains=value) |
                Q(questions__icontains=value)
            )
        return queryset