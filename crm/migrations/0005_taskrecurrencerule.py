from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0004_taskautomation'),
    ]

    operations = [
        migrations.CreateModel(
            name='TaskRecurrenceRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=180)),
                ('frequency', models.CharField(choices=[('daily', 'Diária'), ('weekly', 'Semanal'), ('monthly', 'Mensal')], max_length=20)),
                ('interval', models.PositiveIntegerField(default=1)),
                ('active', models.BooleanField(default=True)),
                ('last_run_at', models.DateTimeField(blank=True, null=True)),
                ('next_run_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('source_task', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='recurrence_rules', to='crm.taskdemand')),
            ],
            options={'db_table': 'task_recurrence_rules', 'ordering': ['-created_at']},
        ),
    ]
