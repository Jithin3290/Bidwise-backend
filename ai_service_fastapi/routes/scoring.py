# routes/scoring.py - Scoring API Endpoints

import logging
from datetime import datetime
from typing import List

from fastapi import APIRouter, HTTPException, Query

from models.schemas import (
    CalculateScoreRequest,
    ScoreResponse,
    BulkCalculateRequest,
    BulkScoreResponse,
    BulkScoreResult,
    HealthResponse,
    StatsResponse,
)
from services.scoring_engine import get_scoring_engine
from services.vector_search import get_job_matcher
from services.cache import get_cache
from rabbitmq.connection import get_rabbitmq
from rabbitmq.publisher import get_publisher
from database import database

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scoring", tags=["Scoring"])


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint"""
    rabbitmq = await get_rabbitmq()
    matcher = get_job_matcher()
    
    return HealthResponse(
        status="healthy",
        service="AI Scoring Service",
        database="connected" if database and database.is_connected else "disconnected",
        rabbitmq="connected" if rabbitmq.is_connected else "disconnected",
        chromadb=f"indexed: {matcher.get_collection_stats()['total_indexed']}",
        timestamp=datetime.utcnow(),
    )


@router.post("/calculate")
async def calculate_score(request: CalculateScoreRequest):
    """
    Calculate freelancer score
    
    POST /api/scoring/calculate/
    Body: {"user_id": 123}
    """
    try:
        engine = get_scoring_engine()
        result = await engine.calculate_final_score(request.user_id)
        
        # Publish event
        publisher = await get_publisher()
        await publisher.publish_score_calculated(
            user_id=request.user_id,
            final_score=result["final_score"],
            tier=result["tier"],
        )
        
        return result

    except Exception as e:
        logger.error(f"Error calculating score for user {request.user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to calculate score", "message": str(e)},
        )


@router.get("/score/{user_id}")
async def get_score(user_id: int):
    """
    Get existing freelancer score (from cache or recalculate)
    
    GET /api/scoring/score/{user_id}/
    """
    try:
        engine = get_scoring_engine()
        result = await engine.calculate_final_score(user_id, use_cache=True)
        return result

    except Exception as e:
        logger.error(f"Error getting score for user {user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to get score", "message": str(e)},
        )


@router.post("/bulk-calculate", response_model=BulkScoreResponse)
async def bulk_calculate_scores(request: BulkCalculateRequest):
    """
    Calculate scores for multiple freelancers
    
    POST /api/scoring/bulk-calculate/
    Body: {"user_ids": [1, 2, 3, 4, 5]}
    """
    engine = get_scoring_engine()
    results: List[BulkScoreResult] = []
    successful = 0
    failed = 0

    for user_id in request.user_ids:
        try:
            score_data = await engine.calculate_final_score(user_id, use_cache=False)
            results.append(BulkScoreResult(
                user_id=user_id,
                success=True,
                score=score_data["final_score"],
                tier=score_data["tier"],
            ))
            successful += 1
        except Exception as e:
            results.append(BulkScoreResult(
                user_id=user_id,
                success=False,
                error=str(e),
            ))
            failed += 1

    return BulkScoreResponse(
        total=len(request.user_ids),
        successful=successful,
        failed=failed,
        results=results,
    )


@router.get("/top-freelancers")
async def get_top_freelancers(limit: int = Query(10, ge=1, le=100)):
    """
    Get top-rated freelancers
    
    GET /api/scoring/top-freelancers/?limit=10
    """
    from database import fetch_all

    try:
        query = """
            SELECT 
                fs.user_id,
                fs.final_score,
                fs.tier,
                u.username
            FROM freelancer_scores fs
            JOIN users u ON fs.user_id = u.id
            ORDER BY fs.final_score DESC
            LIMIT :limit
        """
        rows = await fetch_all(query, {"limit": limit})

        return {
            "freelancers": [
                {
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "final_score": float(row["final_score"]),
                    "tier": row["tier"],
                }
                for row in rows
            ],
            "count": len(rows),
        }

    except Exception as e:
        logger.error(f"Error fetching top freelancers: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to fetch top freelancers", "message": str(e)},
        )


@router.get("/stats", response_model=StatsResponse)
async def get_stats():
    """
    Get scoring statistics
    
    GET /api/scoring/stats/
    """
    from database import fetch_one, fetch_all

    try:
        # Get freelancer score stats
        stats_query = """
            SELECT 
                COUNT(*) as total_scored,
                COALESCE(AVG(final_score), 0) as avg_score
            FROM freelancer_scores
        """
        stats_row = await fetch_one(stats_query, {})

        # Get tier distribution
        tier_query = """
            SELECT tier, COUNT(*) as count
            FROM freelancer_scores
            GROUP BY tier
        """
        tier_rows = await fetch_all(tier_query, {})
        tier_distribution = {row["tier"]: row["count"] for row in tier_rows}

        # Get job match count
        match_query = """
            SELECT COUNT(*) as total FROM job_matches
        """
        match_row = await fetch_one(match_query, {})

        # Get indexed freelancers count
        matcher = get_job_matcher()
        indexed_count = matcher.get_collection_stats()["total_indexed"]

        return StatsResponse(
            total_freelancers_scored=stats_row["total_scored"] if stats_row else 0,
            total_job_matches=match_row["total"] if match_row else 0,
            average_score=float(stats_row["avg_score"]) if stats_row else 0,
            tier_distribution=tier_distribution,
            indexed_freelancers=indexed_count,
        )

    except Exception as e:
        logger.error(f"Error fetching stats: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to fetch stats", "message": str(e)},
        )
