"""Campaign funnel report: clicks -> signups -> enrollments -> certificates.

The admin list views can browse the raw rows, but the funnel needs joins across
apps, so it lives here. Read-only.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db.models import Count
from django.utils import timezone

from learning.models import Certificate, Enrollment
from users.models import CampaignHit, UserAcquisition


class Command(BaseCommand):
    help = "Per-campaign funnel: hits, signups, enrolled users, certificates."

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=30,
            help='Window in days (default: 30). Use 0 for all time.',
        )

    def handle(self, *args, **options):
        days = options['days']
        since = timezone.now() - timedelta(days=days) if days else None

        hits = CampaignHit.objects.all()
        acquisitions = UserAcquisition.objects.all()
        if since:
            hits = hits.filter(created_at__gte=since)
            acquisitions = acquisitions.filter(created_at__gte=since)

        # A campaign is the (source, medium, campaign) triple — content/term are
        # variant labels and would fragment the report.
        def tally(queryset):
            return {
                (row['source'], row['medium'], row['campaign']): row['n']
                for row in queryset.values('source', 'medium', 'campaign')
                                   .annotate(n=Count('id')).order_by()
            }

        hit_counts = tally(hits)
        signup_counts = tally(acquisitions)

        # Users who did something after signing up, grouped by their origin.
        enrolled_users = set(
            Enrollment.objects.values_list('user_id', flat=True).distinct()
        )
        certified_users = set(
            Certificate.objects.values_list('user_id', flat=True).distinct()
        )
        enrolled_counts, certified_counts = {}, {}
        for source, medium, campaign, user_id in acquisitions.values_list(
            'source', 'medium', 'campaign', 'user_id',
        ):
            key = (source, medium, campaign)
            if user_id in enrolled_users:
                enrolled_counts[key] = enrolled_counts.get(key, 0) + 1
            if user_id in certified_users:
                certified_counts[key] = certified_counts.get(key, 0) + 1

        keys = sorted(
            set(hit_counts) | set(signup_counts),
            key=lambda k: (-signup_counts.get(k, 0), -hit_counts.get(k, 0), k),
        )
        if not keys:
            window = 'all time' if not since else f'the last {days} day(s)'
            self.stdout.write(f'No campaign data for {window}.')
            return

        header = f'{"source":<18}{"medium":<14}{"campaign":<22}{"hits":>7}{"signup":>8}{"enrol":>7}{"cert":>6}{"conv":>8}'
        self.stdout.write(self.style.MIGRATE_HEADING(header))
        self.stdout.write('-' * len(header))
        for key in keys:
            source, medium, campaign = key
            hit_n = hit_counts.get(key, 0)
            signup_n = signup_counts.get(key, 0)
            # Signup rate is only meaningful where we counted the clicks too;
            # organic/direct rows have signups but no hits by design.
            conversion = f'{signup_n / hit_n:.0%}' if hit_n else '—'
            self.stdout.write(
                f'{source[:17]:<18}{medium[:13]:<14}{(campaign or "—")[:21]:<22}'
                f'{hit_n:>7}{signup_n:>8}{enrolled_counts.get(key, 0):>7}'
                f'{certified_counts.get(key, 0):>6}{conversion:>8}'
            )
        self.stdout.write('-' * len(header))
        self.stdout.write(
            f'{sum(hit_counts.values())} hit(s), {sum(signup_counts.values())} signup(s) '
            f'over {"all time" if not since else f"{days} day(s)"}.'
        )
