# services/vector_search.py - Semantic Job Matcher with ChromaDB

from typing import List, Dict, Optional
import logging
import json

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document

from config import get_settings
from database import fetch_one, fetch_all

logger = logging.getLogger(__name__)


class SemanticJobMatcher:
    """Semantic search for freelancer-job matching using ChromaDB"""

    def __init__(self):
        settings = get_settings()
        
        # Initialize embeddings
        self.embeddings = HuggingFaceEmbeddings(
            model_name=settings.EMBEDDING_MODEL,
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}
        )
        logger.info(f"Loaded embeddings: {settings.EMBEDDING_MODEL}")

        # Initialize ChromaDB vectorstore
        self.vectorstore = Chroma(
            collection_name="freelancers",
            embedding_function=self.embeddings,
            persist_directory=settings.CHROMA_DB_PATH,
            collection_metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"ChromaDB initialized at: {settings.CHROMA_DB_PATH}")

    async def index_freelancer(self, user_id: int) -> None:
        """Index a freelancer in the vector database - Async DB, Sync Chroma"""
        try:
            # Fetch freelancer data from database (async)
            query = """
                SELECT 
                    u.username,
                    u.bio,
                    fp.skills,
                    fp.experience_level,
                    fp.years_of_experience,
                    pp.title
                FROM users u
                JOIN freelancer_profiles fp ON u.id = fp.user_id
                LEFT JOIN user_professional_profiles pp ON u.id = pp.user_id
                WHERE u.id = :user_id
            """
            row = await fetch_one(query, {"user_id": user_id})
            
            if not row:
                raise Exception(f"User {user_id} not found or not a freelancer")

            username = row['username']
            bio = row['bio']
            skills_raw = row['skills']
            exp_level = row['experience_level']
            years_exp = row['years_of_experience']
            title = row['title']

            # Parse skills
            skills = self._parse_skills(skills_raw)
            logger.debug(f"User {user_id} - Parsed skills: {skills}")

            # Create searchable text
            profile_text = f"""
Professional: {title or 'Freelancer'}
Skills: {', '.join(skills) if skills else 'General'}
Experience: {exp_level or 'intermediate'} level with {years_exp or 0} years
Bio: {bio or ''}
            """.strip()

            # Create LangChain Document
            document = Document(
                page_content=profile_text,
                metadata={
                    'user_id': str(user_id),
                    'username': username,
                    'skills': ','.join(skills) if skills else '',
                    'experience_level': exp_level or 'intermediate',
                    'years_experience': years_exp or 0,
                    'title': title or 'Freelancer'
                }
            )

            # Add to vectorstore (sync operation)
            self.vectorstore.add_documents(
                documents=[document],
                ids=[str(user_id)]
            )

            logger.info(f"Indexed freelancer {user_id}")

        except Exception as e:
            logger.error(f"Error indexing freelancer {user_id}: {e}")
            raise

    def _parse_skills(self, skills_raw) -> List[str]:
        """Parse skills from various formats"""
        if isinstance(skills_raw, str):
            try:
                skills = json.loads(skills_raw)
            except (json.JSONDecodeError, TypeError):
                skills = [s.strip() for s in skills_raw.split(',') if s.strip()]
        elif isinstance(skills_raw, list):
            skills = skills_raw
        else:
            skills = []
        return skills

    def find_best_matches(
        self,
        job_description: str,
        required_skills: List[str],
        top_k: int = 10
    ) -> List[Dict]:
        """Find best freelancer matches for a job"""
        
        # DEBUG: Log input parameters
        logger.info(f"=== FIND_BEST_MATCHES DEBUG ===")
        logger.info(f"Job Description: {job_description[:100]}...")
        logger.info(f"Required Skills: {required_skills}")
        logger.info(f"Required Skills Count: {len(required_skills)}")

        # Check if collection has data
        collection = self.vectorstore._collection
        if collection.count() == 0:
            logger.warning("No freelancers indexed yet")
            return []

        # Create search query
        query_text = f"""
Job Requirements: {job_description}
Required Skills: {', '.join(required_skills)}
        """.strip()

        # Perform similarity search (sync)
        results = self.vectorstore.similarity_search_with_score(
            query=query_text,
            k=min(top_k, collection.count())
        )

        if not results:
            return []

        # Format results
        matches = []
        for doc, distance in results:
            user_id = int(doc.metadata.get('user_id'))

            skills_str = doc.metadata.get('skills', '')
            if skills_str and skills_str.strip():
                freelancer_skills = [s.strip() for s in skills_str.split(',') if s.strip()]
            else:
                freelancer_skills = []

            # Convert distance to similarity (0-1)
            similarity = max(0, 1 - distance)

            # Calculate skill match
            skill_match = self._calculate_skill_match(required_skills, freelancer_skills)

            # Combined score (weighted)
            combined_score = (similarity * 0.6) + (skill_match * 0.4)

            # Find matched and missing skills
            matched_skills, missing_skills = self._get_skill_diff(
                required_skills, freelancer_skills
            )

            matches.append({
                'user_id': user_id,
                'username': doc.metadata.get('username', ''),
                'similarity_score': round(similarity, 3),
                'skill_match': round(skill_match * 100, 2),
                'combined_score': round(combined_score * 100, 2),
                'matched_skills': matched_skills,
                'missing_skills': missing_skills,
                'freelancer_skills': freelancer_skills,
                'experience_level': doc.metadata.get('experience_level', ''),
                'years_experience': doc.metadata.get('years_experience', 0)
            })

        # Sort by combined score
        matches.sort(key=lambda x: x['combined_score'], reverse=True)
        return matches

    def find_with_filters(
        self,
        job_description: str,
        required_skills: List[str],
        min_years_experience: Optional[int] = None,
        experience_level: Optional[str] = None,
        top_k: int = 10
    ) -> List[Dict]:
        """Find matches with metadata filters"""

        # Build metadata filter
        filter_dict = {}
        if min_years_experience is not None:
            filter_dict['years_experience'] = {'$gte': min_years_experience}
        if experience_level:
            filter_dict['experience_level'] = experience_level

        query_text = f"""
Job Requirements: {job_description}
Required Skills: {', '.join(required_skills)}
        """.strip()

        # Search with filter
        if filter_dict:
            results = self.vectorstore.similarity_search_with_score(
                query=query_text,
                k=top_k,
                filter=filter_dict
            )
        else:
            results = self.vectorstore.similarity_search_with_score(
                query=query_text,
                k=top_k
            )

        # Format results (same as find_best_matches)
        matches = []
        for doc, distance in results:
            user_id = int(doc.metadata.get('user_id'))
            
            skills_str = doc.metadata.get('skills', '')
            freelancer_skills = [s.strip() for s in skills_str.split(',') if s.strip()] if skills_str else []

            similarity = max(0, 1 - distance)
            skill_match = self._calculate_skill_match(required_skills, freelancer_skills)
            combined_score = (similarity * 0.6) + (skill_match * 0.4)

            matched_skills, missing_skills = self._get_skill_diff(required_skills, freelancer_skills)

            matches.append({
                'user_id': user_id,
                'username': doc.metadata.get('username', ''),
                'similarity_score': round(similarity, 3),
                'skill_match': round(skill_match * 100, 2),
                'combined_score': round(combined_score * 100, 2),
                'matched_skills': matched_skills,
                'missing_skills': missing_skills,
                'freelancer_skills': freelancer_skills,
                'experience_level': doc.metadata.get('experience_level', ''),
                'years_experience': doc.metadata.get('years_experience', 0)
            })

        matches.sort(key=lambda x: x['combined_score'], reverse=True)
        return matches

    def _calculate_skill_match(self, required: List[str], has: List[str]) -> float:
        """Calculate skill match percentage"""
        # DEBUG: Log skill comparison
        logger.debug(f"Skill Match - Required: {required}, Has: {has}")
        
        if not required:
            logger.warning("No required skills provided - returning 100% match")
            return 1.0

        required_set = set(s.lower().strip() for s in required if s and s.strip())
        has_set = set(s.lower().strip() for s in has if s and s.strip())
        
        logger.debug(f"Required Set: {required_set}, Has Set: {has_set}")

        if not required_set:
            logger.warning("Required set is empty after filtering - returning 100% match")
            return 1.0

        matched = len(required_set & has_set)
        match_percentage = matched / len(required_set)
        logger.debug(f"Matched: {matched}/{len(required_set)} = {match_percentage:.2%}")
        return match_percentage

    def _get_skill_diff(
        self, required: List[str], has: List[str]
    ) -> tuple[List[str], List[str]]:
        """Get matched and missing skills"""
        freelancer_lower = set(s.lower().strip() for s in has if s and s.strip())
        
        matched_skills = []
        missing_skills = []

        for req_skill in required:
            if req_skill and req_skill.strip():
                req_lower = req_skill.lower().strip()
                if req_lower in freelancer_lower:
                    matched_skills.append(req_skill)
                else:
                    missing_skills.append(req_skill)

        return matched_skills, missing_skills

    async def bulk_index_freelancers(self, user_ids: List[int]) -> Dict:
        """Bulk index multiple freelancers"""
        results = {'success': [], 'errors': []}

        for user_id in user_ids:
            try:
                await self.index_freelancer(user_id)
                results['success'].append(user_id)
            except Exception as e:
                logger.error(f"Error indexing user {user_id}: {e}")
                results['errors'].append({'user_id': user_id, 'error': str(e)})

        logger.info(f"Bulk indexed: {len(results['success'])} success, {len(results['errors'])} errors")
        return results

    def delete_freelancer(self, user_id: int) -> None:
        """Remove freelancer from vector store"""
        try:
            self.vectorstore.delete(ids=[str(user_id)])
            logger.info(f"Deleted freelancer {user_id} from vector store")
        except Exception as e:
            logger.error(f"Error deleting freelancer {user_id}: {e}")
            raise

    def get_collection_stats(self) -> Dict:
        """Get vector store statistics"""
        collection = self.vectorstore._collection
        return {
            "total_indexed": collection.count(),
            "collection_name": "freelancers"
        }

    async def reindex_all_freelancers(self) -> Dict:
        """Reindex all freelancers from database"""
        
        # Clear existing collection
        collection = self.vectorstore._collection
        try:
            # Get all existing IDs and delete them
            existing = collection.get()
            if existing and existing.get('ids'):
                self.vectorstore.delete(ids=existing['ids'])
                logger.info(f"Cleared {len(existing['ids'])} existing entries")
        except Exception as e:
            logger.warning(f"Could not clear collection: {e}")

        # Fetch all freelancer IDs
        query = """
            SELECT user_id FROM freelancer_profiles
        """
        rows = await fetch_all(query, {})
        user_ids = [row['user_id'] for row in rows]

        # Bulk index
        return await self.bulk_index_freelancers(user_ids)


# Singleton instance
_job_matcher: Optional[SemanticJobMatcher] = None


def get_job_matcher() -> SemanticJobMatcher:
    """Get or create the job matcher instance"""
    global _job_matcher
    if _job_matcher is None:
        _job_matcher = SemanticJobMatcher()
    return _job_matcher
