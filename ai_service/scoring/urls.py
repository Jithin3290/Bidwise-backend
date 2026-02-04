# scoring/urls.py

from django.urls import path
from .views import (
    HealthCheckView,
    CalculateScoreView,
    GetScoreView,
    BulkCalculateScoresView,
    TopFreelancersView,
    JobMatchingView,
    GetJobMatchesView,
    IndexFreelancerView,
    BulkIndexFreelancersView,
    StatsView, DeleteFreelancerIndexView, ReindexAllView
)

urlpatterns = [
    path('health/', HealthCheckView.as_view(), name='health'),
    path('calculate/', CalculateScoreView.as_view(), name='calculate_score'),
    path('score/<int:user_id>/', GetScoreView.as_view(), name='get_score'),
    path('bulk-calculate/', BulkCalculateScoresView.as_view(), name='bulk_calculate'),
    path('top-freelancers/', TopFreelancersView.as_view(), name='top_freelancers'),
    path('match-job/', JobMatchingView.as_view(), name='match_job'),
    path('job-matches/<str:job_id>/', GetJobMatchesView.as_view(), name='get_job_matches'),
    path('index-freelancer/', IndexFreelancerView.as_view(), name='index_freelancer'),
    path('bulk-index/', BulkIndexFreelancersView.as_view(), name='bulk_index'),
    path('stats/', StatsView.as_view(), name='stats'),
    path('delete-freelancer/', DeleteFreelancerIndexView.as_view(), name='delete_freelancer'),
    path('reindex-all/', ReindexAllView.as_view(), name='reindex-all'),

]