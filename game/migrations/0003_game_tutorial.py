from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('game', '0002_seat_bots'),
    ]

    operations = [
        migrations.AddField(
            model_name='game',
            name='tutorial',
            field=models.BooleanField(default=False),
        ),
    ]
