# services/scoring_engine.py - AI-Powered Scoring Engine (Async)

from typing import Dict, Optional
import logging
import google.generativeai as genai
from config import get_settings
from database import fetch_one
from services.cache import get_cache

logger = logging.getLogger(__name__)


class FreelancerScoringEngine:
    """AI-powered scoring using Gemini - Async version"""

    def __init__(self):
        settings = get_settings()
        genai.configure(api_key=settings.GEMINI_API_KEY)
        self.model = genai.GenerativeModel(settings.AI_MODEL_NAME)
        self.cache = get_cache(ttl=settings.CACHE_TTL)

        self.weights = {
            'experience': 0.20,
            'education': 0.15,
            'reviews': 0.25,
            'completion': 0.20,
            'responsiveness': 0.10,
            'skills': 0.10
        }

    async def get_user_data_from_db(self, user_id: int) -> Dict:
        """Fetch user data directly from database using async queries"""
        
        # Get user basic info
        user_query = """
            SELECT id, username, email, profile_completion_percentage
            FROM users
            WHERE id = :user_id
        """
        user_row = await fetch_one(user_query, {"user_id": user_id})
        
        if not user_row:
            raise Exception(f"User {user_id} not found")

        # Get freelancer profile
        freelancer_query = """
            SELECT 
                years_of_experience,
                skills,
                average_rating,
                total_reviews,
                total_projects_completed,
                experience_level
            FROM freelancer_profiles
            WHERE user_id = :user_id
        """
        freelancer_row = await fetch_one(freelancer_query, {"user_id": user_id})

        if not freelancer_row:
            raise Exception(f"User {user_id} is not a freelancer")

        years_exp = freelancer_row['years_of_experience']
        skills = freelancer_row['skills']
        avg_rating = freelancer_row['average_rating']
        total_reviews = freelancer_row['total_reviews']
        total_projects = freelancer_row['total_projects_completed']
        exp_level = freelancer_row['experience_level']

        # Get education level
        education_query = """
            SELECT degree
            FROM user_education ue
            JOIN freelancer_profiles fp ON ue.freelancer_profile_id = fp.id
            WHERE fp.user_id = :user_id
            ORDER BY ue.end_date DESC NULLS FIRST
            LIMIT 1
        """
        education_row = await fetch_one(education_query, {"user_id": user_id})
        education_level = self._infer_education_from_degree(
            education_row['degree'] if education_row else None
        )

        return {
            'user_id': user_row['id'],
            'username': user_row['username'],
            'email': user_row['email'],
            'years_experience': years_exp or 0,
            'skills': skills or [],
            'average_rating': float(avg_rating or 0),
            'total_reviews': total_reviews or 0,
            'total_projects': total_projects or 0,
            'completion_rate': self._calculate_completion_rate(total_projects or 0),
            'avg_response_hours': 12.0,  # Default
            'education_level': education_level,
            'profile_completion': user_row['profile_completion_percentage'] or 0,
        }

    def _infer_education_from_degree(self, degree: Optional[str]) -> str:
        """Infer education level from degree name"""
        if not degree:
            return 'none'

        degree_lower = degree.lower()
        if 'phd' in degree_lower or 'doctor' in degree_lower:
            return 'phd'
        elif 'master' in degree_lower or 'msc' in degree_lower or 'mba' in degree_lower:
            return 'masters'
        elif 'bachelor' in degree_lower or 'bsc' in degree_lower or 'ba' in degree_lower:
            return 'bachelors'
        elif 'associate' in degree_lower or 'diploma' in degree_lower:
            return 'associate'
        else:
            return 'self-taught'

    def _calculate_completion_rate(self, total_projects: int) -> float:
        """Calculate completion rate based on projects"""
        if total_projects == 0:
            return 0
        # Assume 95% completion rate for active freelancers
        return 95.0

    def calculate_experience_score(self, years: float) -> float:
        """Score based on years of experience (0-100)"""
        if years <= 2:
            return years * 20
        elif years <= 5:
            return 40 + (years - 2) * 10
        elif years <= 10:
            return 70 + (years - 5) * 4
        else:
            return min(90 + (years - 10) * 2, 100)

    def calculate_education_score(self, education: str) -> float:
        """Score based on education level"""
        mapping = {
            'phd': 100,
            'masters': 85,
            'bachelors': 70,
            'associate': 50,
            'bootcamp': 60,
            'self-taught': 40,
            'highschool': 30,
            'none': 0
        }
        return mapping.get(education.lower(), 0)

    def calculate_review_score(self, avg_rating: float, total_reviews: int) -> float:
        """Score based on ratings with confidence weighting"""
        if total_reviews == 0:
            return 0

        base_score = (avg_rating / 5.0) * 100

        # Confidence based on review count
        if total_reviews <= 5:
            confidence = 0.5
        elif total_reviews <= 20:
            confidence = 0.75
        elif total_reviews <= 50:
            confidence = 0.9
        else:
            confidence = 1.0

        return base_score * confidence

    def calculate_completion_score(self, completion_rate: float) -> float:
        """Direct conversion"""
        return completion_rate

    def calculate_responsiveness_score(self, avg_response_hours: float) -> float:
        """Score based on response time"""
        if avg_response_hours < 2:
            return 100
        elif avg_response_hours < 6:
            return 90
        elif avg_response_hours < 12:
            return 80
        elif avg_response_hours < 24:
            return 70
        else:
            return max(70 - ((avg_response_hours - 24) / 24) * 5, 0)

    async def calculate_final_score(self, user_id: int, use_cache: bool = True) -> Dict:
        """Calculate comprehensive freelancer score - Async"""

        # Check cache first
        cache_key = f'freelancer_score:{user_id}'
        if use_cache:
            cached = self.cache.get(cache_key)
            if cached:
                logger.info(f"Returning cached score for user {user_id}")
                return cached

        # Fetch user data from database (async)
        user_data = await self.get_user_data_from_db(user_id)

        # Calculate component scores
        scores = {
            'experience': self.calculate_experience_score(user_data['years_experience']),
            'education': self.calculate_education_score(user_data['education_level']),
            'reviews': self.calculate_review_score(
                user_data['average_rating'],
                user_data['total_reviews']
            ),
            'completion': self.calculate_completion_score(user_data['completion_rate']),
            'responsiveness': self.calculate_responsiveness_score(user_data['avg_response_hours']),
            'skills': 0  # Calculated per-job
        }

        # Calculate weighted final score
        final_score = sum(scores[key] * self.weights[key] for key in scores)

        result = {
            'user_id': user_id,
            'final_score': round(final_score, 2),
            'tier': self._get_tier(final_score),
            'scores': {k: round(v, 2) for k, v in scores.items()},
            'breakdown': {
                key: round(scores[key] * self.weights[key], 2)
                for key in scores
            },
            'weights': self.weights,
            'user_data': user_data
        }

        # Cache result
        if use_cache:
            self.cache.set(cache_key, result)

        return result

    def _get_tier(self, score: float) -> str:
        """Determine tier based on score"""
        if score >= 90:
            return 'elite'
        elif score >= 80:
            return 'excellent'
        elif score >= 70:
            return 'good'
        elif score >= 50:
            return 'average'
        else:
            return 'new'

    def invalidate_cache(self, user_id: int) -> bool:
        """Invalidate cached score for a user"""
        cache_key = f'freelancer_score:{user_id}'
        return self.cache.delete(cache_key)


# Singleton instance
_scoring_engine: Optional[FreelancerScoringEngine] = None


def get_scoring_engine() -> FreelancerScoringEngine:
    """Get or create the scoring engine instance"""
    global _scoring_engine
    if _scoring_engine is None:
        _scoring_engine = FreelancerScoringEngine()
    return _scoring_engine
