# scoring/views.py

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.core.cache import cache
from .services.scoring_engine import FreelancerScoringEngine
from .models import FreelancerScore, JobMatch
import logging

logger = logging.getLogger(__name__)


class HealthCheckView(APIView):
    """Health check endpoint"""

    def get(self, request):
        return Response({
            'status': 'healthy',
            'service': 'ai-scoring-service',
            'version': '1.0.0'
        })


class CalculateScoreView(APIView):
    """
    Calculate freelancer score
    POST /api/scoring/calculate/
    Body: {"user_id": 123}
    """

    def post(self, request):
        user_id = request.data.get('user_id')

        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            # Initialize scoring engine
            engine = FreelancerScoringEngine()

            # Calculate score
            result = engine.calculate_final_score(user_id)

            # Save to database
            FreelancerScore.objects.update_or_create(
                user_id=user_id,
                defaults={
                    'experience_score': result['scores']['experience'],
                    'education_score': result['scores']['education'],
                    'review_score': result['scores']['reviews'],
                    'completion_score': result['scores']['completion'],
                    'responsiveness_score': result['scores']['responsiveness'],
                    'final_score': result['final_score']
                }
            )

            return Response(result, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error calculating score: {str(e)}")
            return Response(
                {'error': 'Failed to calculate score', 'detail': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class GetScoreView(APIView):
    """
    Get existing freelancer score
    GET /api/scoring/score/{user_id}/
    """

    def get(self, request, user_id):
        try:
            score = FreelancerScore.objects.get(user_id=user_id)

            return Response({
                'user_id': score.user_id,
                'final_score': score.final_score,
                'scores': {
                    'experience': score.experience_score,
                    'education': score.education_score,
                    'reviews': score.review_score,
                    'completion': score.completion_score,
                    'responsiveness': score.responsiveness_score,
                },
                'last_calculated': score.last_calculated,
            })

        except FreelancerScore.DoesNotExist:
            return Response(
                {'error': 'Score not found. Calculate score first.'},
                status=status.HTTP_404_NOT_FOUND
            )


class BulkCalculateScoresView(APIView):
    """
    Calculate scores for multiple freelancers
    POST /api/scoring/bulk-calculate/
    Body: {"user_ids": [1, 2, 3, 4, 5]}
    """

    def post(self, request):
        user_ids = request.data.get('user_ids', [])

        if not user_ids:
            return Response(
                {'error': 'user_ids array is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        results = []
        errors = []

        engine = FreelancerScoringEngine()

        for user_id in user_ids:
            try:
                result = engine.calculate_final_score(user_id)

                # Save to database
                FreelancerScore.objects.update_or_create(
                    user_id=user_id,
                    defaults={
                        'experience_score': result['scores']['experience'],
                        'education_score': result['scores']['education'],
                        'review_score': result['scores']['reviews'],
                        'completion_score': result['scores']['completion'],
                        'responsiveness_score': result['scores']['responsiveness'],
                        'final_score': result['final_score']
                    }
                )

                results.append({
                    'user_id': user_id,
                    'final_score': result['final_score'],
                    'status': 'success'
                })

            except Exception as e:
                logger.error(f"Error calculating score for user {user_id}: {str(e)}")
                errors.append({
                    'user_id': user_id,
                    'error': str(e)
                })

        return Response({
            'results': results,
            'errors': errors,
            'total_processed': len(results),
            'total_errors': len(errors)
        })


class TopFreelancersView(APIView):
    """
    Get top-rated freelancers
    GET /api/scoring/top-freelancers/?limit=10
    """

    def get(self, request):
        limit = int(request.query_params.get('limit', 10))

        scores = FreelancerScore.objects.all().order_by('-final_score')[:limit]

        return Response({
            'freelancers': [
                {
                    'user_id': score.user_id,
                    'final_score': score.final_score,
                    'last_calculated': score.last_calculated
                }
                for score in scores
            ],
            'count': len(scores)
        })
#
#
# class JobMatchingView(APIView):
#     """
#     Find best freelancers for a job using semantic search
#     POST /api/scoring/match-job/
#     Body: {
#         "job_id": "123",
#         "job_description": "Looking for Python developer...",
#         "required_skills": ["python", "django"],
#         "top_k": 10
#     }
#     """
#
#     def post(self, request):
#         job_id = request.data.get('job_id')
#         job_description = request.data.get('job_description', '')
#         required_skills = request.data.get('required_skills', [])
#         top_k = request.data.get('top_k', 10)
#
#         if not job_id:
#             return Response(
#                 {'error': 'job_id is required'},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
#
#         try:
#             # Initialize matcher
#             matcher = SemanticJobMatcher()
#
#             # Perform semantic search
#             matches = matcher.find_best_matches(
#                 job_description=job_description,
#                 required_skills=required_skills,
#                 top_k=top_k
#             )
#
#             # Save matches to database
#             for match in matches:
#                 JobMatch.objects.update_or_create(
#                     job_id=job_id,
#                     user_id=match['user_id'],
#                     defaults={
#                         'semantic_similarity': match['similarity_score'],
#                         'skill_match_percentage': match['skill_match'],
#                         'combined_score': match['combined_score']
#                     }
#                 )
#
#             return Response({
#                 'job_id': job_id,
#                 'matches': matches,
#                 'count': len(matches)
#             })
#
#         except Exception as e:
#             logger.error(f"Error matching job: {str(e)}")
#             return Response(
#                 {'error': 'Failed to match job', 'detail': str(e)},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )


class GetJobMatchesView(APIView):
    """
    Get existing job matches
    GET /api/scoring/job-matches/{job_id}/
    """

    def get(self, request, job_id):
        matches = JobMatch.objects.filter(job_id=job_id).order_by('-combined_score')

        return Response({
            'job_id': job_id,
            'matches': [
                {
                    'user_id': match.user_id,
                    'semantic_similarity': match.semantic_similarity,
                    'skill_match_percentage': match.skill_match_percentage,
                    'combined_score': match.combined_score,
                    'created_at': match.created_at
                }
                for match in matches
            ],
            'count': matches.count()
        })

#
# class IndexFreelancerView(APIView):
#     """
#     Add/update freelancer in vector database
#     POST /api/scoring/index-freelancer/
#     Body: {"user_id": 123}
#     """
#
#     def post(self, request):
#         user_id = request.data.get('user_id')
#
#         if not user_id:
#             return Response(
#                 {'error': 'user_id is required'},
#                 status=status.HTTP_400_BAD_REQUEST
#             )
#
#         try:
#             matcher = SemanticJobMatcher()
#             matcher.index_freelancer(user_id)
#
#             return Response({
#                 'message': f'Freelancer {user_id} indexed successfully',
#                 'user_id': user_id
#             })
#
#         except Exception as e:
#             logger.error(f"Error indexing freelancer: {str(e)}")
#             return Response(
#                 {'error': 'Failed to index freelancer', 'detail': str(e)},
#                 status=status.HTTP_500_INTERNAL_SERVER_ERROR
#             )


class StatsView(APIView):
    """
    Get scoring statistics
    GET /api/scoring/stats/
    """

    def get(self, request):
        from django.db.models import Avg, Count

        stats = FreelancerScore.objects.aggregate(
            total_scores=Count('id'),
            avg_score=Avg('final_score')
        )

        # Score distribution
        elite = FreelancerScore.objects.filter(final_score__gte=90).count()
        excellent = FreelancerScore.objects.filter(final_score__gte=80, final_score__lt=90).count()
        good = FreelancerScore.objects.filter(final_score__gte=70, final_score__lt=80).count()
        average = FreelancerScore.objects.filter(final_score__gte=50, final_score__lt=70).count()
        new = FreelancerScore.objects.filter(final_score__lt=50).count()

        return Response({
            'total_freelancers_scored': stats['total_scores'],
            'average_score': round(stats['avg_score'] or 0, 2),
            'score_distribution': {
                'elite': elite,
                'excellent': excellent,
                'good': good,
                'average': average,
                'new': new
            },
            'total_job_matches': JobMatch.objects.count()
        })


# scoring/views.py - Add these classes

class JobMatchingView(APIView):
    """
    Find best freelancers for a job using semantic search
    POST /api/scoring/match-job/
    """

    def post(self, request):
        job_id = request.data.get('job_id')
        job_description = request.data.get('job_description', '')
        required_skills = request.data.get('required_skills', [])
        top_k = request.data.get('top_k', 10)

        if not job_id:
            return Response(
                {'error': 'job_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from .services.vector_search import SemanticJobMatcher
            matcher = SemanticJobMatcher()

            # Find matches
            matches = matcher.find_best_matches(
                job_description=job_description,
                required_skills=required_skills,
                top_k=top_k
            )

            # Save to database
            for match in matches:
                JobMatch.objects.update_or_create(
                    job_id=job_id,
                    user_id=match['user_id'],
                    defaults={
                        'semantic_similarity': match['similarity_score'],
                        'skill_match_percentage': match['skill_match'],
                        'combined_score': match['combined_score'],
                        'matched_skills': match['matched_skills'],
                        'missing_skills': match['missing_skills']
                    }
                )

            return Response({
                'job_id': job_id,
                'matches': matches,
                'count': len(matches)
            })

        except Exception as e:
            logger.error(f"Error matching job: {str(e)}")
            return Response(
                {'error': 'Failed to match job', 'detail': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class IndexFreelancerView(APIView):
    """Index freelancer in vector database"""

    def post(self, request):
        user_id = request.data.get('user_id')

        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from .services.vector_search import SemanticJobMatcher
            matcher = SemanticJobMatcher()
            matcher.index_freelancer(user_id)

            return Response({
                'message': f'Freelancer {user_id} indexed successfully',
                'user_id': user_id
            })

        except Exception as e:
            logger.error(f"Error indexing: {str(e)}")
            return Response(
                {'error': 'Failed to index freelancer', 'detail': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class BulkIndexFreelancersView(APIView):
    """Bulk index freelancers"""

    def post(self, request):
        user_ids = request.data.get('user_ids', [])

        if not user_ids:
            return Response(
                {'error': 'user_ids array is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from .services.vector_search import SemanticJobMatcher
            matcher = SemanticJobMatcher()
            results = matcher.bulk_index_freelancers(user_ids)

            return Response(results)

        except Exception as e:
            logger.error(f"Bulk indexing error: {str(e)}")
            return Response(
                {'error': 'Failed to bulk index', 'detail': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

class DeleteFreelancerIndexView(APIView):
    """Remove freelancer from vector database"""

    def post(self, request):
        user_id = request.data.get('user_id')

        if not user_id:
            return Response(
                {'error': 'user_id is required'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            from .services.vector_search import SemanticJobMatcher
            matcher = SemanticJobMatcher()
            matcher.delete_freelancer(user_id)

            return Response({
                'message': f'Freelancer {user_id} removed from index',
                'user_id': user_id
            })

        except Exception as e:
            logger.error(f"Error deleting from index: {str(e)}")
            return Response(
                {'error': 'Failed to delete from index', 'detail': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class ReindexAllView(APIView):
    """Re-index all freelancers (clears old data)"""

    def post(self, request):
        try:
            from .services.vector_search import SemanticJobMatcher
            from django.db import connection

            # Get all freelancer user IDs
            with connection.cursor() as cursor:
                cursor.execute("SELECT user_id FROM freelancer_profiles")
                user_ids = [row[0] for row in cursor.fetchall()]

            # Clear old collection
            matcher = SemanticJobMatcher()
            matcher.vectorstore.delete_collection()

            # Recreate collection
            matcher = SemanticJobMatcher()

            # Re-index all
            results = matcher.bulk_index_freelancers(user_ids)

            return Response({
                'message': 'Re-indexed all freelancers',
                'total_users': len(user_ids),
                'results': results
            })

        except Exception as e:
            logger.error(f"Re-indexing error: {str(e)}")
            return Response(
                {'error': str(e)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )