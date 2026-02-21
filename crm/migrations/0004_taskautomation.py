from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0003_workspace_team_task_fields'),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskAutomation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=180)),
                ('action', models.CharField(choices=[('comment', 'Comentário automático'), ('notify', 'Notificação interna')], default='comment', max_length=20)),
                ('message_template', models.TextField(blank=True, null=True)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('team', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='automations', to='crm.team')),
                ('trigger_from_stage', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='automations_from', to='crm.taskstage')),
                ('trigger_to_stage', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='automations_to', to='crm.taskstage')),
                ('workspace', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='automations', to='crm.workspace')),
            ],
            options={
                'db_table': 'task_automations',
                'ordering': ['-created_at'],
            },
        ),
    ]
