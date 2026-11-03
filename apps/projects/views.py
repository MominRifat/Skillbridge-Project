from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import FileResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from apps.core.permissions import verified_required
from apps.core.exceptions import DomainError
from apps.accounts.models import User
from apps.projects.models import Project, TeamInvitation, ProjectFile, ProjectComment, Review, Dispute
from apps.projects import services
from apps.tasks.models import Task

@verified_required
def project_list(request):
    u = request.user
    from apps.agreements.models import Agreement
    from apps.projects.services import create_project_from_agreement
    for ag in Agreement.objects.filter(status=Agreement.Status.ACTIVE):
        create_project_from_agreement(ag)
    q = Project.objects.filter(client=u) if u.is_client else Project.objects.filter(models.Q(freelancer=u) | models.Q(team__members__user=u)).distinct()
    return render(request, 'projects/list.html', {'projects': q, 'page_title': 'Projects Workspace', 'nav': 'projects'})

@verified_required
def project_detail(request, public_id):
    p = get_object_or_404(Project.objects.select_related('client', 'freelancer', 'team'), public_id=public_id)
    if not p.has_access(request.user): raise PermissionDenied("Access denied.")
    t = getattr(p, 'team', None)
    from apps.tasks.services import check_and_auto_approve_task
    from apps.tasks.models import Task
    for rev_task in p.tasks.filter(status=Task.Status.IN_REVIEW):
        check_and_auto_approve_task(rev_task)
    reviews = p.reviews.select_related('reviewer', 'reviewee').all()
    my_review = p.reviews.filter(reviewer=request.user).first()
    disputes = p.disputes.select_related('raised_by', 'against').all()
    can_review = (p.status == Project.Status.COMPLETED) and (request.user.pk in (p.client_id, p.freelancer_id)) and not my_review
    can_dispute = (request.user.pk in (p.client_id, p.freelancer_id))
    reviewee = p.freelancer if request.user.pk == p.client_id else p.client
    return render(request, 'projects/detail.html', {
        'project': p, 'team': t, 'is_owner': p.is_owner(request.user), 'page_title': p.title, 'nav': 'projects',
        'team_members': t.members.select_related('user').all() if t else [],
        'pending_invites': t.invitations.filter(status=TeamInvitation.Status.PENDING).select_related('invitee') if t else [],
        'my_invite': TeamInvitation.objects.filter(team=t, invitee=request.user, status=TeamInvitation.Status.PENDING).first() if t else None,
        'tasks': p.tasks.prefetch_related('subtasks', 'subtasks__assigned_to', 'files').all(),
        'files': p.files.select_related('uploaded_by').all(),
        'comments': p.comments.select_related('author', 'task').prefetch_related('mentions').all(),
        'activities': p.task_activities.select_related('actor', 'task', 'subtask').all()[:30],
        'available_freelancers': services.search_freelancers(query=request.GET.get('q', '').strip(), exclude_team=t) if p.is_owner(request.user) and t else [],
        'reviews': reviews,
        'my_review': my_review,
        'disputes': disputes,
        'can_review': can_review,
        'can_dispute': can_dispute,
        'reviewee': reviewee,
    })

@verified_required
@require_POST
def create_team(request, public_id):
    p = get_object_or_404(Project, public_id=public_id)
    try: services.create_team(p, request.POST.get('name', '').strip() or f"{p.title[:80]} Team", request.user)
    except DomainError as e: messages.error(request, e.message)
    return redirect(f"{reverse('projects:detail', kwargs={'public_id': p.public_id})}#team-workspace")

@verified_required
@require_POST
def invite_member(request, public_id):
    p = get_object_or_404(Project, public_id=public_id)
    if hasattr(p, 'team'):
        invitee = None
        invitee_id = request.POST.get('invitee_id')
        email = request.POST.get('email', '').strip().lower()
        if invitee_id:
            invitee = get_object_or_404(User, pk=invitee_id)
        elif email:
            invitee = User.objects.filter(email__iexact=email).first()
            if not invitee:
                messages.error(request, f"No user registered with email '{email}'.")
                return redirect(f"{reverse('projects:detail', kwargs={'public_id': p.public_id})}#team-workspace")
        else:
            messages.error(request, "Please select a freelancer or provide an email address.")
            return redirect(f"{reverse('projects:detail', kwargs={'public_id': p.public_id})}#team-workspace")
        try:
            services.invite_to_team(p.team, invitee, request.user, request.POST.get('message', ''))
            messages.success(request, f"Invitation sent to {invitee.username} ({invitee.email}).")
        except DomainError as e:
            messages.error(request, e.message)
    return redirect(f"{reverse('projects:detail', kwargs={'public_id': p.public_id})}#team-workspace")

@verified_required
@require_POST
def respond_invitation(request, invitation_id):
    inv = get_object_or_404(TeamInvitation, pk=invitation_id)
    try: services.respond_to_invitation(inv, request.user, (request.POST.get('action') == 'accept'))
    except DomainError as e: messages.error(request, e.message)
    return redirect('projects:detail', public_id=inv.team.project.public_id)

@verified_required
@require_POST
def upload_file(request, public_id):
    p = get_object_or_404(Project, public_id=public_id)
    if 'file' in request.FILES:
        try: services.upload_project_file(p, request.user, request.FILES['file'], request.POST.get('description', ''))
        except DomainError as e: messages.error(request, e.message)
    return redirect('projects:detail', public_id=p.public_id)

@verified_required
def download_file(request, public_id, file_id):
    p = get_object_or_404(Project, public_id=public_id)
    if not p.has_access(request.user): return HttpResponseForbidden("Access Denied.")
    pf = get_object_or_404(ProjectFile, pk=file_id, project=p)
    return FileResponse(pf.file.open('rb'), as_attachment=True, filename=pf.original_name)

@verified_required
@require_POST
def add_comment(request, public_id):
    p = get_object_or_404(Project, public_id=public_id)
    t = Task.objects.filter(pk=request.POST.get('task_id'), project=p).first() if request.POST.get('task_id') else None
    try: services.add_project_comment(p, request.user, request.POST.get('content', ''), t)
    except DomainError as e: messages.error(request, e.message)
    return redirect('projects:detail', public_id=p.public_id)

@verified_required
def project_chat_view(request, public_id):
    p = get_object_or_404(Project, public_id=public_id)
    if not p.has_access(request.user): raise PermissionDenied()
    return render(request, 'projects/chat.html', {'project': p, 'page_title': f'Chat — {p.title}', 'nav': 'projects'})

@verified_required
def project_chat_poll(request, public_id):
    p = get_object_or_404(Project, public_id=public_id)
    if not p.has_access(request.user): return HttpResponseForbidden()
    msgs = [{'id': c.id, 'author': c.author.username, 'author_name': c.author.username, 'is_me': c.author_id == request.user.pk, 'content': c.content, 'task_id': c.task_id, 'task_title': c.task.title if c.task else None, 'created_at': c.created_at.strftime("%I:%M %p · %d %b")} for c in ProjectComment.objects.filter(project=p, id__gt=int(request.GET.get('after_id', 0))).select_related('author', 'task').order_by('id')]
    return JsonResponse({'messages': msgs})

@verified_required
@require_POST
def project_chat_send(request, public_id):
    p = get_object_or_404(Project, public_id=public_id)
    if not p.has_access(request.user): return HttpResponseForbidden()
    body = request.POST.get('content', '').strip()
    if not body: return JsonResponse({'error': 'Empty'}, status=400)
    t = Task.objects.filter(pk=request.POST.get('task_id'), project=p).first() if request.POST.get('task_id') else None
    c = services.add_project_comment(p, request.user, body, t)
    return JsonResponse({'status': 'ok', 'message': {'id': c.id, 'author': c.author.username, 'content': c.content, 'created_at': c.created_at.strftime("%I:%M %p")}})

@verified_required
@require_POST
def submit_review(request, public_id):
    p = get_object_or_404(Project, public_id=public_id)
    if not (request.user.pk in (p.client_id, p.freelancer_id)):
        raise PermissionDenied("Only client or lead freelancer can review this project.")
    if p.status != Project.Status.COMPLETED:
        messages.error(request, "Ratings and reviews can only be submitted after project completion.")
        return redirect('projects:detail', public_id=p.public_id)
    if p.reviews.filter(reviewer=request.user).exists():
        messages.error(request, "You have already reviewed this project.")
        return redirect('projects:detail', public_id=p.public_id)

    reviewee = p.freelancer if request.user.pk == p.client_id else p.client
    try:
        rating = int(request.POST.get('rating', 5))
        if rating < 1 or rating > 5:
            rating = 5
    except Exception:
        rating = 5
    feedback = request.POST.get('feedback', '').strip()
    Review.objects.create(
        project=p,
        reviewer=request.user,
        reviewee=reviewee,
        rating=rating,
        feedback=feedback
    )
    messages.success(request, f"Review submitted successfully ({rating}★).")
    return redirect('projects:detail', public_id=p.public_id)

@verified_required
@require_POST
def submit_dispute(request, public_id):
    p = get_object_or_404(Project, public_id=public_id)
    if not (request.user.pk in (p.client_id, p.freelancer_id)):
        raise PermissionDenied("Only client or lead freelancer can raise a dispute.")
    against = p.freelancer if request.user.pk == p.client_id else p.client
    reason = request.POST.get('reason', 'OTHER')
    description = request.POST.get('description', '').strip()
    if not description:
        messages.error(request, "Dispute description cannot be empty.")
        return redirect('projects:detail', public_id=p.public_id)

    evidence = request.FILES.get('evidence')
    Dispute.objects.create(
        project=p,
        raised_by=request.user,
        against=against,
        reason=reason,
        description=description,
        evidence=evidence,
        status=Dispute.Status.OPEN
    )
    messages.warning(request, "Dispute submitted to Admin for formal investigation.")
    return redirect('projects:detail', public_id=p.public_id)



@verified_required
@require_POST
def project_complete_view(request, public_id):
    p = get_object_or_404(Project.objects.select_related('client', 'freelancer', 'agreement', 'job'), public_id=public_id)
    if request.user.pk != p.client_id and not (getattr(request.user, 'is_platform_admin', False) or request.user.is_superuser):
        raise PermissionDenied("Only the client can approve and complete this project.")
    if p.status == Project.Status.COMPLETED:
        messages.info(request, "This project has already been approved and completed.")
        return redirect('projects:detail', public_id=p.public_id)

    feedback = request.POST.get('feedback', 'Project deliverables approved.')
    if p.agreement:
        from apps.agreements.services import complete_agreement_and_release_payment
        complete_agreement_and_release_payment(agreement=p.agreement, client=request.user, feedback=feedback)
    else:
        from apps.wallets import ledger
        from apps.wallets.models import WalletTransaction
        from apps.tasks.models import Task
        from apps.core.money import ZERO
        from django.db.models import Sum
        from django.utils import timezone

        amount = p.final_price
        freelancer = p.freelancer
        client = p.client

        already_paid_to_members = WalletTransaction.objects.filter(
            project=p,
            task__isnull=False,
            transaction_type=WalletTransaction.Type.PROJECT_PAYMENT
        ).exclude(user=freelancer).aggregate(total=Sum('amount'))['total'] or ZERO

        # Automatically disburse subtask funds to team members for completed tasks
        for t in p.tasks.filter(status=Task.Status.COMPLETED, assigned_to__isnull=False, skillcoin_allocation__gt=ZERO).exclude(assigned_to=freelancer):
            if not WalletTransaction.objects.filter(task=t, transaction_type=WalletTransaction.Type.PROJECT_PAYMENT, user=t.assigned_to).exists():
                t_amt = min(t.skillcoin_allocation, max(ZERO, amount - already_paid_to_members))
                if t_amt > ZERO:
                    c_src = WalletTransaction.Bucket.ESCROW if client.wallet.escrow_balance >= t_amt else (WalletTransaction.Bucket.RESERVED if client.wallet.reserved_balance >= t_amt else WalletTransaction.Bucket.AVAILABLE)
                    d_txn = ledger.move(user=client, amount=t_amt, transaction_type=WalletTransaction.Type.ESCROW_RELEASE, from_bucket=c_src, to_bucket=WalletTransaction.Bucket.EXTERNAL, project=p, task=t, counterparty=t.assigned_to, actor=client, description=f'Escrow release for subtask "{t.title}"')
                    ledger.move(user=t.assigned_to, amount=t_amt, transaction_type=WalletTransaction.Type.PROJECT_PAYMENT, from_bucket=WalletTransaction.Bucket.EXTERNAL, to_bucket=WalletTransaction.Bucket.AVAILABLE, project=p, task=t, counterparty=freelancer, actor=client, related=d_txn, description=f'Milestone subtask payout for "{t.title}" ({p.title})')
                    already_paid_to_members += t_amt

        leader_share = max(ZERO, amount - already_paid_to_members)
        if leader_share > ZERO:
            c_src = WalletTransaction.Bucket.ESCROW if client.wallet.escrow_balance >= leader_share else (WalletTransaction.Bucket.RESERVED if client.wallet.reserved_balance >= leader_share else WalletTransaction.Bucket.AVAILABLE)
            d_txn = ledger.move(user=client, amount=leader_share, transaction_type=WalletTransaction.Type.PROJECT_PAYMENT, from_bucket=c_src, to_bucket=WalletTransaction.Bucket.EXTERNAL, project=p, counterparty=freelancer, actor=client, description=f'Final leader payment for project “{p.title}”')
            ledger.move(user=freelancer, amount=leader_share, transaction_type=WalletTransaction.Type.PROJECT_PAYMENT, from_bucket=WalletTransaction.Bucket.EXTERNAL, to_bucket=WalletTransaction.Bucket.AVAILABLE, project=p, counterparty=client, actor=client, related=d_txn, description=f'Project payment received for “{p.title}”')

        p.status = Project.Status.COMPLETED
        p.completed_at = timezone.now()
        p.save(update_fields=['status', 'completed_at', 'updated_at'])

    messages.success(request, f'Project approved! Milestone escrow payments distributed to team members and remaining funds released to {p.freelancer.username}.')
    return redirect('projects:detail', public_id=p.public_id)
