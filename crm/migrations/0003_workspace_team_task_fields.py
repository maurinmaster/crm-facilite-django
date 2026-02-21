from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0002_taskdemand_position'),
    ]

    operations = [
        migrations.CreateModel(
            name='Workspace',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=140, unique=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
            ],
            options={'db_table': 'workspaces', 'ordering': ['name']},
        ),
        migrations.CreateModel(
            name='Team',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=140)),
                ('description', models.TextField(blank=True, null=True)),
                ('active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('workspace', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='teams', to='crm.workspace')),
            ],
            options={'db_table': 'teams', 'ordering': ['name'], 'unique_together': {('workspace', 'name')}},
        ),
        migrations.CreateModel(
            name='TeamMember',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('user_id', models.UUIDField(blank=True, null=True)),
                ('role', models.CharField(default='colaborador', max_length=30)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('team', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='members', to='crm.team')),
            ],
            options={'db_table': 'team_members', 'ordering': ['-created_at']},
        ),
        migrations.AddField(
            model_name='taskdemand',
            name='workspace',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_demands', to='crm.workspace'),
        ),
        migrations.AddField(
            model_name='taskdemand',
            name='team',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='task_demands', to='crm.team'),
        ),
    ]
