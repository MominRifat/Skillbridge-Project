from __future__ import annotations
from django.db import transaction
from django.utils import timezone
from apps.agreements.models import Agreement
from apps.core.exceptions import InvalidState, PermissionDenied, ValidationFailed
from apps.core.models import ActivityVerb
from apps.core.money import ZERO
from apps.core.services import record_activity
from apps.marketplace.models import Job
from apps.negotiations.models import Offer
from apps.notifications.models import NotificationType
from apps.notifications.services import notify
from apps.proposals.models import Proposal
from apps.wallets import ledger
from apps.wallets.models import WalletTransaction

@transaction.atomic()
def create_agreement_from_offer(*, offer: Offer, actor) -> Agreement:
    negotiation = offer.negotiation
    job = negotiation.job
    agreement = Agreement.objects.create(job=job, client=negotiation.client, freelancer=negotiation.freelancer, offer=offer, amount=offer.amount, deadline=offer.deadline, deliverables=offer.deliverables, revision_limit=offer.revision_limit, status=Agreement.Status.ACTIVE)
    job.hired_freelancer = negotiation.freelancer
    job.hired_at = timezone.now()
    job.status = Job.Status.HIRED
    job.save(update_fields=['hired_freelancer', 'hired_at', 'status', 'updated_at'])
    Proposal.objects.filter(pk=negotiation.proposal_id).update(status=Proposal.Status.ACCEPTED, responded_at=timezone.now())
    Proposal.objects.filter(job=job, status__in=Proposal.OPEN_STATUSES).exclude(pk=negotiation.proposal_id).update(status=Proposal.Status.REJECTED, rejection_reason='The client hired another freelancer for this position.', responded_at=timezone.now())
    return agreement

@transaction.atomic()
def submit_work(*, agreement: Agreement, freelancer, submission_text: str='', submission_link: str='', files=None) -> Agreement:
    from apps.agreements.models import AgreementAttachment
    agreement = Agreement.objects.select_for_update().get(pk=agreement.pk)
    if agreement.freelancer_id != freelancer.pk:
        raise PermissionDenied('Only the hired freelancer can submit work.')
    if agreement.status == Agreement.Status.COMPLETED:
        raise InvalidState('This contract has already been completed and approved.')
    if agreement.status == Agreement.Status.CANCELLED:
        raise InvalidState('This contract is cancelled.')
    submission_text = submission_text.strip()
    submission_link = submission_link.strip()
    if not submission_text and (not submission_link) and (not files):
        raise ValidationFailed('Please provide notes, a project link (Google Drive / GitHub / Demo), or upload deliverables files.')
    agreement.work_submission = submission_text
    agreement.submission_link = submission_link
    agreement.submitted_at = timezone.now()
    agreement.status = Agreement.Status.IN_PROGRESS
    file_list = files or []
    if file_list:
        agreement.submission_file = file_list[0]
    agreement.save(update_fields=['work_submission', 'submission_link', 'submission_file', 'submitted_at', 'status', 'updated_at'])
    for upload in file_list:
        AgreementAttachment.objects.create(agreement=agreement, file=upload, original_name=getattr(upload, 'name', 'file')[:255], size_bytes=getattr(upload, 'size', 0) or 0)
    job = Job.objects.select_for_update().get(pk=agreement.job_id)
    if job.status == Job.Status.HIRED:
        job.status = Job.Status.IN_PROGRESS
        job.save(update_fields=['status', 'updated_at'])
    record_activity(ActivityVerb.WORK_SUBMITTED, f'Submitted work for “{job.title}”', actor=freelancer, job=job, target=agreement)
    notify(agreement.client, NotificationType.WORK_SUBMITTED, f'Work submitted for “{job.title}”', message=f'{freelancer.full_name} has submitted deliverables for your review.', actor=freelancer, target_url=agreement.get_absolute_url(), level='INFO')
    return agreement

@transaction.atomic()
def complete_agreement_and_release_payment(*, agreement: Agreement, client, feedback: str='') -> Agreement:
    agreement = Agreement.objects.select_for_update().get(pk=agreement.pk)
    if agreement.client_id != client.pk:
        raise PermissionDenied('Only the client can approve deliverables and release payment.')
    if agreement.status == Agreement.Status.COMPLETED:
        raise InvalidState('This agreement has already been completed and paid.')
    if agreement.status == Agreement.Status.CANCELLED:
        raise InvalidState('Cannot release payment for a cancelled agreement.')
    job = Job.objects.select_for_update().get(pk=agreement.job_id)
    freelancer = agreement.freelancer
    amount = agreement.amount

    from apps.projects.models import Project
    from apps.tasks.models import Task
    from django.db.models import Sum, Q

    project = Project.objects.filter(Q(agreement=agreement) | Q(job=job)).first()

    already_paid_to_members = ZERO
    if project:
        # Sum of subtask payouts already received by team members on this project
        already_paid_to_members = WalletTransaction.objects.filter(
            project_id=project.id,
            task_id__isnull=False,
            transaction_type=WalletTransaction.Type.PROJECT_PAYMENT
        ).exclude(user=freelancer).aggregate(total=Sum('amount'))['total'] or ZERO

        # Automatically disburse funds to any completed tasks assigned to team members that haven't been paid yet
        pending_member_tasks = project.tasks.filter(
            status=Task.Status.COMPLETED,
            assigned_to__isnull=False,
            skillcoin_allocation__gt=ZERO
        ).exclude(assigned_to=freelancer)

        for t in pending_member_tasks:
            if not WalletTransaction.objects.filter(task_id=t.id, transaction_type=WalletTransaction.Type.PROJECT_PAYMENT, user=t.assigned_to).exists():
                t_amt = min(t.skillcoin_allocation, max(ZERO, amount - already_paid_to_members))
                if t_amt > ZERO:
                    ledger.release_payment(client=client, freelancer=t.assigned_to, amount=t_amt, project=project, task=t, actor=client)
                    already_paid_to_members += t_amt

    # The remaining amount from the project budget goes to the team leader
    leader_share = max(ZERO, amount - already_paid_to_members)
    client_debit_remaining = leader_share
    credit_freelancer = None

    client.wallet.refresh_from_db()
    if client_debit_remaining > ZERO:
        c_src = WalletTransaction.Bucket.RESERVED if client.wallet.reserved_balance >= client_debit_remaining else (WalletTransaction.Bucket.ESCROW if client.wallet.escrow_balance >= client_debit_remaining else WalletTransaction.Bucket.AVAILABLE)
        debit_client = ledger.move(user=client, amount=client_debit_remaining, transaction_type=WalletTransaction.Type.PROJECT_PAYMENT, from_bucket=c_src, to_bucket=WalletTransaction.Bucket.EXTERNAL, job=job, project=project, counterparty=freelancer, actor=client, description=f'Payment for completed job “{job.title[:60]}”')
        credit_freelancer = ledger.move(user=freelancer, amount=leader_share, transaction_type=WalletTransaction.Type.PROJECT_PAYMENT, from_bucket=WalletTransaction.Bucket.EXTERNAL, to_bucket=WalletTransaction.Bucket.AVAILABLE, job=job, project=project, counterparty=client, actor=client, related=debit_client, description=f'Payment received for completed job “{job.title[:60]}”')
        WalletTransaction.objects.filter(pk=debit_client.pk).update(related_transaction=credit_freelancer)

    client.wallet.refresh_from_db()
    remainder = max(ZERO, job.reserved_amount - amount)
    remainder = min(remainder, client.wallet.reserved_balance)
    if remainder > ZERO:
        ledger.release_job_budget(user=client, amount=remainder, job=job, actor=client, reason='Unused budget returned after agreement completion')

    job.reserved_amount = ZERO
    job.status = Job.Status.COMPLETED
    job.completed_at = timezone.now()
    job.save(update_fields=['reserved_amount', 'status', 'completed_at', 'updated_at'])

    agreement.status = Agreement.Status.COMPLETED
    agreement.completed_at = timezone.now()
    agreement.client_feedback = feedback.strip()
    agreement.payment_transaction = credit_freelancer
    agreement.save(update_fields=['status', 'completed_at', 'client_feedback', 'payment_transaction', 'updated_at'])

    if project:
        project.status = Project.Status.COMPLETED
        project.completed_at = timezone.now()
        project.save(update_fields=['status', 'completed_at', 'updated_at'])

    record_activity(ActivityVerb.PAYMENT_RELEASED, f'Approved work and released {amount:,.2f} SKC for “{job.title}”', actor=client, job=job, project=project, target=agreement, amount=amount)
    notify(freelancer, NotificationType.PAYMENT_RELEASED, f'Payment of {leader_share:,.2f} SKC released!', message=f'{client.full_name} approved your work for “{job.title}”. {leader_share:,.2f} SKC has been credited to your wallet available balance!', actor=client, target_url=agreement.get_absolute_url(), level='SUCCESS', email=True)
    return agreement
