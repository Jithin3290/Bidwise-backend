# jobs/views.py
import logging
from django.db.models import Avg, F, Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import filters, generics, status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .authentication import JWTAuthentication
from .models import Job, JobAttachment, JobCategory, JobSave, JobView, Skill
from .serializers import (
    JobAttachmentSerializer, JobCategorySerializer,
    JobCreateUpdateSerializer, JobDetailSerializer,
    JobListSerializer, JobSaveSerializer,
    JobStatsSerializer, JobStatusUpdateSerializer,
    SkillSerializer
)
from .services import user_service

logger = logging.getLogger(__name__)


# ================= PAGINATION =================
class CustomPageNumberPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


# ================= PUBLIC ENDPOINTS =================
class JobCategoryListView(generics.ListAPIView):
    queryset = JobCategory.objects.filter(is_active=True)
    serializer_class = JobCategorySerializer
    pagination_class = None


class SkillListView(generics.ListAPIView):
    queryset = Skill.objects.filter(is_active=True)
    serializer_class = SkillSerializer
    filter_backends = [filters.SearchFilter]
    search_fields = ["name", "category"]
    pagination_class = None


class JobListView(generics.ListAPIView):
    serializer_class = JobListSerializer
    pagination_class = CustomPageNumberPagination

    def get_queryset(self):
        queryset = Job.objects.filter(status="published") \
            .select_related("category") \
            .prefetch_related("skills")

        # Filters
        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) |
                Q(description__icontains=search) |
                Q(search_keywords__icontains=search.lower())
            )

        category = self.request.query_params.get("category")
        if category:
            queryset = queryset.filter(category_id=category)

        job_type = self.request.query_params.get("job_type")
        if job_type:
            queryset = queryset.filter(job_type=job_type)

        experience_level = self.request.query_params.get("experience_level")
        if experience_level:
            queryset = queryset.filter(experience_level=experience_level)

        skills = self.request.query_params.get("skills")
        if skills:
            skill_list = [s.strip() for s in skills.split(",")]
            queryset = queryset.filter(skills__name__in=skill_list).distinct()

        min_budget = self.request.query_params.get("min_budget")
        max_budget = self.request.query_params.get("max_budget")
        if min_budget:
            queryset = queryset.filter(
                Q(budget_min__gte=min_budget) | Q(hourly_rate_min__gte=min_budget)
            )
        if max_budget:
            queryset = queryset.filter(
                Q(budget_max__lte=max_budget) | Q(hourly_rate_max__lte=max_budget)
            )

        if self.request.query_params.get("remote_only", "").lower() == "true":
            queryset = queryset.filter(remote_allowed=True)

        location = self.request.query_params.get("location")
        if location:
            queryset = queryset.filter(location__icontains=location)

        if self.request.query_params.get("featured_only", "").lower() == "true":
            queryset = queryset.filter(is_featured=True)

        ordering = self.request.query_params.get("ordering", "-created_at")
        valid_orderings = [
            "created_at", "-created_at",
            "budget_min", "-budget_min",
            "deadline", "-deadline",
            "views_count", "-views_count",
            "applications_count", "-applications_count",
        ]
        if ordering in valid_orderings:
            queryset = queryset.order_by(ordering)

        return queryset

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            # Batch fetch user info for all jobs on this page
            user_ids = [job.client_id for job in page]
            users_data = user_service.get_users_batch(user_ids)

            for job in page:
                job.client_info = users_data.get(str(job.client_id))

            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        # For non-paginated case
        user_ids = [job.client_id for job in queryset]
        users_data = user_service.get_users_batch(user_ids)

        for job in queryset:
            job.client_info = users_data.get(str(job.client_id))

        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)


class JobDetailView(generics.RetrieveAPIView):
    serializer_class = JobDetailSerializer
    lookup_field = "id"

    def get_queryset(self):
        return Job.objects.select_related("category").prefetch_related(
            "skills", "attachments", "milestones"
        )

    def retrieve(self, request, *args, **kwargs):
        job = self.get_object()
        self._track_job_view(job, request)
        Job.objects.filter(id=job.id).update(views_count=F("views_count") + 1)

        # Use UserService to get client info
        job.client_info = user_service.get_user_profile(job.client_id)

        return Response(self.get_serializer(job).data)

    def _track_job_view(self, job, request):
        try:
            JobView.objects.create(
                job=job,
                viewer_id=getattr(request, "user_id", None),
                ip_address=self._get_client_ip(request),
                user_agent=request.META.get("HTTP_USER_AGENT", ""),
                referrer=request.META.get("HTTP_REFERER", ""),
            )
        except Exception as e:
            logger.error(f"Error tracking job view: {e}")

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
        return x_forwarded_for.split(",")[0] if x_forwarded_for else request.META.get("REMOTE_ADDR")


# ================= CLIENT ENDPOINTS (AUTHENTICATED) =================
class ClientJobListView(generics.ListAPIView):
    serializer_class = JobListSerializer
    pagination_class = CustomPageNumberPagination
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        client_id = self.request.user.user_id
        queryset = Job.objects.filter(client_id=client_id) \
            .select_related("category") \
            .prefetch_related("skills")

        status_filter = self.request.query_params.get("status")
        if status_filter:
            queryset = queryset.filter(status=status_filter)

        search = self.request.query_params.get("search")
        if search:
            queryset = queryset.filter(
                Q(title__icontains=search) | Q(description__icontains=search)
            )

        return queryset.order_by("-created_at")


class ClientJobCreateView(generics.CreateAPIView):
    serializer_class = JobCreateUpdateSerializer
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def perform_create(self, serializer):
        client_id = self.request.user.user_id
        job = serializer.save(client_id=client_id)
        if job.status == "published":
            job.published_at = timezone.now()
            job.save()


class ClientJobDetailView(generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "id"
    authentication_classes = [JWTAuthentication]
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return Job.objects.filter(client_id=self.request.user.user_id)

    def get_serializer_class(self):
        return JobDetailSerializer if self.request.method == "GET" else JobCreateUpdateSerializer

    def retrieve(self, request, *args, **kwargs):
        job = self.get_object()
        job.client_info = user_service.get_user_profile(job.client_id)
        return Response(self.get_serializer(job).data)


# ================= FUNCTION-BASED ENDPOINTS =================
class UpdateJobStatusView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def patch(self, request, job_id):
        client_id = request.user.user_id
        job = get_object_or_404(Job, id=job_id, client_id=client_id)
        old_status = job.status
        serializer = JobStatusUpdateSerializer(job, data=request.data, partial=True)
        if serializer.is_valid():
            new_status = serializer.validated_data["status"]
            if new_status == "published" and old_status == "draft":
                job.published_at = timezone.now()
            elif new_status in ["completed", "cancelled"]:
                job.closed_at = timezone.now()
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class JobAttachmentUploadView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request, job_id):
        client_id = request.user.user_id
        job = get_object_or_404(Job, id=job_id, client_id=client_id)

        if "file" not in request.FILES:
            return Response({"error": "No file provided"}, status=status.HTTP_400_BAD_REQUEST)

        file = request.FILES["file"]
        if file.size > 10 * 1024 * 1024:
            return Response({"error": "File size exceeds 10MB limit"}, status=status.HTTP_400_BAD_REQUEST)

        attachment = JobAttachment.objects.create(
            job=job,
            file=file,
            filename=file.name,
            file_size=file.size,
            file_type=file.content_type,
            description=request.data.get("description", ""),
        )
        serializer = JobAttachmentSerializer(attachment, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class JobAttachmentDeleteView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def delete(self, request, job_id, attachment_id):
        client_id = request.user.user_id
        job = get_object_or_404(Job, id=job_id, client_id=client_id)
        attachment = get_object_or_404(JobAttachment, id=attachment_id, job=job)
        if attachment.file:
            attachment.file.delete()
        attachment.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ClientJobStatsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        client_id = request.user.user_id
        jobs = Job.objects.filter(client_id=client_id)
        stats = {
            "total_jobs": jobs.count(),
            "published_jobs": jobs.filter(status="published").count(),
            "draft_jobs": jobs.filter(status="draft").count(),
            "in_progress_jobs": jobs.filter(status="in_progress").count(),
            "completed_jobs": jobs.filter(status="completed").count(),
            "cancelled_jobs": jobs.filter(status="cancelled").count(),
            "total_views": jobs.aggregate(total=Sum("views_count"))["total"] or 0,
            "total_applications": jobs.aggregate(total=Sum("applications_count"))["total"] or 0,
            "average_budget": jobs.filter(budget_max__isnull=False).aggregate(avg=Avg("budget_max"))["avg"] or 0,
            "recent_activity": [
                {
                    "id": str(job.id),
                    "title": job.title,
                    "status": job.status,
                    "updated_at": job.updated_at,
                    "views_count": job.views_count,
                    "applications_count": job.applications_count,
                }
                for job in jobs.order_by("-updated_at")[:5]
            ],
        }
        return Response(JobStatsSerializer(stats).data)


class JobApplicationsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request, job_id):
        client_id = request.user.user_id
        get_object_or_404(Job, id=job_id, client_id=client_id)
        return Response({"results": [], "count": 0})


# ================= JOB SAVE/BOOKMARK =================
class JobSaveView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request, job_id):
        user_id = request.user.user_id
        job = get_object_or_404(Job, id=job_id, status="published")
        job_save, created = JobSave.objects.get_or_create(job=job, user_id=user_id)
        if created:
            Job.objects.filter(id=job.id).update(saves_count=F("saves_count") + 1)
            return Response({"message": "Job saved successfully"}, status=status.HTTP_201_CREATED)
        return Response({"message": "Job already saved"}, status=status.HTTP_200_OK)

    def delete(self, request, job_id):
        user_id = request.user.user_id
        job = get_object_or_404(Job, id=job_id)
        try:
            job_save = JobSave.objects.get(job=job, user_id=user_id)
            job_save.delete()
            Job.objects.filter(id=job.id).update(saves_count=F("saves_count") - 1)
            return Response({"message": "Job removed from saved"}, status=status.HTTP_204_NO_CONTENT)
        except JobSave.DoesNotExist:
            return Response({"message": "Job was not saved"}, status=status.HTTP_404_NOT_FOUND)


class SavedJobsListView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def get(self, request):
        user_id = request.user.user_id
        saved_jobs = JobSave.objects.filter(user_id=user_id) \
            .select_related("job__category") \
            .prefetch_related("job__skills")
        jobs = [save.job for save in saved_jobs if save.job.status == "published"]

        # Batch fetch client info for all jobs
        user_ids = [job.client_id for job in jobs]
        users_data = user_service.get_users_batch(user_ids)
        for job in jobs:
            job.client_info = users_data.get(str(job.client_id))

        serializer = JobListSerializer(jobs, many=True, context={"request": request})
        return Response(serializer.data)


# ================= HEALTH CHECK =================
class HealthCheckView(APIView):
    def get(self, request):
        return Response({
            "status": "healthy",
            "service": "jobs-service",
            "timestamp": timezone.now(),
            "version": "1.0.0",
        })
