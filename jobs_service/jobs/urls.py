from django.urls import path
from . import views

app_name = 'jobs'

urlpatterns = [
    # ============= PUBLIC ENDPOINTS =============

    # Categories and Skills
    path('categories/', views.JobCategoryListView.as_view(), name='job-categories'),
    path('skills/', views.SkillListView.as_view(), name='skills-list'),

    # Public Job Listings
    path('', views.JobListView.as_view(), name='job-list'),
    path('<uuid:id>/', views.JobDetailView.as_view(), name='job-detail'),

    # ============= CLIENT MANAGEMENT ENDPOINTS =============

    # Client Job Management
    path('client/jobs/', views.ClientJobListView.as_view(), name='client-job-list'),
    path('client/jobs/create/', views.ClientJobCreateView.as_view(), name='client-job-create'),
    path('client/jobs/<uuid:id>/', views.ClientJobDetailView.as_view(), name='client-job-detail'),

    # Job Status Management
    path('client/jobs/<uuid:job_id>/status/', views.UpdateJobStatusView.as_view(), name='update-job-status'),

    # Job Attachments
    path('client/jobs/<uuid:job_id>/attachments/', views.JobAttachmentUploadView.as_view(),
         name='upload-job-attachment'),
    path('client/jobs/<uuid:job_id>/attachments/<int:attachment_id>/', views.JobAttachmentDeleteView.as_view(),
         name='delete-job-attachment'),

    # Client Analytics
    path('client/stats/', views.ClientJobStatsView.as_view(), name='client-job-stats'),

    # ============= JOB SAVE/BOOKMARK ENDPOINTS =============

    path('save/<uuid:job_id>/', views.JobSaveView.as_view(), name='save-job'),
    path('unsave/<uuid:job_id>/', views.JobSaveView.as_view(), name='unsave-job'),  # DELETE method
    path('saved/', views.SavedJobsListView.as_view(), name='saved-jobs-list'),
    path('client/jobs/<uuid:job_id>/applications/', views.JobApplicationsView.as_view(), name='client-job-applications'),

    # ============= UTILITY ENDPOINTS =============

    path('health/', views.HealthCheckView.as_view(), name='health-check'),
]

