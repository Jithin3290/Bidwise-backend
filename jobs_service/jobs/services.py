
import logging
import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)


class UserService:
    """Client for communicating with Users Service"""

    def __init__(self):
        self.base_url = getattr(settings, 'USERS_SERVICE_URL', 'http://users-service:8000')
        self.service_token = getattr(settings, 'SERVICE_TOKEN', 'secure-service-token-123')
        self.timeout = 10
        self.cache_timeout = 300  # 5 minutes

    def _get_headers(self):
        return {
            'Authorization': f'Bearer {self.service_token}',
            'Content-Type': 'application/json'
        }

    def get_user_profile(self, user_id, use_cache=True):
        """Get single user profile with optional caching"""
        if not user_id:
            return None

        cache_key = f'user_profile_{user_id}'

        if use_cache:
            cached_data = cache.get(cache_key)
            if cached_data:
                logger.debug(f"Cache hit for user {user_id}")
                return cached_data

        try:
            url = f"{self.base_url}/api/auth/users/{user_id}/profile/"
            response = requests.get(
                url,
                headers=self._get_headers(),
                timeout=self.timeout
            )

            if response.status_code == 200:
                data = response.json()
                transformed_data = self._transform_user_data(data)

                if use_cache:
                    cache.set(cache_key, transformed_data, self.cache_timeout)

                return transformed_data

            elif response.status_code == 404:
                logger.warning(f"User {user_id} not found")
                return self._get_fallback_user(user_id)
            else:
                logger.error(f"Failed to fetch user {user_id}: {response.status_code}")
                return self._get_fallback_user(user_id)

        except requests.RequestException as e:
            logger.error(f"Request failed for user {user_id}: {e}")
            return self._get_fallback_user(user_id)

    def get_users_batch(self, user_ids, use_cache=True):
        """Get multiple user profiles with optional caching"""
        if not user_ids:
            return {}

        users_data = {}
        uncached_ids = []

        if use_cache:
            for user_id in user_ids:
                cache_key = f'user_profile_{user_id}'
                cached_data = cache.get(cache_key)
                if cached_data:
                    users_data[str(user_id)] = cached_data
                else:
                    uncached_ids.append(user_id)
        else:
            uncached_ids = user_ids

        if uncached_ids:
            try:
                url = f"{self.base_url}/api/auth/users/batch/"
                payload = {'user_ids': uncached_ids}

                response = requests.post(
                    url,
                    json=payload,
                    headers=self._get_headers(),
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    fetched_users = response.json().get('users', [])
                    for user in fetched_users:
                        user_id = user['id']
                        transformed_data = self._transform_user_data(user)
                        users_data[str(user_id)] = transformed_data

                        if use_cache:
                            cache_key = f'user_profile_{user_id}'
                            cache.set(cache_key, transformed_data, self.cache_timeout)

                    # Add fallback for missing users
                    for user_id in uncached_ids:
                        if str(user_id) not in users_data:
                            users_data[str(user_id)] = self._get_fallback_user(user_id)
                else:
                    logger.error(f"Batch fetch failed: {response.status_code}")
                    for user_id in uncached_ids:
                        users_data[str(user_id)] = self._get_fallback_user(user_id)

            except requests.RequestException as e:
                logger.error(f"Batch request failed: {e}")
                for user_id in uncached_ids:
                    users_data[str(user_id)] = self._get_fallback_user(user_id)

        return users_data

    def _transform_user_data(self, user_data):
        """Transform user data to expected format"""
        return {
            'id': user_data.get('id'),
            'username': user_data.get('username'),
            'first_name': user_data.get('first_name'),
            'last_name': user_data.get('last_name'),
            'profile_picture': user_data.get('profile_picture'),
            'rating': user_data.get('rating', 0.0),
            'total_spent': user_data.get('total_spent', 0.0),
            'jobs_posted': user_data.get('jobs_posted', 0),
            'member_since': user_data.get('date_joined'),
            'location': user_data.get('location', ''),
            'is_verified': user_data.get('is_verified', False),
        }

    def _get_fallback_user(self, user_id):
        """Return fallback user data"""
        return {
            'id': user_id,
            'username': f'user_{user_id}',
            'first_name': 'Unknown',
            'last_name': 'User',
            'profile_picture': None,
            'rating': 0.0,
            'total_spent': 0.0,
            'jobs_posted': 0,
            'member_since': None,
            'location': '',
            'is_verified': False,
        }

    def invalidate_cache(self, user_id):
        """Invalidate cached user data"""
        cache_key = f'user_profile_{user_id}'
        cache.delete(cache_key)
        logger.debug(f"Invalidated cache for user {user_id}")


# Singleton instance
user_service = UserService()