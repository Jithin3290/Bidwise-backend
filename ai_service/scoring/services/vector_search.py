# scoring/services/vector_search.py

from typing import List, Dict
import logging
from django.conf import settings
from django.db import connection
import json

from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain.docstore.document import Document
from langchain.text_splitter import RecursiveCharacterTextSplitter

logger = logging.getLogger(__name__)


class SemanticJobMatcher:

    def __init__(self):

        self.embeddings = HuggingFaceEmbeddings(
            model_name='sentence-transformers/all-MiniLM-L6-v2',
            model_kwargs={'device': 'cpu'},
            encode_kwargs={'normalize_embeddings': True}  # For cosine similarity
        )

        logger.info(f"Loaded LangChain embeddings: {self.embeddings.model_name}")

        self.vectorstore = Chroma(
            collection_name="freelancers",
            embedding_function=self.embeddings,
            persist_directory=settings.CHROMA_DB_PATH,
            collection_metadata={"hnsw:space": "cosine"}
        )

        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )

        logger.info("SemanticJobMatcher initialized with LangChain")

    def index_freelancer(self, user_id: int):

        try:
            # Fetch freelancer data from database
            with connection.cursor() as cursor:
                cursor.execute("""
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
                    WHERE u.id = %s
                """, [user_id])

                row = cursor.fetchone()
                if not row:
                    raise Exception(f"User {user_id} not found or not a freelancer")

                username, bio, skills_raw, exp_level, years_exp, title = row

            # Parse skills - handle both JSON string and Python list
            if isinstance(skills_raw, str):
                try:
                    # Try to parse as JSON first
                    skills = json.loads(skills_raw)
                except (json.JSONDecodeError, TypeError):
                    # If not JSON, treat as comma-separated string
                    skills = [s.strip() for s in skills_raw.split(',') if s.strip()]
            elif isinstance(skills_raw, list):
                skills = skills_raw
            else:
                skills = []

            logger.debug(f"User {user_id} - Raw skills from DB: {skills_raw}")
            logger.debug(f"User {user_id} - Parsed skills: {skills}")

            # Create searchable text
            profile_text = f"""
Professional: {title or 'Freelancer'}
Skills: {', '.join(skills) if skills else 'General'}
Experience: {exp_level or 'intermediate'} level with {years_exp or 0} years
Bio: {bio or ''}
            """.strip()

            # Create LangChain Document object
            # Document = text content + metadata for filtering
            document = Document(
                page_content=profile_text,
                metadata={
                    'user_id': str(user_id),
                    'username': username,
                    'skills': ','.join(skills) if skills else '',  # Store as comma-separated
                    'experience_level': exp_level or 'intermediate',
                    'years_experience': years_exp or 0,
                    'title': title or 'Freelancer'
                }
            )

            self.vectorstore.add_documents(
                documents=[document],
                ids=[str(user_id)]
            )

            logger.info(f"Indexed freelancer {user_id} via LangChain")

        except Exception as e:
            logger.error(f"Error indexing freelancer {user_id}: {e}")
            raise

    def find_best_matches(self,
                          job_description: str,
                          required_skills: List[str],
                          top_k: int = 10) -> List[Dict]:


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

            logger.debug(f"User {user_id} - Raw skills string: '{skills_str}'")
            logger.debug(f"User {user_id} - Parsed skills: {freelancer_skills}")

            # Convert distance to similarity (0-1)
            # Chroma returns L2 distance, convert to similarity
            similarity = max(0, 1 - distance)

            # Calculate skill match (case-insensitive)
            skill_match = self._calculate_skill_match(required_skills, freelancer_skills)

            # Combined score (weighted)
            combined_score = (similarity * 0.6) + (skill_match * 0.4)

            # Normalize skill names for matching (case-insensitive)
            required_lower = set(s.lower().strip() for s in required_skills if s and s.strip())
            freelancer_lower = set(s.lower().strip() for s in freelancer_skills if s and s.strip())

            # Find matched and missing skills (preserve original case from required_skills)
            matched_skills = []
            missing_skills = []

            for req_skill in required_skills:
                if req_skill and req_skill.strip():
                    req_lower = req_skill.lower().strip()
                    if req_lower in freelancer_lower:
                        matched_skills.append(req_skill)
                    else:
                        missing_skills.append(req_skill)

            matches.append({
                'user_id': user_id,
                'username': doc.metadata.get('username', ''),
                'similarity_score': round(similarity, 3),
                'skill_match': round(skill_match * 100, 2),
                'combined_score': round(combined_score * 100, 2),
                'matched_skills': matched_skills,
                'missing_skills': missing_skills,
                'freelancer_skills': freelancer_skills,  # Add this to see what's stored
                'experience_level': doc.metadata.get('experience_level', ''),
                'years_experience': doc.metadata.get('years_experience', 0)
            })

        # Sort by combined score
        matches.sort(key=lambda x: x['combined_score'], reverse=True)

        return matches

    def find_with_filters(self,
                          job_description: str,
                          required_skills: List[str],
                          min_years_experience: int = None,
                          experience_level: str = None,
                          top_k: int = 10) -> List[Dict]:


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
                filter=filter_dict  # LangChain metadata filtering
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

            # Parse skills from metadata properly
            skills_str = doc.metadata.get('skills', '')
            if skills_str and skills_str.strip():
                freelancer_skills = [s.strip() for s in skills_str.split(',') if s.strip()]
            else:
                freelancer_skills = []

            similarity = max(0, 1 - distance)
            skill_match = self._calculate_skill_match(required_skills, freelancer_skills)
            combined_score = (similarity * 0.6) + (skill_match * 0.4)

            # Case-insensitive skill matching
            required_lower = set(s.lower().strip() for s in required_skills if s and s.strip())
            freelancer_lower = set(s.lower().strip() for s in freelancer_skills if s and s.strip())

            matched_skills = []
            missing_skills = []

            for req_skill in required_skills:
                if req_skill and req_skill.strip():
                    req_lower = req_skill.lower().strip()
                    if req_lower in freelancer_lower:
                        matched_skills.append(req_skill)
                    else:
                        missing_skills.append(req_skill)

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

        if not required:
            return 1.0

        # Normalize: lowercase, strip whitespace, remove empty strings
        required_set = set(s.lower().strip() for s in required if s and s.strip())
        has_set = set(s.lower().strip() for s in has if s and s.strip())

        if not required_set:
            return 1.0

        # Find matches (case-insensitive)
        matched = len(required_set & has_set)

        logger.debug(f"Required skills: {required_set}")
        logger.debug(f"Has skills: {has_set}")
        logger.debug(f"Matched: {matched}/{len(required_set)}")

        return matched / len(required_set)

    def bulk_index_freelancers(self, user_ids: List[int]) -> Dict:

        import json

        results = {'success': [], 'errors': []}

        documents = []
        ids = []

        for user_id in user_ids:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("""
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
                        WHERE u.id = %s
                    """, [user_id])

                    row = cursor.fetchone()
                    if not row:
                        results['errors'].append({'user_id': user_id, 'error': 'User not found'})
                        continue

                    username, bio, skills_raw, exp_level, years_exp, title = row

                # Parse skills - handle both JSON string and Python list
                if isinstance(skills_raw, str):
                    try:
                        skills = json.loads(skills_raw)
                    except (json.JSONDecodeError, TypeError):
                        skills = [s.strip() for s in skills_raw.split(',') if s.strip()]
                elif isinstance(skills_raw, list):
                    skills = skills_raw
                else:
                    skills = []

                profile_text = f"""
Professional: {title or 'Freelancer'}
Skills: {', '.join(skills) if skills else 'General'}
Experience: {exp_level or 'intermediate'} level with {years_exp or 0} years
Bio: {bio or ''}
                """.strip()

                # Create Document
                document = Document(
                    page_content=profile_text,
                    metadata={
                        'user_id': str(user_id),
                        'username': username,
                        'skills': ','.join(skills) if skills else '',  # Store as comma-separated
                        'experience_level': exp_level or 'intermediate',
                        'years_experience': years_exp or 0,
                        'title': title or 'Freelancer'
                    }
                )

                documents.append(document)
                ids.append(str(user_id))
                results['success'].append(user_id)

            except Exception as e:
                logger.error(f"Error preparing user {user_id}: {e}")
                results['errors'].append({'user_id': user_id, 'error': str(e)})

        # Batch add documents (LangChain optimization)
        if documents:
            try:
                self.vectorstore.add_documents(documents=documents, ids=ids)
                logger.info(f"Bulk indexed {len(documents)} freelancers")
            except Exception as e:
                logger.error(f"Batch indexing error: {e}")
                # Mark all as errors
                for user_id in results['success']:
                    results['errors'].append({'user_id': user_id, 'error': str(e)})
                results['success'] = []

        return results

    def delete_freelancer(self, user_id: int):

        try:
            self.vectorstore.delete(ids=[str(user_id)])
            logger.info(f"Deleted freelancer {user_id} from vector store")
        except Exception as e:
            logger.error(f"Error deleting freelancer {user_id}: {e}")
            raise

    def get_retriever(self, search_type: str = "similarity", k: int = 10):

        return self.vectorstore.as_retriever(
            search_type=search_type,
            search_kwargs={"k": k}
        )