# tests/test.py
from unittest.mock import patch

from django.conf import settings
from rest_framework.test import APITestCase, APIClient
from rest_framework import status
from django.urls import reverse
from django.contrib.auth import get_user_model
from ..models import UserAccountType
User = get_user_model()


class RegisterViewTest(APITestCase):
    def setUp(self):
        self.url = reverse('register')  # make sure the URL name is 'register'
        self.user_data = {
            "email": "testuser@example.com",
            "username": "testuser",
            "password": "StrongP@ssw0rd",
            "account_types": ["freelancer"],
            "recaptcha": "dummy-token"  # Assuming your view checks recaptcha
        }

    @patch('users.views.send_welcome_email_task.delay')
    @patch('users.views.update_profile_completion_task.delay')
    def test_register_success(self, mock_update_task, mock_welcome_task):
        response = self.client.post(self.url, self.user_data, format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertIn('user', response.data)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

        # Check user created in DB
        user = User.objects.get(email=self.user_data['email'])
        self.assertEqual(user.username, self.user_data['email'])

        # Check Celery tasks were called
        mock_welcome_task.assert_called_once_with(user.id)
        mock_update_task.assert_called_once_with(user.id)

    def test_register_invalid_password(self):
        invalid_data = self.user_data.copy()
        invalid_data['password'] = 'short'

        response = self.client.post(self.url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)

    def test_register_missing_role(self):
        invalid_data = self.user_data.copy()
        invalid_data['account_types'] = []

        response = self.client.post(self.url, invalid_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('account_types', response.data)

class GoogleLoginViewTest(APITestCase):
    @patch('users.views.id_token.verify_oauth2_token')  # Mock Google verification
    @patch('users.views.send_welcome_email_task.delay')
    @patch('users.views.update_profile_completion_task.delay')
    def test_google_login_success(self, mock_update_task, mock_welcome_task, mock_verify):
        """
        Test Google login view returns JWT and creates/gets user.
        """
        # Fake Google payload
        mock_verify.return_value = {
            "email": "googleuser@example.com",
            "email_verified": True,
            "name": "Google User",
        }

        url = reverse('google_login')  # make sure your urls.py name matches
        data = {"token": "fake-google-token", "account_type": "freelancer"}

        response = self.client.post(url, data, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('access', response.data)
        self.assertIn('refresh', response.data)

        user = User.objects.get(email='googleuser@example.com')
        self.assertEqual(user.email, 'googleuser@example.com')
        self.assertTrue(UserAccountType.objects.filter(user=user, account_type='freelancer').exists())

        mock_welcome_task.assert_called_once_with(user.id)
        mock_update_task.assert_called_once_with(user.id)


class GetUserProfileForServiceTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="serviceuser@example.com",
            username="serviceuser",
            password="StrongP@ssw0rd"
        )
        UserAccountType.objects.create(user=self.user, account_type='freelancer')

        self.client = APIClient()
        self.url = reverse('user-profile-service', kwargs={'user_id': self.user.id})
        self.valid_token = getattr(settings, 'SERVICE_TOKEN', 'secure-service-token-123')

    def test_valid_service_token_returns_user_profile(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION=f'Bearer {self.valid_token}')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['email'], self.user.email)
        self.assertIn('account_types', response.data)

    def test_invalid_service_token_returns_403(self):
        response = self.client.get(self.url, HTTP_AUTHORIZATION='Bearer invalid')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class BatchGetUserProfilesTest(APITestCase):
    def setUp(self):
        self.user1 = User.objects.create_user(
            email="user1@example.com",
            username="user1",
            password="StrongP@ssw0rd"
        )
        self.user2 = User.objects.create_user(
            email="user2@example.com",
            username="user2",
            password="StrongP@ssw0rd"
        )
        UserAccountType.objects.create(user=self.user1, account_type='freelancer')
        UserAccountType.objects.create(user=self.user2, account_type='client')

        self.client = APIClient()
        self.url = reverse('users-batch-service')
        self.valid_token = 'secure-service-token-123'

    def test_batch_user_profiles_with_valid_token(self):
        data = {"user_ids": [self.user1.id, self.user2.id]}
        response = self.client.post(
            self.url, data, format='json',
            HTTP_AUTHORIZATION=f'Bearer {self.valid_token}'
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 2)
        emails = [u['email'] for u in response.data]
        self.assertIn(self.user1.email, emails)
        self.assertIn(self.user2.email, emails)

    def test_batch_user_profiles_invalid_token(self):
        data = {"user_ids": [self.user1.id]}
        response = self.client.post(
            self.url, data, format='json',
            HTTP_AUTHORIZATION='Bearer invalid'
        )
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)