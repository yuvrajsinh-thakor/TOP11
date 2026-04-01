from rest_framework import serializers
from .models import CricketTeam, Player, Match, Squad


class CricketTeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = CricketTeam
        fields = ['id', 'name', 'short_name', 'logo', 'country']


class PlayerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Player
        fields = [
            'id', 'name', 'country', 'role',
            'batting_style', 'bowling_style', 'photo',
        ]


class SquadPlayerSerializer(serializers.ModelSerializer):
    """Player info + their fantasy credit for a specific match"""
    player = PlayerSerializer(read_only=True)
    team = CricketTeamSerializer(read_only=True)

    class Meta:
        model = Squad
        fields = [
            'id', 'player', 'team',
            'fantasy_credit', 'is_playing_xi', 'is_announced',
        ]


class MatchListSerializer(serializers.ModelSerializer):
    """Compact match info for list views"""
    team_a = CricketTeamSerializer(read_only=True)
    team_b = CricketTeamSerializer(read_only=True)
    time_until_match = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = [
            'id', 'team_a', 'team_b', 'format',
            'status', 'venue', 'series_name',
            'scheduled_at', 'time_until_match',
        ]

    def get_time_until_match(self, obj):
        from django.utils import timezone
        now = timezone.now()
        if obj.scheduled_at > now:
            diff = obj.scheduled_at - now
            hours = int(diff.total_seconds() // 3600)
            minutes = int((diff.total_seconds() % 3600) // 60)
            if hours > 24:
                days = hours // 24
                return f"{days}d {hours % 24}h"
            return f"{hours}h {minutes}m"
        return None


class MatchDetailSerializer(serializers.ModelSerializer):
    """Full match info including squads"""
    team_a = CricketTeamSerializer(read_only=True)
    team_b = CricketTeamSerializer(read_only=True)
    winner = CricketTeamSerializer(read_only=True)
    squads = serializers.SerializerMethodField()
    contest_count = serializers.SerializerMethodField()

    class Meta:
        model = Match
        fields = [
            'id', 'team_a', 'team_b', 'format',
            'status', 'venue', 'series_name',
            'scheduled_at', 'squads_locked_at',
            'winner', 'result_summary',
            'squads', 'contest_count',
        ]

    def get_squads(self, obj):
        squads = Squad.objects.filter(match=obj).select_related('player', 'team')
        return SquadPlayerSerializer(squads, many=True).data

    def get_contest_count(self, obj):
        return obj.contests.filter(status='upcoming').count()