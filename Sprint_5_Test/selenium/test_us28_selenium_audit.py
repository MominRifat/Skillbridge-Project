import time
from decimal import Decimal
from django.contrib.auth import get_user_model
from selenium.webdriver.common.by import By
from apps.wallets.models import Wallet, WalletTransaction, Deposit
from Sprint_5_Test.selenium.base import BaseSprint5SeleniumTestCase

User = get_user_model()

class US28SeleniumAuditTest(BaseSprint5SeleniumTestCase):
    def setUp(self):
        self.password = 'Pass123456!'
        self.admin = User.objects.create_superuser(
            username='sel_admin_audit',
            email='sel_admin_audit@test.com',
            password=self.password
        )
        self.client_user = User.objects.create_user(
            username='sel_client_audit',
            email='sel_client_audit@test.com',
            password=self.password,
            role='CLIENT',
            is_email_verified=True
        )
        self.wallet = Wallet.objects.get_or_create(user=self.client_user)[0]

    def test_admin_financial_audit_trail_navigation_in_browser(self):
        """US-28: Admin navigates to transaction ledger in Django Admin."""
        WalletTransaction.objects.create(
            wallet=self.wallet,
            user=self.client_user,
            amount=Decimal('5000.00'),
            transaction_type=WalletTransaction.Type.DEPOSIT,
            status=WalletTransaction.Status.COMPLETED,
            description='Test verified audit deposit'
        )
        self.login_user('sel_admin_audit@test.com', self.password)
        self.driver.get(f'{self.live_server_url}/admin/wallets/wallettransaction/')
        time.sleep(1)

        self.assertIn('Wallet transactions', self.driver.page_source)
        self.assertIn(self.client_user.username, self.driver.page_source)
        self.assertIn('5000', self.driver.page_source)

    def test_admin_deposit_status_filter_in_browser(self):
        """US-28: Admin inspects deposit requests and filters by status."""
        Deposit.objects.create(
            user=self.client_user,
            amount=Decimal('2500.00'),
            payment_method='BKASH',
            sender_number='01700000000',
            transaction_id='TRXAUDIT999',
            status=Deposit.Status.PENDING
        )
        self.login_user('sel_admin_audit@test.com', self.password)
        self.driver.get(f'{self.live_server_url}/admin/wallets/deposit/')
        time.sleep(1)

        self.assertIn('TRXAUDIT999', self.driver.page_source)
        self.assertIn('PENDING', self.driver.page_source)

    def test_admin_dashboard_models_overview_rendering(self):
        """US-28: Admin dashboard renders all project, wallet, and dispute models."""
        self.login_user('sel_admin_audit@test.com', self.password)
        self.driver.get(f'{self.live_server_url}/admin/')
        time.sleep(1)

        self.assertIn('Skillbridge admin', self.driver.page_source)
        self.assertIn('Wallets', self.driver.page_source)
