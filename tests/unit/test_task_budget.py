from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from apps.accounts.models import User, Role
from apps.projects.models import Project
from apps.tasks import services
from apps.tasks.models import Task
from apps.core.exceptions import ValidationFailed

class TaskBudgetEnforcementTest(TestCase):
    def setUp(self):
        self.client_user = User.objects.create_user(username='client1', email='c1@test.com', password='pw', role=Role.CLIENT)
        self.freelancer = User.objects.create_user(username='freelancer1', email='f1@test.com', password='pw', role=Role.FREELANCER)
        self.member = User.objects.create_user(username='member1', email='m1@test.com', password='pw', role=Role.FREELANCER)
        self.project = Project.objects.create(
            client=self.client_user,
            freelancer=self.freelancer,
            title='Test 1000 SKC Project',
            final_price=Decimal('1000.00'),
            deadline=timezone.now() + timezone.timedelta(days=7)
        )

    def test_cannot_exceed_project_escrow_budget(self):
        # 1. Allocate 600 SKC - should succeed
        t1 = services.create_task(
            project=self.project,
            title='Task 1',
            created_by=self.freelancer,
            assigned_to=self.member,
            skillcoin_allocation=Decimal('600.00')
        )
        self.assertEqual(t1.skillcoin_allocation, Decimal('600.00'))

        # 2. Try to allocate 500 SKC (total 1100 > 1000) - should fail with ValidationFailed
        with self.assertRaises(ValidationFailed) as ctx:
            services.create_task(
                project=self.project,
                title='Task 2',
                created_by=self.freelancer,
                assigned_to=self.member,
                skillcoin_allocation=Decimal('500.00')
            )
        self.assertIn('remains unallocated from the funded project budget', str(ctx.exception))

        # 3. Allocate 400 SKC (total 1000 == 1000) - should succeed
        t2 = services.create_task(
            project=self.project,
            title='Task 2',
            created_by=self.freelancer,
            assigned_to=self.member,
            skillcoin_allocation=Decimal('400.00')
        )
        self.assertEqual(t2.skillcoin_allocation, Decimal('400.00'))

        # 4. Try to allocate even 1 SKC more - should fail
        with self.assertRaises(ValidationFailed):
            services.create_task(
                project=self.project,
                title='Task 3',
                created_by=self.freelancer,
                assigned_to=self.member,
                skillcoin_allocation=Decimal('1.00')
            )
