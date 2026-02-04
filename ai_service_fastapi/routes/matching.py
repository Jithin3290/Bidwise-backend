# routes/matching.py - Job Matching API Endpoints

import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from models.schemas import (
    JobMatchRequest,
    JobMatchResponse,
    IndexFreelancerRequest,
    BulkIndexRequest,
    BulkIndexResponse,
    DeleteFreelancerRequest,
    IndexResult,
)
from services.vector_search import get_job_matcher
from rabbitmq.publisher import get_publisher
from database import fetch_all

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scoring", tags=["Job Matching"])


@router.post("/match-job", response_model=JobMatchResponse)
async def match_job(request: JobMatchRequest):
    """
    Find best freelancers for a job using semantic search
    
    POST /api/scoring/match-job/
    Body: {
        "job_id": "123",
        "job_description": "Looking for Python developer...",
        "required_skills": ["Python", "Django", "REST API"],
        "min_years_experience": 2,
        "experience_level": "intermediate",
        "top_k": 10
    }
    """
    try:
        start_time = time.time()
        matcher = get_job_matcher()

        # Use filtered search if filters provided
        if request.min_years_experience or request.experience_level:
            matches = matcher.find_with_filters(
                job_description=request.job_description,
                required_skills=request.required_skills,
                min_years_experience=request.min_years_experience,
                experience_level=request.experience_level.value if request.experience_level else None,
                top_k=request.top_k,
            )
        else:
            matches = matcher.find_best_matches(
                job_description=request.job_description,
                required_skills=request.required_skills,
                top_k=request.top_k,
            )

        processing_time = (time.time() - start_time) * 1000

        # Publish event asynchronously
        publisher = await get_publisher()
        await publisher.publish_matches_found(
            job_id=request.job_id,
            client_id=0,  # Would come from auth context
            matches=matches,
        )

        return JobMatchResponse(
            job_id=request.job_id,
            matches=matches,
            total_matches=len(matches),
            processing_time_ms=round(processing_time, 2),
        )

    except Exception as e:
        logger.error(f"Error matching job {request.job_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to match job", "message": str(e)},
        )


@router.get("/job-matches/{job_id}")
async def get_job_matches(job_id: str, limit: int = Query(10, ge=1, le=50)):
    """
    Get existing job matches from database
    
    GET /api/scoring/job-matches/{job_id}/
    """
    try:
        query = """
            SELECT 
                jm.user_id,
                u.username,
                jm.semantic_similarity,
                jm.skill_match_percentage,
                jm.combined_score,
                jm.created_at
            FROM job_matches jm
            JOIN users u ON jm.user_id = u.id
            WHERE jm.job_id = :job_id
            ORDER BY jm.combined_score DESC
            LIMIT :limit
        """
        rows = await fetch_all(query, {"job_id": job_id, "limit": limit})

        return {
            "job_id": job_id,
            "matches": [
                {
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "similarity_score": float(row["semantic_similarity"]),
                    "skill_match": float(row["skill_match_percentage"]),
                    "combined_score": float(row["combined_score"]),
                }
                for row in rows
            ],
            "total_matches": len(rows),
        }

    except Exception as e:
        logger.error(f"Error fetching job matches for {job_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to fetch job matches", "message": str(e)},
        )


@router.post("/index-freelancer", response_model=IndexResult)
async def index_freelancer(request: IndexFreelancerRequest):
    """
    Add/update freelancer in vector database
    
    POST /api/scoring/index-freelancer/
    Body: {"user_id": 123}
    """
    try:
        matcher = get_job_matcher()
        await matcher.index_freelancer(request.user_id)

        # Publish success event
        publisher = await get_publisher()
        await publisher.publish_freelancer_indexed(request.user_id, success=True)

        return IndexResult(
            user_id=request.user_id,
            status="indexed",
        )

    except Exception as e:
        logger.error(f"Error indexing freelancer {request.user_id}: {e}")
        
        # Publish failure event
        publisher = await get_publisher()
        await publisher.publish_freelancer_indexed(
            request.user_id, success=False, error=str(e)
        )
        
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to index freelancer", "message": str(e)},
        )


@router.post("/bulk-index", response_model=BulkIndexResponse)
async def bulk_index_freelancers(request: BulkIndexRequest):
    """
    Bulk index freelancers
    
    POST /api/scoring/bulk-index/
    Body: {"user_ids": [1, 2, 3, 4, 5]}
    """
    try:
        matcher = get_job_matcher()
        results = await matcher.bulk_index_freelancers(request.user_ids)

        return BulkIndexResponse(
            total=len(request.user_ids),
            success=results["success"],
            errors=results["errors"],
        )

    except Exception as e:
        logger.error(f"Error bulk indexing freelancers: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to bulk index", "message": str(e)},
        )


@router.post("/delete-freelancer", response_model=IndexResult)
async def delete_freelancer_index(request: DeleteFreelancerRequest):
    """
    Remove freelancer from vector database
    
    POST /api/scoring/delete-freelancer/
    Body: {"user_id": 123}
    """
    try:
        matcher = get_job_matcher()
        matcher.delete_freelancer(request.user_id)

        return IndexResult(
            user_id=request.user_id,
            status="deleted",
        )

    except Exception as e:
        logger.error(f"Error deleting freelancer {request.user_id}: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to delete freelancer", "message": str(e)},
        )


@router.post("/reindex-all")
async def reindex_all_freelancers():
    """
    Re-index all freelancers (clears old data)
    
    POST /api/scoring/reindex-all/
    """
    try:
        matcher = get_job_matcher()
        results = await matcher.reindex_all_freelancers()

        return {
            "status": "completed",
            "indexed": len(results["success"]),
            "errors": len(results["errors"]),
            "success_ids": results["success"],
            "error_details": results["errors"],
        }

    except Exception as e:
        logger.error(f"Error reindexing all freelancers: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to reindex", "message": str(e)},
        )


@router.get("/collection-stats")
async def get_collection_stats():
    """
    Get vector store statistics
    
    GET /api/scoring/collection-stats/
    """
    try:
        matcher = get_job_matcher()
        stats = matcher.get_collection_stats()

        return stats

    except Exception as e:
        logger.error(f"Error fetching collection stats: {e}")
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to fetch stats", "message": str(e)},
        )
