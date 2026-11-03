import json
from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.projects.models import Project
from apps.tasks.models import Task
from apps.core.assistant import process_assistant_query, get_user_accessible_projects, get_user_accessible_tasks

User = get_user_model()

class US29AIAssistantTest(TestCase):
    def setUp(self):
        self.user_a = User.objects.create_user(
            username='user_a',
            email='user_a@ai.com',
            password='Password123!',
            role='FREELANCER',
            is_email_verified=True
        )
        self.user_b = User.objects.create_user(
            username='user_b',
            email='user_b@ai.com',
            password='Password123!',
            role='CLIENT',
            is_email_verified=True
        )
        self.outsider = User.objects.create_user(
            username='user_outsider',
            email='outsider@ai.com',
            password='Password123!',
            role='FREELANCER',
            is_email_verified=True
        )

        # Project between user_a and user_b
        self.project_a = Project.objects.create(
            client=self.user_b,
            freelancer=self.user_a,
            title='FinTech Mobile Wallet',
            final_price=Decimal('15000.00'),
            deadline=timezone.now() + timedelta(days=30),
            status=Project.Status.IN_PROGRESS
        )

        # Task assigned to user_a
        self.task_1 = Task.objects.create(
            project=self.project_a,
            title='Implement Biometric Login',
            created_by=self.user_b,
            assigned_to=self.user_a,
            skillcoin_allocation=Decimal('2500.00'),
            priority=Task.Priority.HIGH,
            status=Task.Status.IN_PROGRESS,
            deadline=timezone.now() + timedelta(days=5)
        )

        # Private project for outsider only
        self.secret_client = User.objects.create_user(
            username='secret_client',
            email='secret@ai.com',
            password='Password123!',
            role='CLIENT',
            is_email_verified=True
        )
        self.secret_project = Project.objects.create(
            client=self.secret_client,
            freelancer=self.outsider,
            title='Classified Government Project',
            final_price=Decimal('99999.00'),
            deadline=timezone.now() + timedelta(days=90),
            status=Project.Status.ACTIVE
        )

    def test_assistant_accessible_projects_and_tasks_scoping(self):
        """US-29: AI Assistant strictly scopes data to logged-in user."""
        projects_a = get_user_accessible_projects(self.user_a)
        self.assertIn(self.project_a, projects_a)
        self.assertNotIn(self.secret_project, projects_a)

        tasks_a = get_user_accessible_tasks(self.user_a)
        self.assertIn(self.task_1, tasks_a)

        # Outsider cannot see user_a's project
        projects_outsider = get_user_accessible_projects(self.outsider)
        self.assertNotIn(self.project_a, projects_outsider)

    def test_assistant_answers_projects_query_grounded(self):
        """US-29: AI assistant returns grounded project summary for user."""
        res = process_assistant_query(self.user_a, "What projects am I currently working on?")
        self.assertIn('FinTech Mobile Wallet', res['text'])
        self.assertNotIn('Classified Government Project', res['text'])
        self.assertEqual(len(res['grounded_items']), 1)
        self.assertEqual(res['grounded_items'][0]['title'], 'FinTech Mobile Wallet')

    def test_assistant_answers_task_query_grounded(self):
        """US-29: AI assistant returns grounded assigned task details and deadlines."""
        res = process_assistant_query(self.user_a, "What tasks are assigned to me?")
        self.assertIn('Implement Biometric Login', res['text'])
        self.assertIn('High', res['text'])
        self.assertEqual(res['scope'], 'tasks')

    def test_assistant_off_topic_query_triggers_strict_guardrail(self):
        """US-29: Off-topic or non-accessible queries return database-grounded guardrail."""
        res = process_assistant_query(self.user_a, "What is the capital of France?")
        self.assertEqual(res['scope'], 'guardrail')
        self.assertIn('strictly grounded to answer questions about projects', res['text'])

    def test_assistant_cannot_leak_secret_project_to_unauthorized_user(self):
        """US-29: Asking about another user's project yields no confidential data."""
        res = process_assistant_query(self.user_a, "Tell me about Classified Government Project")
        # Should not reveal secret details
        self.assertNotIn('99999', res['text'])
        self.assertNotIn('secret@ai.com', res['text'])

    def test_assistant_chat_view_and_ask_api_endpoints(self):
        """US-29: Interactive chat interface endpoint and async API."""
        self.client.login(email='user_a@ai.com', password='Password123!')
        
        # Test GET assistant UI
        page_res = self.client.get(reverse('core:assistant'))
        self.assertEqual(page_res.status_code, 200)
        self.assertContains(page_res, 'AI Assistant (Database Grounded)')

        # Test POST ask API
        api_res = self.client.post(
            reverse('core:assistant_ask'),
            data=json.dumps({'query': 'Show my high priority tasks'}),
            content_type='application/json'
        )
        self.assertEqual(api_res.status_code, 200)
        data = api_res.json()
        self.assertIn('Implement Biometric Login', data['text'])
        self.assertTrue(len(data['grounded_items']) > 0)
