from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('crm', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='taskdemand',
            name='position',
            field=models.PositiveIntegerField(default=0),
        ),
    ]
