import uuid
from io import BytesIO
from PIL import Image
from django.core.files.base import ContentFile

from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_http_methods
from django.core.paginator import Paginator
from django.utils import timezone
from django.db import models
from django.core.files.storage import default_storage

from openpyxl import Workbook

from .auth import authenticate, create_session, destroy_session
from .models import (
    Client, ClientContact, ClientCredentialSimple, ClientLink,
    User,
    TaskStage, WorkGroup, TaskDemand, TaskComment, TaskAttachment, TaskAutomation, TaskRecurrenceRule, TaskNotification,
    Workspace, Team, TeamMember,
)


def require_login(request):
    if not getattr(request, 'user_ctx', None):
        return redirect('/login/?next=' + request.path)
    return None


def _allowed_team_ids(user):
    if user.is_admin:
        return None
    return list(TeamMember.objects.filter(user_id=user.id).values_list('team_id', flat=True))


def _team_role(user, team_id):
    if user.is_admin:
        return 'admin'
    m = TeamMember.objects.filter(user_id=user.id, team_id=team_id).first()
    return m.role if m else None


def _can_manage_task(user, task):
    if user.is_admin:
        return True
    role = _team_role(user, task.team_id)
    return role in ('gerente', 'admin_workspace')


def _can_interact_task(user, task):
    if user.is_admin:
        return True
    role = _team_role(user, task.team_id)
    if role in ('gerente', 'admin_workspace', 'colaborador'):
        if role == 'colaborador':
            ass = (task.assigned_to or '').lower()
            return (user.email or '').lower() in ass or (user.name or '').lower() in ass
        return True
    return False


def _notify(task, event_type, message):
    TaskNotification.objects.create(
        task=task,
        team_id=task.team_id,
        event_type=event_type,
        message=message,
        created_at=timezone.now(),
        read=False,
    )


def _run_stage_automations(task, old_stage_id, new_stage_id, actor_email=None):
    autos = TaskAutomation.objects.filter(active=True)
    if task.workspace_id:
        autos = autos.filter(models.Q(workspace_id=task.workspace_id) | models.Q(workspace__isnull=True))
    if task.team_id:
        autos = autos.filter(models.Q(team_id=task.team_id) | models.Q(team__isnull=True))

    for a in autos:
        if a.trigger_from_stage_id and a.trigger_from_stage_id != old_stage_id:
            continue
        if a.trigger_to_stage_id and a.trigger_to_stage_id != new_stage_id:
            continue

        msg = (a.message_template or '').strip()
        if not msg:
            msg = f"Automação '{a.name}' executada na mudança de estágio."

        msg = msg.replace('{{task_title}}', task.title or '')
        msg = msg.replace('{{from_stage}}', str(old_stage_id or ''))
        msg = msg.replace('{{to_stage}}', str(new_stage_id or ''))

        # Nesta versão, ações viram registro no histórico de comentários.
        prefix = '[AUTO]' if a.action == 'comment' else '[AUTO-NOTIFY]'
        TaskComment.objects.create(
            task=task,
            comment=f"{prefix} {msg}",
            author=actor_email or 'automation',
            created_at=timezone.now(),
        )


def _next_run(base_dt, frequency, interval):
    interval = max(int(interval or 1), 1)
    if frequency == 'daily':
        return base_dt + timezone.timedelta(days=interval)
    if frequency == 'weekly':
        return base_dt + timezone.timedelta(weeks=interval)
    # monthly (aproximação operacional: +30 dias * intervalo)
    return base_dt + timezone.timedelta(days=30 * interval)


def _ensure_due_notifications(base_qs):
    today = timezone.now().date()
    tomorrow = today + timezone.timedelta(days=1)

    due_soon = base_qs.filter(due_date=tomorrow)
    for t in due_soon:
        key = f"[DUE_SOON:{tomorrow.isoformat()}]"
        if not TaskNotification.objects.filter(task=t, event_type='due_soon', message__contains=key).exists():
            _notify(t, 'due_soon', f"{key} Tarefa '{t.title}' vence amanhã.")

    overdue = base_qs.filter(due_date__lt=today).exclude(stage__name__icontains='done').exclude(stage__name__icontains='concl')
    for t in overdue:
        key = f"[OVERDUE:{today.isoformat()}]"
        if not TaskNotification.objects.filter(task=t, event_type='overdue', message__contains=key).exists():
            _notify(t, 'overdue', f"{key} Tarefa '{t.title}' está atrasada.")


def _execute_due_recurrences(actor_email='system'):
    now = timezone.now()
    rules = TaskRecurrenceRule.objects.filter(active=True).filter(models.Q(next_run_at__lte=now) | models.Q(next_run_at__isnull=True))
    for r in rules:
        src = r.source_task
        if not src:
            continue

        last_pos = TaskDemand.objects.filter(stage_id=src.stage_id).order_by('-position').first()
        next_pos = (last_pos.position + 1) if last_pos else 1

        new_task = TaskDemand.objects.create(
            title=src.title,
            client_id=src.client_id,
            description=src.description,
            stage_id=src.stage_id,
            workspace_id=src.workspace_id,
            team_id=src.team_id,
            work_group_id=None,
            assigned_to=src.assigned_to,
            due_date=src.due_date,
            priority=src.priority,
            created_by=actor_email,
            created_at=now,
            updated_at=now,
            position=next_pos,
        )

        TaskComment.objects.create(
            task=new_task,
            comment=f"[AUTO-RECORRÊNCIA] Criada a partir da regra '{r.name}'.",
            author=actor_email,
            created_at=now,
        )

        r.last_run_at = now
        r.next_run_at = _next_run(now, r.frequency, r.interval)
        r.save(update_fields=['last_run_at', 'next_run_at'])


def home(request):
    return redirect('/clients/')


@require_http_methods(["GET", "POST"])
def login_view(request):
    if request.method == 'GET':
        return render(request, 'login.html', { 'next': request.GET.get('next', '/clients/'), 'error': None })

    email = request.POST.get('email', '')
    password = request.POST.get('password', '')
    nxt = request.POST.get('next', '/clients/')

    u = authenticate(email, password)
    if not u:
        return render(request, 'login.html', { 'next': nxt, 'error': 'Credenciais inválidas' })

    token, exp = create_session(u.id)
    resp = redirect(nxt or '/clients/')
    resp.set_cookie('crm_session', token, httponly=True, secure=True, samesite='Lax', path='/', max_age=60*60*24*14)
    return resp


@require_http_methods(["POST", "GET"])
def logout_view(request):
    tok = request.COOKIES.get('crm_session')
    destroy_session(tok)
    resp = redirect('/login/')
    resp.delete_cookie('crm_session', path='/')
    return resp


def clients_list(request):
    guard = require_login(request)
    if guard: return guard

    q = (request.GET.get('q') or '').strip()
    page = int(request.GET.get('page') or '1')

    qs = Client.objects.all().order_by('name')
    if q:
        qs = qs.filter(name__icontains=q)

    paginator = Paginator(qs, 25)
    p = paginator.get_page(page)

    return render(request, 'clients.html', {
        'q': q,
        'page_obj': p,
    })


def client_detail(request, client_id):
    guard = require_login(request)
    if guard: return guard

    c = Client.objects.filter(id=client_id).first()
    if not c:
        return HttpResponse('Not found', status=404)

    contacts = ClientContact.objects.filter(client_id=client_id).order_by('-created_at')
    creds = ClientCredentialSimple.objects.filter(client_id=client_id).order_by('-created_at')
    links = ClientLink.objects.filter(client_id=client_id).order_by('-created_at')

    return render(request, 'client_detail.html', {
        'client': c,
        'contacts': contacts,
        'creds': creds,
        'links': links,
    })


@require_http_methods(["GET", "POST"])
def client_new(request):
    guard = require_login(request)
    if guard: return guard

    if request.method == 'GET':
        return render(request, 'client_form.html', { 'title': 'Novo cliente', 'client': {}, 'error': None })

    cid = str(uuid.uuid4())
    name = (request.POST.get('name') or '').strip()
    if not name:
        return render(request, 'client_form.html', { 'title': 'Novo cliente', 'client': request.POST, 'error': 'Nome obrigatório' })

    Client.objects.create(
        id=cid,
        name=name,
        cnpj=(request.POST.get('cnpj') or '').strip() or None,
        status=(request.POST.get('status') or '').strip() or None,
        type=(request.POST.get('type') or '').strip() or None,
        notes=(request.POST.get('notes') or '').strip() or None,
        created_at=timezone.now(),
        updated_at=timezone.now(),
    )
    return redirect(f'/clients/{cid}/')


@require_http_methods(["GET", "POST"])
def client_edit(request, client_id):
    guard = require_login(request)
    if guard: return guard

    c = Client.objects.filter(id=client_id).first()
    if not c:
        return HttpResponse('Not found', status=404)

    if request.method == 'GET':
        return render(request, 'client_form.html', { 'title': 'Editar cliente', 'client': c, 'error': None })

    name = (request.POST.get('name') or '').strip()
    if not name:
        return render(request, 'client_form.html', { 'title': 'Editar cliente', 'client': c, 'error': 'Nome obrigatório' })

    c.name = name
    c.cnpj = (request.POST.get('cnpj') or '').strip() or None
    c.status = (request.POST.get('status') or '').strip() or None
    c.type = (request.POST.get('type') or '').strip() or None
    c.notes = (request.POST.get('notes') or '').strip() or None
    c.updated_at = timezone.now()
    c.save(update_fields=['name', 'cnpj', 'status', 'type', 'notes', 'updated_at'])

    return redirect(f'/clients/{client_id}/')


@require_http_methods(["POST"])
def client_delete(request, client_id):
    guard = require_login(request)
    if guard: return guard

    Client.objects.filter(id=client_id).delete()
    ClientContact.objects.filter(client_id=client_id).delete()
    ClientCredentialSimple.objects.filter(client_id=client_id).delete()
    ClientLink.objects.filter(client_id=client_id).delete()
    return redirect('/clients/')


@require_http_methods(["POST"])
def contact_new(request, client_id):
    guard = require_login(request)
    if guard: return guard

    ClientContact.objects.create(
        id=str(uuid.uuid4()),
        client_id=client_id,
        name=(request.POST.get('name') or '').strip() or None,
        role=(request.POST.get('role') or '').strip() or None,
        department=(request.POST.get('department') or '').strip() or None,
        phone=(request.POST.get('phone') or '').strip() or None,
        email=(request.POST.get('email') or '').strip() or None,
        instagram=(request.POST.get('instagram') or '').strip() or None,
        notes=(request.POST.get('notes') or '').strip() or None,
        created_at=timezone.now(),
    )
    return redirect(f'/clients/{client_id}/')


@require_http_methods(["POST"])
def contact_delete(request, contact_id):
    guard = require_login(request)
    if guard: return guard

    c = ClientContact.objects.filter(id=contact_id).first()
    if not c:
        return redirect('/clients/')
    client_id = c.client_id
    ClientContact.objects.filter(id=contact_id).delete()
    return redirect(f'/clients/{client_id}/')


@require_http_methods(["POST"])
def cred_new(request, client_id):
    guard = require_login(request)
    if guard: return guard

    ClientCredentialSimple.objects.create(
        id=str(uuid.uuid4()),
        client_id=client_id,
        site=(request.POST.get('site') or '').strip() or None,
        usuario=(request.POST.get('usuario') or '').strip() or None,
        senha=(request.POST.get('senha') or '').strip() or None,
        token=(request.POST.get('token') or '').strip() or None,
        obs=(request.POST.get('obs') or '').strip() or None,
        created_at=timezone.now(),
    )
    return redirect(f'/clients/{client_id}/')


@require_http_methods(["POST"])
def cred_delete(request, cred_id):
    guard = require_login(request)
    if guard: return guard

    c = ClientCredentialSimple.objects.filter(id=cred_id).first()
    if not c:
        return redirect('/clients/')
    client_id = c.client_id
    ClientCredentialSimple.objects.filter(id=cred_id).delete()
    return redirect(f'/clients/{client_id}/')


@require_http_methods(["POST"])
def link_new(request, client_id):
    guard = require_login(request)
    if guard: return guard

    ClientLink.objects.create(
        id=str(uuid.uuid4()),
        client_id=client_id,
        name=(request.POST.get('name') or '').strip() or None,
        url=(request.POST.get('url') or '').strip() or None,
        created_at=timezone.now(),
    )
    return redirect(f'/clients/{client_id}/')


@require_http_methods(["POST"])
def link_delete(request, link_id):
    guard = require_login(request)
    if guard: return guard

    l = ClientLink.objects.filter(id=link_id).first()
    if not l:
        return redirect('/clients/')
    client_id = l.client_id
    ClientLink.objects.filter(id=link_id).delete()
    return redirect(f'/clients/{client_id}/')


def export_xlsx(request):
    guard = require_login(request)
    if guard: return guard

    wb = Workbook()

    def norm(v):
        try:
            if hasattr(v, 'tzinfo') and v.tzinfo is not None:
                return v.replace(tzinfo=None)
        except Exception:
            pass
        return v

    def add_sheet(name, rows, headers):
        ws = wb.create_sheet(title=name)
        ws.append(headers)
        for r in rows:
            ws.append([norm(getattr(r, h)) for h in headers])

    wb.remove(wb.active)

    add_sheet('clients', Client.objects.all().order_by('name'), ['id','org_id','name','cnpj','status','type','notes','updated_at','created_at'])
    add_sheet('client_contacts', ClientContact.objects.all().order_by('-created_at'), ['id','client_id','name','role','department','phone','email','instagram','notes','created_at'])
    add_sheet('client_credentials_simple', ClientCredentialSimple.objects.all().order_by('-created_at'), ['id','client_id','site','usuario','senha','token','obs','created_at'])
    add_sheet('client_links', ClientLink.objects.all().order_by('-created_at'), ['id','client_id','name','url','created_at'])

    bio = BytesIO()
    wb.save(bio)
    bio.seek(0)

    resp = HttpResponse(
        bio.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )
    resp['Content-Disposition'] = 'attachment; filename="crm_facilite_export.xlsx"'
    return resp


# ===== Módulo de Tarefas =====
def notifications_unread_count(request):
    guard = require_login(request)
    if guard:
        return JsonResponse({'count': 0}, status=401)

    user = request.user_ctx['user']
    allowed_team_ids = _allowed_team_ids(user)

    qs = TaskNotification.objects.all()
    if allowed_team_ids is not None:
        qs = qs.filter(models.Q(team_id__in=allowed_team_ids) | models.Q(team__isnull=True))

    return JsonResponse({'count': qs.filter(read=False).count()})


def notifications_list(request):
    guard = require_login(request)
    if guard: return guard

    user = request.user_ctx['user']
    allowed_team_ids = _allowed_team_ids(user)

    qs = TaskNotification.objects.select_related('task', 'team').all()
    if allowed_team_ids is not None:
        qs = qs.filter(models.Q(team_id__in=allowed_team_ids) | models.Q(team__isnull=True))

    notifications = qs.order_by('-created_at')[:200]
    unread_count = qs.filter(read=False).count()

    return render(request, 'notifications.html', {
        'notifications': notifications,
        'unread_count': unread_count,
    })


@require_http_methods(["POST"])
def notifications_mark_read(request, notification_id=None):
    guard = require_login(request)
    if guard: return guard

    user = request.user_ctx['user']
    allowed_team_ids = _allowed_team_ids(user)

    qs = TaskNotification.objects.all()
    if allowed_team_ids is not None:
        qs = qs.filter(models.Q(team_id__in=allowed_team_ids) | models.Q(team__isnull=True))

    if notification_id:
        qs.filter(id=notification_id).update(read=True)
    else:
        qs.filter(read=False).update(read=True)

    return redirect('/tasks/notifications/')


def workload_dashboard(request):
    guard = require_login(request)
    if guard: return guard

    user = request.user_ctx['user']
    allowed_team_ids = _allowed_team_ids(user)

    days = int((request.GET.get('days') or '30').strip() or '30')
    start_date = timezone.now().date() - timezone.timedelta(days=days)

    teams = Team.objects.filter(active=True).select_related('workspace').order_by('workspace__name', 'name')
    if allowed_team_ids is not None:
        teams = teams.filter(id__in=allowed_team_ids)

    rows = []
    max_total = 1
    for tm in teams:
        qs = TaskDemand.objects.filter(team=tm, created_at__date__gte=start_date)
        total = qs.count()
        done = qs.filter(stage__name__icontains='concl').count() + qs.filter(stage__name__icontains='done').count()
        em_producao = qs.filter(stage__name__icontains='produção').count() + qs.filter(stage__name__icontains='doing').count()
        fila = qs.filter(stage__name__icontains='fila').count() + qs.filter(stage__name__icontains='todo').count()
        overdue = qs.filter(due_date__lt=timezone.now().date()).exclude(stage__name__icontains='done').count()
        max_total = max(max_total, total)
        rows.append({
            'workspace': tm.workspace.name,
            'team': tm.name,
            'total': total,
            'fila': fila,
            'em_producao': em_producao,
            'done': done,
            'overdue': overdue,
        })

    for r in rows:
        r['pct'] = int((r['total'] / max_total) * 100) if max_total else 0

    return render(request, 'workload_dashboard.html', {'rows': rows, 'days': days})


def tasks_dashboard(request):
    guard = require_login(request)
    if guard: return guard

    user = request.user_ctx['user']
    q = (request.GET.get('q') or '').strip()
    stage_id = (request.GET.get('stage') or '').strip()
    priority = (request.GET.get('priority') or '').strip()
    workspace_id = (request.GET.get('workspace') or '').strip()
    team_id = (request.GET.get('team') or '').strip()

    tasks = TaskDemand.objects.select_related('stage', 'workspace', 'team').all().order_by('stage_id', 'position', '-created_at')
    allowed_team_ids = _allowed_team_ids(user)
    if allowed_team_ids is not None:
        tasks = tasks.filter(team_id__in=allowed_team_ids)
    if q:
        tasks = tasks.filter(title__icontains=q)
    if stage_id:
        tasks = tasks.filter(stage_id=stage_id)
    if priority:
        tasks = tasks.filter(priority=priority)
    if workspace_id:
        tasks = tasks.filter(workspace_id=workspace_id)
    if team_id:
        tasks = tasks.filter(team_id=team_id)

    stages = TaskStage.objects.filter(active=True).order_by('sort_order', 'name')
    stage_cards = []
    for s in stages:
        stage_cards.append({'id': s.id, 'name': s.name, 'count': tasks.filter(stage=s).count()})

    client_map = {c.id: c.name for c in Client.objects.filter(id__in=[t.client_id for t in tasks])}
    for t in tasks:
        t.client_name = client_map.get(t.client_id, '—')

    tasks_by_stage = {}
    for s in stages:
        tasks_by_stage[s.id] = [t for t in tasks if t.stage_id == s.id]

    _ensure_due_notifications(tasks)

    workspaces = Workspace.objects.filter(active=True).order_by('name')
    teams = Team.objects.filter(active=True).select_related('workspace').order_by('workspace__name', 'name')
    if allowed_team_ids is not None:
        teams = teams.filter(id__in=allowed_team_ids)

    return render(request, 'tasks_dashboard.html', {
        'tasks': tasks,
        'stages': stages,
        'stage_cards': stage_cards,
        'tasks_by_stage': tasks_by_stage,
        'workspaces': workspaces,
        'teams': teams,
        'q': q,
        'stage_id': stage_id,
        'priority': priority,
        'workspace_id': workspace_id,
        'team_id': team_id,
        'total': tasks.count(),
    })


@require_http_methods(["GET", "POST"])
def tasks_settings(request):
    guard = require_login(request)
    if guard: return guard

    user = request.user_ctx['user']
    if not user.is_admin:
        return HttpResponse('Apenas admin pode configurar estágios e grupos.', status=403)

    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'add_stage':
            name = (request.POST.get('name') or '').strip()
            sort_order = int(request.POST.get('sort_order') or '0')
            if name:
                TaskStage.objects.create(name=name, sort_order=sort_order)
        elif action == 'add_automation':
            name = (request.POST.get('name') or '').strip()
            from_stage = (request.POST.get('trigger_from_stage_id') or '').strip()
            to_stage = (request.POST.get('trigger_to_stage_id') or '').strip()
            action_type = (request.POST.get('automation_action') or 'comment').strip()
            msg = (request.POST.get('message_template') or '').strip()
            ws_id = (request.POST.get('workspace_id') or '').strip()
            team_id = (request.POST.get('team_id') or '').strip()
            if name:
                TaskAutomation.objects.create(
                    name=name,
                    trigger_from_stage_id=(from_stage or None),
                    trigger_to_stage_id=(to_stage or None),
                    action=action_type,
                    message_template=msg or None,
                    workspace_id=(ws_id or None),
                    team_id=(team_id or None),
                    active=True,
                )
        elif action == 'toggle_automation':
            aid = (request.POST.get('automation_id') or '').strip()
            a = TaskAutomation.objects.filter(id=aid).first()
            if a:
                a.active = not a.active
                a.save(update_fields=['active'])
        elif action == 'add_recurrence':
            name = (request.POST.get('name') or '').strip()
            source_task_id = (request.POST.get('source_task_id') or '').strip()
            frequency = (request.POST.get('frequency') or 'weekly').strip()
            interval = int((request.POST.get('interval') or '1').strip() or '1')
            if name and source_task_id:
                now = timezone.now()
                TaskRecurrenceRule.objects.create(
                    name=name,
                    source_task_id=source_task_id,
                    frequency=frequency,
                    interval=max(interval, 1),
                    active=True,
                    last_run_at=None,
                    next_run_at=_next_run(now, frequency, max(interval, 1)),
                    created_at=now,
                )
        elif action == 'toggle_recurrence':
            rid = (request.POST.get('rule_id') or '').strip()
            r = TaskRecurrenceRule.objects.filter(id=rid).first()
            if r:
                r.active = not r.active
                r.save(update_fields=['active'])
        elif action == 'run_recurrence_now':
            _execute_due_recurrences(actor_email=user.email)

        return redirect('/tasks/settings/')

    return render(request, 'tasks_settings.html', {
        'stages': TaskStage.objects.all().order_by('sort_order', 'name'),
        'workspaces': Workspace.objects.filter(active=True).order_by('name'),
        'teams': Team.objects.filter(active=True).select_related('workspace').order_by('workspace__name', 'name'),
        'automations': TaskAutomation.objects.select_related('workspace', 'team', 'trigger_from_stage', 'trigger_to_stage').all().order_by('-created_at'),
        'recurrence_rules': TaskRecurrenceRule.objects.select_related('source_task').all().order_by('-created_at'),
        'task_sources': TaskDemand.objects.all().order_by('-created_at')[:200],
    })


@require_http_methods(["GET", "POST"])
def teams_settings(request):
    guard = require_login(request)
    if guard: return guard

    user = request.user_ctx['user']
    if not user.is_admin:
        return HttpResponse('Apenas admin pode configurar equipes.', status=403)

    if request.method == 'POST':
        action = (request.POST.get('action') or '').strip()

        if action == 'add_workspace':
            name = (request.POST.get('name') or '').strip()
            desc = (request.POST.get('description') or '').strip()
            if name:
                Workspace.objects.create(name=name, description=desc or None)

        elif action == 'edit_workspace':
            ws_id = (request.POST.get('workspace_id') or '').strip()
            name = (request.POST.get('name') or '').strip()
            desc = (request.POST.get('description') or '').strip()
            ws = Workspace.objects.filter(id=ws_id).first()
            if ws and name:
                ws.name = name
                ws.description = desc or None
                ws.save(update_fields=['name', 'description'])

        elif action == 'delete_workspace':
            ws_id = (request.POST.get('workspace_id') or '').strip()
            ws = Workspace.objects.filter(id=ws_id).first()
            if ws:
                ws.delete()

        elif action == 'add_team':
            ws_id = (request.POST.get('workspace_id') or '').strip()
            name = (request.POST.get('name') or '').strip()
            desc = (request.POST.get('description') or '').strip()
            if ws_id and name:
                Team.objects.create(workspace_id=ws_id, name=name, description=desc or None)

        elif action == 'edit_team':
            team_id = (request.POST.get('team_id') or '').strip()
            ws_id = (request.POST.get('workspace_id') or '').strip()
            name = (request.POST.get('name') or '').strip()
            desc = (request.POST.get('description') or '').strip()
            t = Team.objects.filter(id=team_id).first()
            if t and ws_id and name:
                t.workspace_id = ws_id
                t.name = name
                t.description = desc or None
                t.save(update_fields=['workspace', 'name', 'description'])

        elif action == 'delete_team':
            team_id = (request.POST.get('team_id') or '').strip()
            t = Team.objects.filter(id=team_id).first()
            if t:
                t.delete()

        elif action == 'add_member':
            team_id = (request.POST.get('team_id') or '').strip()
            user_id = (request.POST.get('user_id') or '').strip()
            role = (request.POST.get('role') or 'colaborador').strip()
            if team_id and user_id:
                TeamMember.objects.get_or_create(team_id=team_id, user_id=user_id, defaults={'role': role})

        elif action == 'remove_member':
            member_id = (request.POST.get('member_id') or '').strip()
            if member_id:
                TeamMember.objects.filter(id=member_id).delete()

        return redirect('/teams/settings/')

    users = User.objects.filter(active=True).order_by('name')
    members = TeamMember.objects.select_related('team', 'team__workspace').all().order_by('team__workspace__name', 'team__name', '-created_at')

    return render(request, 'teams_settings.html', {
        'workspaces': Workspace.objects.all().order_by('name'),
        'teams': Team.objects.select_related('workspace').all().order_by('workspace__name', 'name'),
        'users': users,
        'members': members,
    })


@require_http_methods(["POST"])
def task_stage_delete(request, stage_id):
    guard = require_login(request)
    if guard: return guard
    TaskStage.objects.filter(id=stage_id).delete()
    return redirect('/tasks/settings/')


@require_http_methods(["POST"])
def work_group_delete(request, group_id):
    guard = require_login(request)
    if guard: return guard
    WorkGroup.objects.filter(id=group_id).delete()
    return redirect('/tasks/settings/')


@require_http_methods(["GET", "POST"])
def task_new(request):
    guard = require_login(request)
    if guard: return guard

    user = request.user_ctx['user']
    allowed_team_ids = _allowed_team_ids(user)

    stages = TaskStage.objects.filter(active=True).order_by('sort_order', 'name')
    clients = Client.objects.all().order_by('name')
    workspaces = Workspace.objects.filter(active=True).order_by('name')
    teams = Team.objects.filter(active=True).select_related('workspace').order_by('workspace__name', 'name')
    if allowed_team_ids is not None:
        teams = teams.filter(id__in=allowed_team_ids)

    if request.method == 'GET':
        return render(request, 'task_form.html', {
            'stages': stages,
            'clients': clients,
            'workspaces': workspaces,
            'teams': teams,
            'error': None,
        })

    title = (request.POST.get('title') or '').strip()
    client_id = (request.POST.get('client_id') or '').strip()
    stage_id = (request.POST.get('stage_id') or '').strip()

    if not title or not client_id or not stage_id:
        return render(request, 'task_form.html', {
            'stages': stages,
            'clients': clients,
            'workspaces': workspaces,
            'teams': teams,
            'error': 'Título, cliente e estágio são obrigatórios.',
        })

    selected_team_id = (request.POST.get('team_id') or None) or None
    if allowed_team_ids is not None and selected_team_id and int(selected_team_id) not in allowed_team_ids:
        return HttpResponse('Sem permissão para essa equipe', status=403)

    if not user.is_admin and selected_team_id:
        role = _team_role(user, int(selected_team_id))
        if role not in ('gerente', 'admin_workspace'):
            return HttpResponse('Sem permissão para criar tarefa nesta equipe', status=403)

    last_pos = TaskDemand.objects.filter(stage_id=stage_id).order_by('-position').first()
    next_pos = (last_pos.position + 1) if last_pos else 1

    task = TaskDemand.objects.create(
        title=title,
        client_id=client_id,
        description=(request.POST.get('description') or '').strip() or None,
        stage_id=stage_id,
        workspace_id=(request.POST.get('workspace_id') or None) or None,
        team_id=selected_team_id,
        work_group_id=None,
        assigned_to=(request.POST.get('assigned_to') or '').strip() or None,
        due_date=(request.POST.get('due_date') or None) or None,
        priority=(request.POST.get('priority') or 'media'),
        created_by=(request.user_ctx['user'].email if getattr(request, 'user_ctx', None) else None),
        created_at=timezone.now(),
        updated_at=timezone.now(),
        position=next_pos,
    )

    files = request.FILES.getlist('attachments')
    for f in files:
        TaskAttachment.objects.create(
            task=task,
            file=f,
            uploaded_by=(request.user_ctx['user'].email if getattr(request, 'user_ctx', None) else None),
            created_at=timezone.now(),
        )

    _notify(task, 'created', f"Nova tarefa criada: {task.title}")

    return redirect(f'/tasks/{task.id}/')


@require_http_methods(["POST"])
def task_move(request, task_id):
    guard = require_login(request)
    if guard: return guard

    task = TaskDemand.objects.filter(id=task_id).first()
    if not task:
        return HttpResponse('Not found', status=404)

    user = request.user_ctx['user']
    allowed_team_ids = _allowed_team_ids(user)
    if allowed_team_ids is not None and (task.team_id not in allowed_team_ids):
        return HttpResponse('Sem permissão', status=403)
    if not _can_manage_task(user, task):
        return HttpResponse('Sem permissão para mover tarefa', status=403)

    stage_id = (request.POST.get('stage_id') or '').strip()
    if not stage_id:
        return HttpResponse('stage_id obrigatório', status=400)

    stage = TaskStage.objects.filter(id=stage_id, active=True).first()
    if not stage:
        return HttpResponse('stage inválido', status=400)

    old_stage_id = task.stage_id
    old_stage_name = TaskStage.objects.filter(id=old_stage_id).values_list('name', flat=True).first() or '—'
    task.stage = stage
    task.updated_at = timezone.now()
    task.save(update_fields=['stage', 'updated_at'])
    _run_stage_automations(task, old_stage_id, task.stage_id, actor_email=user.email)
    _notify(task, 'stage_changed', f"Tarefa '{task.title}' movida de {old_stage_name} para {stage.name}")
    return HttpResponse('ok', status=200)


@require_http_methods(["POST"])
def task_reorder(request, task_id):
    guard = require_login(request)
    if guard: return guard

    task = TaskDemand.objects.filter(id=task_id).first()
    if not task:
        return HttpResponse('Not found', status=404)

    user = request.user_ctx['user']
    allowed_team_ids = _allowed_team_ids(user)
    if allowed_team_ids is not None and (task.team_id not in allowed_team_ids):
        return HttpResponse('Sem permissão', status=403)
    if not _can_manage_task(user, task):
        return HttpResponse('Sem permissão para reordenar tarefa', status=403)

    direction = (request.POST.get('direction') or '').strip()
    siblings = list(TaskDemand.objects.filter(stage_id=task.stage_id).order_by('position', 'id'))
    idx = next((i for i, t in enumerate(siblings) if t.id == task.id), None)
    if idx is None:
        return HttpResponse('not found', status=404)

    if direction == 'up' and idx > 0:
        prev_task = siblings[idx - 1]
        task.position, prev_task.position = prev_task.position, task.position
        task.save(update_fields=['position'])
        prev_task.save(update_fields=['position'])
    elif direction == 'down' and idx < len(siblings) - 1:
        next_task = siblings[idx + 1]
        task.position, next_task.position = next_task.position, task.position
        task.save(update_fields=['position'])
        next_task.save(update_fields=['position'])

    return redirect('/tasks/')


@require_http_methods(["POST"])
def task_editor_upload(request):
    guard = require_login(request)
    if guard:
        return JsonResponse({'error': 'unauthorized'}, status=401)

    f = request.FILES.get('file')
    if not f:
        return JsonResponse({'error': 'file obrigatório'}, status=400)

    try:
        img = Image.open(f)
        img = img.convert('RGB')

        # Redimensiona se imagem for muito grande (mantendo proporção)
        max_w, max_h = 1920, 1920
        img.thumbnail((max_w, max_h))

        # Compressão automática JPEG
        out = BytesIO()
        img.save(out, format='JPEG', quality=75, optimize=True)
        out.seek(0)

        filename = f"task_editor/{uuid.uuid4().hex}.jpg"
        content = ContentFile(out.read(), name=filename.split('/')[-1])
        path = default_storage.save(filename, content)
        url = default_storage.url(path)
        return JsonResponse({'location': url})
    except Exception:
        # fallback para arquivos que não forem imagem
        ext = ''
        if '.' in f.name:
            ext = '.' + f.name.split('.')[-1].lower()
        filename = f"task_editor/{uuid.uuid4().hex}{ext}"
        path = default_storage.save(filename, f)
        url = default_storage.url(path)
        return JsonResponse({'location': url})


@require_http_methods(["GET", "POST"])
def task_detail(request, task_id):
    guard = require_login(request)
    if guard: return guard

    task = TaskDemand.objects.select_related('stage', 'workspace', 'team').filter(id=task_id).first()
    if not task:
        return HttpResponse('Not found', status=404)

    user = request.user_ctx['user']
    allowed_team_ids = _allowed_team_ids(user)
    if allowed_team_ids is not None and (task.team_id not in allowed_team_ids):
        return HttpResponse('Sem permissão', status=403)

    task.client_obj = Client.objects.filter(id=task.client_id).first()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'comment':
            if not _can_interact_task(user, task):
                return HttpResponse('Sem permissão para comentar', status=403)
            txt = (request.POST.get('comment') or '').strip()
            if txt:
                TaskComment.objects.create(
                    task=task,
                    comment=txt,
                    author=(user.email if getattr(request, 'user_ctx', None) else None),
                    created_at=timezone.now(),
                )
                _notify(task, 'comment', f"Novo comentário em '{task.title}' por {user.name or user.email}")
        elif action == 'stage':
            if not _can_manage_task(user, task):
                return HttpResponse('Sem permissão para mover estágio', status=403)
            sid = (request.POST.get('stage_id') or '').strip()
            if sid:
                old_stage_id = task.stage_id
                old_stage_name = TaskStage.objects.filter(id=old_stage_id).values_list('name', flat=True).first() or '—'
                task.stage_id = sid
                task.updated_at = timezone.now()
                task.save(update_fields=['stage', 'updated_at'])
                _run_stage_automations(task, old_stage_id, task.stage_id, actor_email=user.email)
                new_stage_name = TaskStage.objects.filter(id=task.stage_id).values_list('name', flat=True).first() or '—'
                _notify(task, 'stage_changed', f"Tarefa '{task.title}' movida de {old_stage_name} para {new_stage_name}")
        elif action == 'attach':
            if not _can_interact_task(user, task):
                return HttpResponse('Sem permissão para anexar', status=403)
            files = request.FILES.getlist('attachments')
            for f in files:
                TaskAttachment.objects.create(
                    task=task,
                    file=f,
                    uploaded_by=(user.email if getattr(request, 'user_ctx', None) else None),
                    created_at=timezone.now(),
                )
        return redirect(f'/tasks/{task.id}/')

    return render(request, 'task_detail.html', {
        'task': task,
        'comments': task.comments.all().order_by('created_at'),
        'attachments': task.attachments.all().order_by('-created_at'),
        'stages': TaskStage.objects.filter(active=True).order_by('sort_order', 'name'),
    })
