"""
Bid attachment management views
"""
import logging
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from ..models import Bid, BidAttachment
from ..serializers import BidAttachmentSerializer

logger = logging.getLogger(__name__)


class BidAttachmentView(APIView):
    """Upload and delete bid attachments"""
    permission_classes = [IsAuthenticated]

    def post(self, request, bid_id, *args, **kwargs):
        """Upload attachment to a bid"""
        # Validate Bid ownership
        bid = get_object_or_404(Bid, id=bid_id, freelancer_id=request.user.user_id)

        if bid.status != 'pending':
            return Response(
                {"error": "Can only add attachments to pending bids"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if 'file' not in request.FILES:
            return Response(
                {"error": "No file provided"},
                status=status.HTTP_400_BAD_REQUEST
            )

        file = request.FILES['file']
        description = request.data.get('description', '')
        file_type = request.data.get('file_type', 'document')

        # File size validation (10MB limit)
        if file.size > 10 * 1024 * 1024:
            return Response(
                {"error": "File size exceeds 10MB limit"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            attachment = BidAttachment.objects.create(
                bid=bid,
                file=file,
                filename=file.name,
                file_type=file_type,
                file_size=file.size,
                description=description
            )
            serializer = BidAttachmentSerializer(attachment, context={'request': request})
            return Response(serializer.data, status=status.HTTP_201_CREATED)

        except Exception as e:
            logger.error(f"Error creating bid attachment: {e}")
            return Response(
                {"error": "Failed to upload attachment"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

    def delete(self, request, bid_id, attachment_id=None, *args, **kwargs):
        """Delete a bid attachment"""
        # Validate Bid and Attachment
        bid = get_object_or_404(Bid, id=bid_id, freelancer_id=request.user.user_id)
        attachment = get_object_or_404(BidAttachment, id=attachment_id, bid=bid)

        if bid.status != 'pending':
            return Response(
                {"error": "Can only delete attachments from pending bids"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Delete file from storage then DB
        if attachment.file:
            attachment.file.delete()
        attachment.delete()

        return Response(status=status.HTTP_204_NO_CONTENT)