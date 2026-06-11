import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0007_userprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='movie',
            name='kind',
            field=models.CharField(
                choices=[('movie', 'Movie'), ('series', 'Series')],
                db_index=True, default='movie', max_length=10),
        ),
        migrations.AddField(
            model_name='movie',
            name='end_year',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='Episode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('imdb_id', models.CharField(max_length=20, unique=True)),
                ('title', models.CharField(max_length=255)),
                ('season_number', models.IntegerField(blank=True, null=True)),
                ('episode_number', models.IntegerField(blank=True, null=True)),
                ('release_year', models.IntegerField(blank=True, null=True)),
                ('duration', models.IntegerField(blank=True, null=True)),
                ('rating', models.FloatField(blank=True, null=True)),
                ('num_votes', models.IntegerField(blank=True, null=True)),
                ('poster_url', models.URLField(blank=True, max_length=500, null=True)),
                ('plot_summary', models.TextField(blank=True, null=True)),
                ('is_seen', models.BooleanField(default=False)),
                ('series', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='episodes', to='app.movie')),
            ],
            options={
                'ordering': ['season_number', 'episode_number'],
            },
        ),
        migrations.AddIndex(
            model_name='episode',
            index=models.Index(fields=['series', 'season_number', 'episode_number'], name='app_episode_series__255477_idx'),
        ),
    ]
