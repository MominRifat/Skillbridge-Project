from __future__ import annotations
import os
from decimal import Decimal
from django.db.models.signals import post_save
from django.dispatch import receiver
from apps.accounts.models import Role, User

@receiver(post_save, sender=User, dispatch_uid='accounts.bootstrap_user')
def bootstrap_user(sender, instance: User, created: bool, raw: bool=False, **kwargs):
    if not created or raw:
        return
    from apps.profiles.models import ClientProfile, FreelancerProfile
    from apps.wallets.models import Wallet

    init_bal = Decimal(os.getenv('INITIAL_WALLET_BALANCE', '0.00'))
    Wallet.objects.get_or_create(user=instance, defaults={'available_balance': init_bal})
    if instance.role == Role.CLIENT:
        ClientProfile.objects.get_or_create(user=instance)
    elif instance.role == Role.FREELANCER:
        FreelancerProfile.objects.get_or_create(user=instance)
