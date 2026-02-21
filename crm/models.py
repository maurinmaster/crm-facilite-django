from django.db import models
from django.utils import timezone


class Client(models.Model):
    id = models.TextField(primary_key=True)
    org_id = models.TextField(null=True, blank=True)
    name = models.TextField(null=True, blank=True)
    cnpj = models.TextField(null=True, blank=True)
    status = models.TextField(null=True, blank=True)
    type = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'clients'
        managed = False


class ClientContact(models.Model):
    id = models.TextField(primary_key=True)
    client_id = models.TextField(null=True, blank=True)
    name = models.TextField(null=True, blank=True)
    role = models.TextField(null=True, blank=True)
    department = models.TextField(null=True, blank=True)
    phone = models.TextField(null=True, blank=True)
    email = models.TextField(null=True, blank=True)
    instagram = models.TextField(null=True, blank=True)
    notes = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'client_contacts'
        managed = False


class ClientCredentialSimple(models.Model):
    id = models.TextField(primary_key=True)
    client_id = models.TextField(null=True, blank=True)
    site = models.TextField(null=True, blank=True)
    usuario = models.TextField(null=True, blank=True)
    senha = models.TextField(null=True, blank=True)
    token = models.TextField(null=True, blank=True)
    obs = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'client_credentials_simple'
        managed = False


class ClientLink(models.Model):
    id = models.TextField(primary_key=True)
    client_id = models.TextField(null=True, blank=True)
    name = models.TextField(null=True, blank=True)
    url = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'client_links'
        managed = False


class User(models.Model):
    id = models.UUIDField(primary_key=True)
    email = models.TextField(unique=True)
    name = models.TextField()
    password_hash = models.TextField()
    is_admin = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField()

    class Meta:
        db_table = 'users'
        managed = False


class Session(models.Model):
    id = models.UUIDField(primary_key=True)
    user_id = models.UUIDField()
    token = models.TextField(unique=True)
    created_at = models.DateTimeField()
    expires_at = models.DateTimeField()

    class Meta:
        db_table = 'sessions'
        managed = False


# ===== Kanban/Tarefas (novo módulo) =====
class TaskStage(models.Model):
    name = models.CharField(max_length=120, unique=True)
    sort_order = models.PositiveIntegerField(default=0)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'task_stages'
        ordering = ['sort_order', 'name']

    def __str__(self):
        return self.name


class WorkGroup(models.Model):
    name = models.CharField(max_length=140, unique=True)
    description = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'work_groups'
        ordering = ['name']

    def __str__(self):
        return self.name


class Workspace(models.Model):
    name = models.CharField(max_length=140, unique=True)
    description = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'workspaces'
        ordering = ['name']

    def __str__(self):
        return self.name


class Team(models.Model):
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='teams')
    name = models.CharField(max_length=140)
    description = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'teams'
        ordering = ['name']
        unique_together = ('workspace', 'name')

    def __str__(self):
        return f"{self.workspace.name} / {self.name}"


class TeamMember(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='members')
    user_id = models.UUIDField(null=True, blank=True)
    role = models.CharField(max_length=30, default='colaborador')
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'team_members'
        ordering = ['-created_at']


class TaskDemand(models.Model):
    PRIORITY_CHOICES = [
        ('alta', 'Alta'),
        ('media', 'Média'),
        ('baixa', 'Baixa'),
    ]

    title = models.CharField(max_length=240)
    client_id = models.TextField(help_text='ID do cliente na tabela clients')
    description = models.TextField(blank=True, null=True)
    stage = models.ForeignKey(TaskStage, on_delete=models.PROTECT, related_name='task_demands')
    workspace = models.ForeignKey(Workspace, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_demands')
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_demands')
    work_group = models.ForeignKey(WorkGroup, on_delete=models.SET_NULL, null=True, blank=True, related_name='task_demands')
    assigned_to = models.TextField(blank=True, null=True, help_text='Nomes/identificações dos responsáveis')
    due_date = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='media')
    created_by = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(default=timezone.now)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'task_demands'
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class TaskComment(models.Model):
    task = models.ForeignKey(TaskDemand, on_delete=models.CASCADE, related_name='comments')
    comment = models.TextField()
    author = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'task_comments'
        ordering = ['created_at']


class TaskAttachment(models.Model):
    task = models.ForeignKey(TaskDemand, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='task_attachments/%Y/%m/')
    uploaded_by = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'task_attachments'
        ordering = ['-created_at']


class TaskAutomation(models.Model):
    ACTION_CHOICES = [
        ('comment', 'Comentário automático'),
        ('notify', 'Notificação interna'),
    ]

    name = models.CharField(max_length=180)
    workspace = models.ForeignKey(Workspace, on_delete=models.CASCADE, related_name='automations', null=True, blank=True)
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name='automations', null=True, blank=True)
    trigger_from_stage = models.ForeignKey(TaskStage, on_delete=models.SET_NULL, null=True, blank=True, related_name='automations_from')
    trigger_to_stage = models.ForeignKey(TaskStage, on_delete=models.SET_NULL, null=True, blank=True, related_name='automations_to')
    action = models.CharField(max_length=20, choices=ACTION_CHOICES, default='comment')
    message_template = models.TextField(blank=True, null=True)
    active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'task_automations'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class TaskRecurrenceRule(models.Model):
    FREQ_CHOICES = [
        ('daily', 'Diária'),
        ('weekly', 'Semanal'),
        ('monthly', 'Mensal'),
    ]

    name = models.CharField(max_length=180)
    source_task = models.ForeignKey(TaskDemand, on_delete=models.CASCADE, related_name='recurrence_rules')
    frequency = models.CharField(max_length=20, choices=FREQ_CHOICES)
    interval = models.PositiveIntegerField(default=1)
    active = models.BooleanField(default=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    next_run_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'task_recurrence_rules'
        ordering = ['-created_at']

    def __str__(self):
        return self.name


class TaskNotification(models.Model):
    task = models.ForeignKey(TaskDemand, on_delete=models.CASCADE, related_name='notifications')
    team = models.ForeignKey(Team, on_delete=models.SET_NULL, null=True, blank=True)
    event_type = models.CharField(max_length=40)  # created, stage_changed, comment, due_soon, overdue
    message = models.TextField()
    created_at = models.DateTimeField(default=timezone.now)
    read = models.BooleanField(default=False)

    class Meta:
        db_table = 'task_notifications'
        ordering = ['-created_at']
