# models/schemas.py - Pydantic Request/Response Models

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from enum import Enum


# ============ Enums ============

class TierEnum(str, Enum):
    ELITE = "elite"
    EXCELLENT = "excellent"
    GOOD = "good"
    AVERAGE = "average"
    NEW = "new"


class ExperienceLevel(str, Enum):
    ENTRY = "entry"
    INTERMEDIATE = "intermediate"
    SENIOR = "senior"
    EXPERT = "expert"


# ============ Scoring Requests ============

class CalculateScoreRequest(BaseModel):
    user_id: int = Field(..., description="User ID to calculate score for")


class BulkCalculateRequest(BaseModel):
    user_ids: List[int] = Field(..., description="List of user IDs", max_length=100)


# ============ Scoring Responses ============

class ScoreBreakdown(BaseModel):
    experience: float
    education: float
    reviews: float
    completion: float
    responsiveness: float
    skills: float


class ScoreResponse(BaseModel):
    user_id: int
    final_score: float
    tier: TierEnum
    scores: ScoreBreakdown
    breakdown: ScoreBreakdown
    weights: Dict[str, float]
    user_data: Optional[Dict[str, Any]] = None


class BulkScoreResult(BaseModel):
    user_id: int
    success: bool
    score: Optional[float] = None
    tier: Optional[TierEnum] = None
    error: Optional[str] = None


class BulkScoreResponse(BaseModel):
    total: int
    successful: int
    failed: int
    results: List[BulkScoreResult]


# ============ Job Matching Requests ============

class JobMatchRequest(BaseModel):
    job_id: str = Field(..., description="Job identifier")
    job_description: str = Field(..., description="Full job description")
    required_skills: List[str] = Field(..., description="Required skills for the job")
    min_years_experience: Optional[int] = Field(None, ge=0)
    experience_level: Optional[ExperienceLevel] = None
    top_k: int = Field(10, ge=1, le=50, description="Number of matches to return")


# ============ Job Matching Responses ============

class FreelancerMatch(BaseModel):
    user_id: int
    username: str
    similarity_score: float
    skill_match: float
    combined_score: float
    matched_skills: List[str]
    missing_skills: List[str]
    freelancer_skills: List[str]
    experience_level: str
    years_experience: int


class JobMatchResponse(BaseModel):
    job_id: str
    matches: List[FreelancerMatch]
    total_matches: int
    processing_time_ms: Optional[float] = None


# ============ Indexing Requests ============

class IndexFreelancerRequest(BaseModel):
    user_id: int


class BulkIndexRequest(BaseModel):
    user_ids: List[int] = Field(..., max_length=500)


class DeleteFreelancerRequest(BaseModel):
    user_id: int


# ============ Indexing Responses ============

class IndexResult(BaseModel):
    user_id: int
    status: str  # "indexed", "deleted", "error"
    error: Optional[str] = None


class BulkIndexResponse(BaseModel):
    total: int
    success: List[int]
    errors: List[Dict[str, Any]]


# ============ Stats Response ============

class StatsResponse(BaseModel):
    total_freelancers_scored: int
    total_job_matches: int
    average_score: float
    tier_distribution: Dict[str, int]
    indexed_freelancers: int


# ============ Health Response ============

class HealthResponse(BaseModel):
    status: str
    service: str
    database: str
    rabbitmq: str
    chromadb: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============ RabbitMQ Event Schemas ============

class FreelancerRegisteredEvent(BaseModel):
    """Event published when a freelancer registers"""
    event_type: str = "freelancer.registered"
    user_id: int
    username: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class FreelancerUpdatedEvent(BaseModel):
    """Event published when a freelancer updates their profile"""
    event_type: str = "freelancer.updated"
    user_id: int
    updated_fields: List[str]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class JobPostedEvent(BaseModel):
    """Event received when a job is posted"""
    event_type: str = "job.posted"
    job_id: str
    client_id: int
    job_description: str
    required_skills: List[str]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ScoreCalculatedEvent(BaseModel):
    """Event published when a score is calculated"""
    event_type: str = "score.calculated"
    user_id: int
    final_score: float
    tier: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MatchesFoundEvent(BaseModel):
    """Event published when job matches are found"""
    event_type: str = "matches.found"
    job_id: str
    client_id: int
    match_count: int
    top_user_ids: List[int]
    timestamp: datetime = Field(default_factory=datetime.utcnow)
