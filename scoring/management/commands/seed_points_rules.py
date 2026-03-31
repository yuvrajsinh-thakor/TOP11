from django.core.management.base import BaseCommand
from scoring.models import PointsRule

class Command(BaseCommand):
    help = 'Seed default cricket points rules'

    def handle(self, *args, **options):
        rules = [
            # Batting
            {'event_name': 'Run scored',        'event_code': 'RUN',           'points': 1},
            {'event_name': 'Boundary (4)',       'event_code': 'BOUNDARY',      'points': 1},
            {'event_name': 'Six',               'event_code': 'SIX',           'points': 2},
            {'event_name': 'Duck (T20/ODI)',     'event_code': 'DUCK',          'points': -2},
            {'event_name': '30-run milestone',   'event_code': 'MILESTONE_30',  'points': 4},
            {'event_name': '50-run milestone',   'event_code': 'MILESTONE_50',  'points': 8},
            {'event_name': '100-run milestone',  'event_code': 'MILESTONE_100', 'points': 16},
            # Bowling
            {'event_name': 'Wicket taken',      'event_code': 'WICKET',        'points': 25},
            {'event_name': 'Maiden over',       'event_code': 'MAIDEN',        'points': 12},
            {'event_name': '3-wicket bonus',    'event_code': 'BONUS_3W',      'points': 4},
            {'event_name': '5-wicket bonus',    'event_code': 'BONUS_5W',      'points': 8},
            # Fielding
            {'event_name': 'Catch',             'event_code': 'CATCH',         'points': 8},
            {'event_name': 'Stumping',          'event_code': 'STUMPING',      'points': 12},
            {'event_name': 'Run out (direct)',  'event_code': 'RUNOUT_DIRECT', 'points': 12},
            {'event_name': 'Run out (indirect)','event_code': 'RUNOUT_THROW',  'points': 6},
        ]

        created = 0
        for rule in rules:
            obj, was_created = PointsRule.objects.get_or_create(
                event_code=rule['event_code'],
                defaults={
                    'event_name': rule['event_name'],
                    'points': rule['points'],
                    'sport': 'cricket',
                    'format': 'ALL',
                }
            )
            if was_created:
                created += 1

        self.stdout.write(self.style.SUCCESS(f'Seeded {created} points rules.'))