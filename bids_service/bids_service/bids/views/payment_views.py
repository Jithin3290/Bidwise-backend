import logging

from django.conf import settings
from rest_framework import status, generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .utils import StandardResultsSetPagination
from ..authentication import JWTAuthentication
from ..permissions import IsClient, IsFreelancer
from ..serializers import CreatePaymentOrderSerializer, VerifyPaymentSerializer, PaymentSerializer, BidListSerializer, \
    FreelancerAcceptedBidSerializer
from ..services import RazorpayPaymentService, JobService, notification_client,UserService
from ..models import Payment, Bid, FreelancerBidProfile
from ..utils import update_freelancer_profile_cache

logger = logging.getLogger(__name__)

class CreatePaymentOrderView(APIView):
    """Create Razorpay payment order for an accepted bid"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsClient]

    def post(self, request):
        serializer = CreatePaymentOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        bid_id = serializer.validated_data['bid_id']

        try:
            # Get bid
            bid = Bid.objects.get(id=bid_id)

            # Verify user is the job owner
            job_service = JobService()
            job_data = job_service.get_job_details(bid.job_id)

            if not job_data or job_data.get('client_info', {}).get('id') != request.user.user_id:
                return Response(
                    {"error": "You don't have permission to make payment for this bid"},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Create payment record
            payment = Payment.objects.create(
                bid=bid,
                amount=bid.total_amount,
                currency='INR',
                client_id=request.user.user_id,
                freelancer_id=bid.freelancer_id,
                description=f"Payment for project: {job_data.get('title', 'Project')}",
                notes={
                    'bid_id': str(bid.id),
                    'job_id': bid.job_id,
                    'freelancer_id': bid.freelancer_id
                }
            )

            # Create Razorpay order
            razorpay_service = RazorpayPaymentService()
            order_result = razorpay_service.create_order(
                amount=payment.amount,
                currency=payment.currency,
                receipt=payment.receipt_number,
                notes=payment.notes
            )

            if not order_result['success']:
                payment.mark_failed(order_result.get('error', 'Failed to create order'))
                return Response(
                    {"error": "Failed to create payment order"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Update payment with Razorpay order ID
            payment.razorpay_order_id = order_result['order_id']
            payment.status = 'processing'
            payment.payment_data = order_result
            payment.save()

            return Response({
                'success': True,
                'payment_id': str(payment.id),
                'order_id': order_result['order_id'],
                'amount': float(payment.amount),
                'currency': payment.currency,
                'razorpay_key': settings.RAZORPAY_KEY_ID,
                'receipt': payment.receipt_number,
                'notes': payment.notes
            }, status=status.HTTP_201_CREATED)

        except Bid.DoesNotExist:
            return Response(
                {"error": "Bid not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error creating payment order: {str(e)}")
            return Response(
                {"error": "Failed to create payment order"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class VerifyPaymentView(APIView):
    """Verify Razorpay payment"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = VerifyPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data

        try:
            # Get payment
            payment = Payment.objects.get(id=data['payment_id'])

            # Verify user has permission
            if payment.client_id != request.user.user_id:
                return Response(
                    {"error": "You don't have permission to verify this payment"},
                    status=status.HTTP_403_FORBIDDEN
                )

            # Verify signature
            razorpay_service = RazorpayPaymentService()
            is_valid = razorpay_service.verify_payment_signature(
                data['razorpay_order_id'],
                data['razorpay_payment_id'],
                data['razorpay_signature']
            )

            if not is_valid:
                payment.mark_failed("Invalid payment signature")
                return Response(
                    {"error": "Payment verification failed"},
                    status=status.HTTP_400_BAD_REQUEST
                )

            # Get payment details from Razorpay
            payment_details = razorpay_service.get_payment_details(data['razorpay_payment_id'])

            if not payment_details['success']:
                payment.mark_failed("Failed to fetch payment details")
                return Response(
                    {"error": "Failed to verify payment"},
                    status=status.HTTP_500_INTERNAL_SERVER_ERROR
                )

            # Update payment record
            payment.razorpay_payment_id = data['razorpay_payment_id']
            payment.razorpay_signature = data['razorpay_signature']
            payment.payment_data = payment_details['payment']
            payment.payment_method = payment_details['payment'].get('method', 'razorpay')
            payment.mark_completed()

            # Send notifications
            try:
                notification_client.send_payment_success_notification(payment, payment.bid)
            except Exception as e:
                logger.error(f"Failed to send payment notification: {str(e)}")

            return Response({
                'success': True,
                'message': 'Payment verified successfully',
                'payment_id': str(payment.id),
                'status': payment.status,
                'amount': float(payment.amount),
                'receipt_number': payment.receipt_number
            }, status=status.HTTP_200_OK)

        except Payment.DoesNotExist:
            return Response(
                {"error": "Payment not found"},
                status=status.HTTP_404_NOT_FOUND
            )
        except Exception as e:
            logger.error(f"Error verifying payment: {str(e)}")
            return Response(
                {"error": "Payment verification failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PaymentDetailsView(APIView):
    """Get payment details"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, payment_id):
        try:
            payment = Payment.objects.select_related('bid').get(id=payment_id)

            # Verify user has permission
            if payment.client_id != request.user.user_id and payment.freelancer_id != request.user.user_id:
                return Response(
                    {"error": "You don't have permission to view this payment"},
                    status=status.HTTP_403_FORBIDDEN
                )

            serializer = PaymentSerializer(payment)
            return Response(serializer.data)

        except Payment.DoesNotExist:
            return Response(
                {"error": "Payment not found"},
                status=status.HTTP_404_NOT_FOUND
            )


class BidPaymentsListView(APIView):
    """List all payments for a bid"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request, bid_id):
        try:
            bid = Bid.objects.get(id=bid_id)

            # Verify user has permission
            job_service = JobService()
            job_data = job_service.get_job_details(bid.job_id)

            # if (bid.freelancer_id != request.user.user_id and
            #         job_data.get('client_info', {}).get('id') != request.user.user_id):
            #     return Response(
            #         {"error": "You don't have permission to view payments for this bid"},
            #         status=status.HTTP_403_FORBIDDEN
            #     )

            payments = Payment.objects.filter(bid=bid).order_by('-created_at')
            serializer = PaymentSerializer(payments, many=True)

            return Response(serializer.data)

        except Bid.DoesNotExist:
            return Response(
                {"error": "Bid not found"},
                status=status.HTTP_404_NOT_FOUND
            )


class PaymentWebhookView(APIView):
    """Handle Razorpay webhooks"""

    permission_classes = [AllowAny]

    def post(self, request):
        """Handle payment webhooks from Razorpay"""

        try:
            # Verify webhook signature
            webhook_signature = request.headers.get('X-Razorpay-Signature')
            webhook_body = request.body

            # TODO: Implement webhook signature verification
            # razorpay_client.utility.verify_webhook_signature(webhook_body, webhook_signature, webhook_secret)

            data = request.data
            event = data.get('event')

            logger.info(f"Received Razorpay webhook: {event}")

            if event == 'payment.captured':
                # Handle successful payment
                payment_entity = data.get('payload', {}).get('payment', {}).get('entity', {})
                payment_id = payment_entity.get('id')
                order_id = payment_entity.get('order_id')

                # Update payment status
                payment = Payment.objects.filter(razorpay_order_id=order_id).first()
                if payment:
                    payment.razorpay_payment_id = payment_id
                    payment.payment_data = payment_entity
                    payment.mark_completed()

                    logger.info(f"Payment {payment.id} marked as completed via webhook")

            elif event == 'payment.failed':
                # Handle failed payment
                payment_entity = data.get('payload', {}).get('payment', {}).get('entity', {})
                order_id = payment_entity.get('order_id')
                error_description = payment_entity.get('error_description', 'Payment failed')

                payment = Payment.objects.filter(razorpay_order_id=order_id).first()
                if payment:
                    payment.mark_failed(error_description)
                    logger.info(f"Payment {payment.id} marked as failed via webhook")

            return Response({'status': 'ok'}, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error processing webhook: {str(e)}")
            return Response(
                {"error": "Webhook processing failed"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ClientAcceptedBidsView(generics.ListAPIView):
    """Get all accepted bids for a client"""

    serializer_class = BidListSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsClient]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        client_id = self.request.user.user_id

        # Get all jobs for this client
        job_service = JobService()
        client_jobs = job_service.get_client_jobs(client_id)
        job_ids = [job['id'] for job in client_jobs]

        # Get all accepted bids for these jobs
        queryset = Bid.objects.filter(
            job_id__in=job_ids,
            status='accepted'
        ).select_related().prefetch_related('milestones', 'attachments', 'payments')

        return queryset.order_by('-accepted_at', '-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Enrich with job and freelancer details
        job_service = JobService()

        for bid in queryset:
            # Add job details
            job_data = job_service.get_job_details(bid.job_id)
            if job_data:
                bid.job_title = job_data.get('title', '')
                bid.job_budget = job_data.get('budget_display', '')

            # Update freelancer profile
            profile = FreelancerBidProfile.objects.filter(
                freelancer_id=bid.freelancer_id
            ).first()

            if not profile or not profile.is_cache_valid():
                profile = update_freelancer_profile_cache(bid.freelancer_id)

            bid.freelancer_profile = profile

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


# ============= Add to bids/views.py =============

class FreelancerAcceptedBidsView(generics.ListAPIView):
    """Get all accepted bids for a freelancer"""

    serializer_class = FreelancerAcceptedBidSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsFreelancer]
    pagination_class = StandardResultsSetPagination

    def get_queryset(self):
        freelancer_id = self.request.user.user_id

        # Get all accepted bids for this freelancer
        queryset = Bid.objects.filter(
            freelancer_id=freelancer_id,
            status='accepted'
        ).select_related().prefetch_related('milestones', 'attachments', 'payments')

        return queryset.order_by('-accepted_at', '-created_at')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())

        # Enrich with job and client details
        job_service = JobService()
        user_service = UserService()

        for bid in queryset:
            # Add job details
            job_data = job_service.get_job_details(bid.job_id)
            if job_data:
                bid.job_title = job_data.get('title', '')
                bid.job_description = job_data.get('description', '')
                bid.job_budget = job_data.get('budget_display', '')

                # Get client details
                client_id = job_data.get('client_info', {}).get('id')
                if client_id:
                    client_data = user_service.get_user_profile(client_id)
                    if client_data:
                        bid.client_name = f"{client_data.get('first_name', '')} {client_data.get('last_name', '')}".strip()
                        bid.client_email = client_data.get('email', '')
                        bid.client_location = client_data.get('location', '')

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class FreelancerDashboardStatsView(APIView):
    """Get freelancer dashboard statistics"""

    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated, IsFreelancer]

    def get(self, request):
        freelancer_id = request.user.user_id

        # Get all bids
        all_bids = Bid.objects.filter(freelancer_id=freelancer_id)
        accepted_bids = all_bids.filter(status='accepted')

        # Get payment statistics
        from django.db.models import Sum, Count, Q

        payment_stats = Payment.objects.filter(
            freelancer_id=freelancer_id,
            status='completed'
        ).aggregate(
            total_earnings=Sum('amount'),
            payment_count=Count('id')
        )

        # Pending payments
        pending_payments = accepted_bids.filter(
            payments__isnull=True
        ).aggregate(
            pending_amount=Sum('total_amount')
        )

        # Success rate
        total_bids = all_bids.count()
        acceptance_rate = (accepted_bids.count() / total_bids * 100) if total_bids > 0 else 0

        # Recent activity
        recent_accepted = accepted_bids.order_by('-accepted_at')[:5]
        recent_activity = []

        job_service = JobService()
        for bid in recent_accepted:
            job_data = job_service.get_job_details(bid.job_id)
            has_payment = bid.payments.filter(status='completed').exists()

            recent_activity.append({
                'bid_id': str(bid.id),
                'job_id': bid.job_id,
                'job_title': job_data.get('title', '') if job_data else '',
                'amount': float(bid.total_amount or 0),
                'accepted_at': bid.accepted_at,
                'has_payment': has_payment,
                'payment_status': 'received' if has_payment else 'pending'
            })

        return Response({
            'total_bids': total_bids,
            'accepted_bids': accepted_bids.count(),
            'acceptance_rate': round(acceptance_rate, 2),
            'total_earnings': float(payment_stats['total_earnings'] or 0),
            'payment_count': payment_stats['payment_count'],
            'pending_payments': float(pending_payments['pending_amount'] or 0),
            'recent_activity': recent_activity
        })

