# # jobs/tests/test.py
# from django.urls import reverse
# from rest_framework.test import APITestCase
# from rest_framework import status
# from ..models import Job, JobCategory, Skill
# from decimal import Decimal
# import uuid
#
#
# class JobViewsTestCase(APITestCase):
#
#     def setUp(self):
#         self.category = JobCategory.objects.create(name="Web Development")
#         self.skill = Skill.objects.create(name="Python")
#
#         self.job = Job.objects.create(
#             client_id="123",
#             title="Test Job",
#             description="Job description",
#             category=self.category,
#             job_type="fixed",
#             budget_min=Decimal("100"),
#             budget_max=Decimal("200"),
#             status="published"
#         )
#         self.job.skills.add(self.skill)
#
#     def test_job_list(self):
#         """Test GET /api/jobs/ returns published jobs list"""
#         url = reverse("jobs:job-list")  # include namespace
#         response = self.client.get(url)
#         self.assertEqual(response.status_code, status.HTTP_200_OK)
#         self.assertGreaterEqual(len(response.data), 1)
#
#     def test_job_detail(self):
#         """Test GET /api/jobs/<id>/"""
#         url = reverse("jobs:job-detail", kwargs={"id": self.job.id})
#         response = self.client.get(url)
#         self.assertEqual(response.status_code, status.HTTP_200_OK)
#         self.assertEqual(response.data["title"], self.job.title)
#
#     def test_client_job_list(self):
#         """Test GET /api/jobs/client/jobs/"""
#         url = reverse("jobs:client-job-list")
#         response = self.client.get(url)
#         # Unauthorized should return 401
#         self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
#
#     def test_client_create_job(self):
#         """Test POST /api/jobs/client/jobs/create/"""
#         url = reverse("jobs:client-job-create")
#         payload = {
#             "title": "New Client Job",
#             "description": "Client job description",
#             "category": self.category.id,
#             "skill_ids": [self.skill.id],
#             "job_type": "fixed",
#             "budget_min": "150",
#             "budget_max": "300"
#         }
#         response = self.client.post(url, payload, format="json")
#         # Without authentication, should return 401
#         self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
#
#     def test_client_job_detail(self):
#         """Test GET /api/jobs/client/jobs/<id>/"""
#         url = reverse("jobs:client-job-detail", kwargs={"id": self.job.id})
#         response = self.client.get(url)
#         self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
