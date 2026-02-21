from django.core.management.base import BaseCommand
from django.utils import timezone
from django.db import models

from crm.models import TaskRecurrenceRule, TaskDemand, TaskComment


def _next_run(base_dt, frequency, interval):
    interval = max(int(interval or 1), 1)
    if frequency == 'daily':
        return base_dt + timezone.timedelta(days=interval)
    if frequency == 'weekly':
        return base_dt + timezone.timedelta(weeks=interval)
    return base_dt + timezone.timedelta(days=30 * interval)


class Command(BaseCommand):
    help = 'Executa regras de recorrência vencidas e cria novas tarefas.'

    def handle(self, *args, **options):
        now = timezone.now()
        rules = TaskRecurrenceRule.objects.filter(active=True).filter(
            models.Q(next_run_at__lte=now) | models.Q(next_run_at__isnull=True)
        )

        created = 0
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
                created_by='recurrence-cron',
                created_at=now,
                updated_at=now,
                position=next_pos,
            )

            TaskComment.objects.create(
                task=new_task,
                comment=f"[AUTO-RECORRÊNCIA] Criada a partir da regra '{r.name}'.",
                author='recurrence-cron',
                created_at=now,
            )

            r.last_run_at = now
            r.next_run_at = _next_run(now, r.frequency, r.interval)
            r.save(update_fields=['last_run_at', 'next_run_at'])
            created += 1

        self.stdout.write(self.style.SUCCESS(f'Recorrências executadas. Novas tarefas: {created}'))
