# users/management/commands/setup_groups.py
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand
from users.models import (UserCertification, UserEducation, UserExperience,
                          UserPortfolio, UserSocialLink)

User = get_user_model()


class Command(BaseCommand):
    help = "Setup initial groups, permissions, and sample data"

    def handle(self, *args, **options):
        # Create groups
        groups_data = [
            {
                "name": "Admin",
                "permissions": ["add_user", "change_user", "delete_user", "view_user"],
            },
            {"name": "Freelancer", "permissions": ["change_user", "view_user"]},
            {"name": "Client", "permissions": ["change_user", "view_user"]},
            {"name": "Moderator", "permissions": ["change_user", "view_user"]},
        ]

        for group_data in groups_data:
            group, created = Group.objects.get_or_create(name=group_data["name"])
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created group: {group.name}"))

            # Add permissions to group
            for perm_codename in group_data["permissions"]:
                try:
                    permission = Permission.objects.get(codename=perm_codename)
                    group.permissions.add(permission)
                except Permission.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(f"Permission {perm_codename} not found")
                    )

        # Create admin user if it doesn't exist
        admin_email = "admin@example.com"
        if not User.objects.filter(email=admin_email).exists():
            admin_user = User.objects.create_superuser(
                email=admin_email,
                username="admin",
                password="admin123",
                first_name="Admin",
                last_name="User",
                user_type="admin",
            )
            admin_group = Group.objects.get(name="Admin")
            admin_user.groups.add(admin_group)
            admin_user.calculate_profile_completion()
            admin_user.save()

            self.stdout.write(self.style.SUCCESS(f"Created admin user: {admin_email}"))

        # Create sample freelancer
        freelancer_email = "freelancer@example.com"
        if not User.objects.filter(email=freelancer_email).exists():
            freelancer = User.objects.create_user(
                email=freelancer_email,
                username="freelancer1",
                password="freelancer123",
                first_name="John",
                last_name="Developer",
                user_type="freelancer",
                phone_number="+1234567890",
                bio="Full-stack developer with 5 years of experience",
                country="United States",
                city="New York",
                title="Senior Full Stack Developer",
                website="https://johndeveloper.com",
                linkedin_url="https://linkedin.com/in/johndeveloper",
                github_url="https://github.com/johndeveloper",
                skills=["Python", "JavaScript", "React", "Django", "PostgreSQL"],
                experience_level="senior",
                years_of_experience=5,
                languages_spoken=["English", "Spanish"],
                hourly_rate=75.00,
                availability_status="available",
                availability_hours_per_week=40,
                average_rating=4.8,
                total_reviews=25,
                total_projects_completed=50,
            )

            freelancer_group = Group.objects.get(name="Freelancer")
            freelancer.groups.add(freelancer_group)
            freelancer.calculate_profile_completion()
            freelancer.save()

            # Add education
            UserEducation.objects.create(
                user=freelancer,
                degree="Bachelor of Science",
                field_of_study="Computer Science",
                institution="MIT",
                start_date="2015-09-01",
                end_date="2019-05-30",
                description="Focused on software engineering and algorithms",
            )

            # Add experience
            UserExperience.objects.create(
                user=freelancer,
                title="Senior Full Stack Developer",
                company="Tech Solutions Inc",
                location="New York, NY",
                start_date="2021-03-01",
                description="Lead development of web applications using React and Django",
                is_current=True,
            )

            UserExperience.objects.create(
                user=freelancer,
                title="Full Stack Developer",
                company="StartupXYZ",
                location="San Francisco, CA",
                start_date="2019-06-01",
                end_date="2021-02-28",
                description="Developed and maintained multiple web applications",
            )

            # Add certification
            UserCertification.objects.create(
                user=freelancer,
                name="AWS Certified Solutions Architect",
                issuing_organization="Amazon Web Services",
                issue_date="2022-01-15",
                expiry_date="2025-01-15",
                credential_id="AWS-CSA-2022-001",
            )

            # Add portfolio items
            UserPortfolio.objects.create(
                user=freelancer,
                title="E-commerce Platform",
                description="Full-featured e-commerce platform built with Django and React",
                url="https://demo-ecommerce.com",
                technologies_used=["Django", "React", "PostgreSQL", "Redis"],
                is_featured=True,
            )

            UserPortfolio.objects.create(
                user=freelancer,
                title="Task Management App",
                description="Real-time collaborative task management application",
                url="https://taskmanager-demo.com",
                technologies_used=["React", "Node.js", "MongoDB", "Socket.io"],
            )

            # Add social links
            UserSocialLink.objects.create(
                user=freelancer,
                platform="linkedin",
                url="https://linkedin.com/in/johndeveloper",
            )

            UserSocialLink.objects.create(
                user=freelancer,
                platform="github",
                url="https://github.com/johndeveloper",
            )

            self.stdout.write(
                self.style.SUCCESS(f"Created sample freelancer: {freelancer_email}")
            )

        # Create sample client
        client_email = "client@example.com"
        if not User.objects.filter(email=client_email).exists():
            client = User.objects.create_user(
                email=client_email,
                username="client1",
                password="client123",
                first_name="Sarah",
                last_name="Johnson",
                user_type="client",
                phone_number="+1987654321",
                bio="CEO of a growing tech startup looking for talented freelancers",
                country="United States",
                city="San Francisco",
                company_name="InnovateTech Solutions",
                company_size="small",
                industry="Technology",
                website="https://innovatetech.com",
                total_projects_posted=12,
                total_spent=15000.00,
            )

            client_group = Group.objects.get(name="Client")
            client.groups.add(client_group)
            client.calculate_profile_completion()
            client.save()

            self.stdout.write(
                self.style.SUCCESS(f"Created sample client: {client_email}")
            )

        self.stdout.write(
            self.style.SUCCESS("Successfully setup groups and sample data!")
        )

        self.stdout.write(self.style.SUCCESS("Login credentials:"))
        self.stdout.write(f"Admin: {admin_email} / admin123")
        self.stdout.write(f"Freelancer: {freelancer_email} / freelancer123")
        self.stdout.write(f"Client: {client_email} / client123")
