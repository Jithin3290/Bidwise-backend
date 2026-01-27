# jobs/tests/test.py
from django.urls import reverse
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework import status
from unittest.mock import patch
from ..models import Job

# Mock user class
class MockUser:
    id = 1
    pk = 1  # Required by DRF throttling
    is_client = True
    is_authenticated = True

class JobViewsTestCase(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = MockUser()
        self.client.force_authenticate(user=self.user)

        # Create a sample job
        self.job = Job.objects.create(
            title="Test Job",
            description="Test Description",
            client_id=self.user.id,
            status="published"
        )

    @patch("jobs.views.get_client_info")
    def test_job_list(self, mock_client_info):
        """Test GET /api/jobs/ returns list of jobs"""
        mock_client_info.return_value = {
            "id": self.user.id,
            "username": "testuser"
        }

        url = reverse("jobs:job-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data["results"]), 1)
        self.assertEqual(response.data["results"][0]["title"], "Test Job")
        self.assertEqual(response.data["results"][0]["client_info"]["username"], "testuser")

    @patch("jobs.views.get_client_info")
    def test_job_detail(self, mock_client_info):
        """Test GET /api/jobs/<id>/"""
        mock_client_info.return_value = {
            "id": self.user.id,
            "username": "testuser"
        }

        url = reverse("jobs:job-detail", kwargs={"id": self.job.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["title"], "Test Job")
        self.assertEqual(response.data["client_info"]["username"], "testuser")

    @patch("jobs.views.get_client_info")
    def test_client_create_job(self, mock_client_info):
        """Test POST /api/client/jobs/"""
        mock_client_info.return_value = {
            "id": self.user.id,
            "username": "testuser"
        }

        url = reverse("jobs:client-job-create")
        data = {
            "title": "New Job",
            "description": "New Description",
            "status": "draft"
        }
        response = self.client.post(url, data, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Job.objects.filter(client_id=self.user.id).count(), 2)
