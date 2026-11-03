import time
from datetime import timedelta
from decimal import Decimal
from django.utils import timezone
from django.contrib.auth import get_user_model
from selenium.webdriver.common.by import By
from apps.projects.models import Project, Review
from apps.profiles.models import FreelancerProfile, ClientProfile
from Sprint_5_Test.selenium.base import BaseSprint5SeleniumTestCase

User = get_user_model()

class US25SeleniumReviewTest(BaseSprint5SeleniumTestCase):
    def setUp(self):
        self.password = 'Pass123456!'
        self.client_user = User.objects.create_user(
            username='sel_client_rev',
            email='sel_client_rev@test.com',
            password=self.password,
            role='CLIENT',
            is_email_verified=True
        )
        self.freelancer = User.objects.create_user(
            username='sel_free_rev',
            email='sel_free_rev@test.com',
            password=self.password,
            role='FREELANCER',
            is_email_verified=True
        )
        FreelancerProfile.objects.get_or_create(user=self.freelancer)
        ClientProfile.objects.get_or_create(user=self.client_user)

        self.project = Project.objects.create(
            client=self.client_user,
            freelancer=self.freelancer,
            title='Selenium Review Completed Project',
            final_price=Decimal('4500.00'),
            deadline=timezone.now() + timedelta(days=5),
            status=Project.Status.COMPLETED,
            completed_at=timezone.now()
        )

    def test_submit_review_in_browser(self):
        """US-25: Client submits review and rating on completed project page."""
        self.login_user('sel_client_rev@test.com', self.password)
        project_url = f'{self.live_server_url}/projects/{self.project.public_id}/'
        self.driver.get(project_url)
        time.sleep(1)

        # Locate review section
        self.assertIn('Ratings & Reviews', self.driver.page_source)
        rating_select = self.driver.find_element(By.NAME, 'rating')
        rating_select.send_keys('5')

        feedback_textarea = self.driver.find_element(By.NAME, 'feedback')
        feedback_textarea.send_keys('Superb performance, delivered cleanly ahead of schedule!')

        submit_btn = self.driver.find_element(By.XPATH, "//button[contains(text(), 'Submit Review')]")
        submit_btn.click()
        time.sleep(1.5)

        # Verify review exists in DB
        self.assertTrue(Review.objects.filter(project=self.project, reviewer=self.client_user).exists())

    def test_review_appears_on_freelancer_public_profile(self):
        """US-25: Review and 5-star rating are displayed on freelancer public profile."""
        Review.objects.create(
            project=self.project,
            reviewer=self.client_user,
            reviewee=self.freelancer,
            rating=5,
            feedback='Outstanding engineering excellence!'
        )
        profile_url = f'{self.live_server_url}/freelancers/{self.freelancer.username}/'
        self.driver.get(profile_url)
        time.sleep(1)
        self.assertIn(self.freelancer.username, self.driver.page_source)
        self.assertIn('5', self.driver.page_source)
