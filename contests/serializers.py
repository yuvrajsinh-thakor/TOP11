from rest_framework import serializers
from django.conf import settings
from .models import UserTeam, UserTeamPlayer, ContestEntry
from matches.models import Squad, Player, Match


class CreateTeamSerializer(serializers.Serializer):
    """
    Validates and creates a user fantasy team.
    Expects 11 player IDs from the match squad.
    """
    match_id = serializers.UUIDField()
    name = serializers.CharField(max_length=100, default='My Team')
    player_ids = serializers.ListField(
        child=serializers.UUIDField(),
        min_length=11,
        max_length=11
    )
    captain_id = serializers.UUIDField()
    vice_captain_id = serializers.UUIDField()

    def validate(self, data):
        user = self.context['request'].user
        match_id = data['match_id']
        player_ids = data['player_ids']
        captain_id = data['captain_id']
        vice_captain_id = data['vice_captain_id']

        # --- Rule 0: Match must exist and be upcoming ---
        try:
            match = Match.objects.get(id=match_id)
        except Match.DoesNotExist:
            raise serializers.ValidationError({'match_id': 'Match not found.'})

        if match.status != 'upcoming':
            raise serializers.ValidationError(
                {'match_id': 'You can only create teams for upcoming matches.'}
            )

        # Check squad not locked
        from django.utils import timezone
        if match.squads_locked_at and timezone.now() > match.squads_locked_at:
            raise serializers.ValidationError(
                {'match_id': 'Squad is locked. Team creation is closed.'}
            )

        # --- Rule 1: All 11 players must be in this match squad ---
        squad_entries = Squad.objects.filter(
            match=match,
            player_id__in=player_ids
        ).select_related('player', 'team')

        if squad_entries.count() != 11:
            raise serializers.ValidationError(
                {'player_ids': 'One or more players are not in this match squad.'}
            )

        # --- Rule 2: No duplicate players ---
        if len(set(str(pid) for pid in player_ids)) != 11:
            raise serializers.ValidationError(
                {'player_ids': 'Duplicate players found. Each player can only be selected once.'}
            )

        # --- Rule 3: Budget check (max 100 credits) ---
        total_credits = sum(float(s.fantasy_credit) for s in squad_entries)
        if total_credits > settings.TOP11_TEAM_BUDGET:
            raise serializers.ValidationError(
                {'player_ids': f'Team exceeds budget. Total: {total_credits:.1f}, Max: {settings.TOP11_TEAM_BUDGET}'}
            )

        # --- Rule 4: Role constraints ---
        role_counts = {}
        for sq in squad_entries:
            role = sq.player.role
            role_counts[role] = role_counts.get(role, 0) + 1

        wk_count  = role_counts.get('WK', 0)
        bat_count = role_counts.get('BAT', 0)
        bow_count = role_counts.get('BOW', 0)
        ar_count  = role_counts.get('AR', 0)

        errors = []
        if not (1 <= wk_count <= 1):
            errors.append(f'Need exactly 1 Wicketkeeper (you have {wk_count}).')
        if not (3 <= bat_count <= 6):
            errors.append(f'Need 3-6 Batsmen (you have {bat_count}).')
        if not (3 <= bow_count <= 6):
            errors.append(f'Need 3-6 Bowlers (you have {bow_count}).')
        if not (1 <= ar_count <= 4):
            errors.append(f'Need 1-4 All-rounders (you have {ar_count}).')

        if errors:
            raise serializers.ValidationError({'player_ids': errors})

        # --- Rule 5: Max 7 players from one team ---
        team_counts = {}
        for sq in squad_entries:
            tid = str(sq.team_id)
            team_counts[tid] = team_counts.get(tid, 0) + 1

        for tid, count in team_counts.items():
            if count > 7:
                raise serializers.ValidationError(
                    {'player_ids': f'Maximum 7 players allowed from one team. You have {count}.'}
                )

        # --- Rule 6: Captain and VC must be in the 11 ---
        player_id_strs = [str(pid) for pid in player_ids]
        if str(captain_id) not in player_id_strs:
            raise serializers.ValidationError(
                {'captain_id': 'Captain must be one of your selected 11 players.'}
            )
        if str(vice_captain_id) not in player_id_strs:
            raise serializers.ValidationError(
                {'vice_captain_id': 'Vice-captain must be one of your selected 11 players.'}
            )
        if str(captain_id) == str(vice_captain_id):
            raise serializers.ValidationError(
                {'vice_captain_id': 'Captain and Vice-captain must be different players.'}
            )

        # --- Rule 7: Max 6 teams per user per match ---
        # --- Rule 7: Max 6 teams per user per match ---
        existing_teams = UserTeam.objects.filter(user=user, match=match).count()
        max_teams = getattr(settings, 'TOP11_MAX_TEAMS_PER_USER', 6)
        if existing_teams >= max_teams:
            raise serializers.ValidationError(
                {'match_id': 'You can create maximum 6 teams per match.'}
            )

        # Attach resolved objects for use in the view
        data['match'] = match
        data['squad_entries'] = squad_entries
        data['total_credits'] = total_credits
        return data


class UserTeamPlayerSerializer(serializers.ModelSerializer):
    player_name = serializers.CharField(source='player.name', read_only=True)
    player_role = serializers.CharField(source='player.role', read_only=True)

    class Meta:
        model = UserTeamPlayer
        fields = [
            'player_id', 'player_name', 'player_role',
            'multiplier', 'raw_points', 'final_points',
        ]


class UserTeamSerializer(serializers.ModelSerializer):
    players = UserTeamPlayerSerializer(source='team_players', many=True, read_only=True)
    captain_name = serializers.CharField(source='captain.name', read_only=True)
    vice_captain_name = serializers.CharField(source='vice_captain.name', read_only=True)
    match_name = serializers.SerializerMethodField()

    class Meta:
        model = UserTeam
        fields = [
            'id', 'name', 'match_name',
            'captain_id', 'captain_name',
            'vice_captain_id', 'vice_captain_name',
            'total_points', 'is_locked',
            'players', 'created_at',
        ]

    def get_match_name(self, obj):
        return f"{obj.match.team_a.short_name} vs {obj.match.team_b.short_name}"


class UserTeamListSerializer(serializers.ModelSerializer):
    """Compact version for listing teams"""
    captain_name = serializers.CharField(source='captain.name', read_only=True)
    vice_captain_name = serializers.CharField(source='vice_captain.name', read_only=True)

    class Meta:
        model = UserTeam
        fields = [
            'id', 'name',
            'captain_name', 'vice_captain_name',
            'total_points', 'is_locked', 'created_at',
        ]





from .models import Contest, ContestEntry


class PrizeDistributionSerializer(serializers.Serializer):
    rank_from = serializers.IntegerField(min_value=1)
    rank_to = serializers.IntegerField(min_value=1)
    prize = serializers.IntegerField(min_value=0)  # in paise


class ContestListSerializer(serializers.ModelSerializer):
    """Compact contest info for listing"""
    entry_fee_inr = serializers.SerializerMethodField()
    prize_pool_inr = serializers.SerializerMethodField()
    spots_left = serializers.SerializerMethodField()
    is_full = serializers.SerializerMethodField()
    match_name = serializers.SerializerMethodField()

    class Meta:
        model = Contest
        fields = [
            'id', 'name', 'contest_type', 'status',
            'entry_fee_inr', 'prize_pool_inr',
            'max_entries', 'current_entries',
            'spots_left', 'is_full',
            'max_teams_per_user', 'match_name',
        ]

    def get_entry_fee_inr(self, obj):
        return round(obj.entry_fee / 100, 2)

    def get_prize_pool_inr(self, obj):
        return round(obj.total_prize_pool / 100, 2)

    def get_spots_left(self, obj):
        return max(0, obj.max_entries - obj.current_entries)

    def get_is_full(self, obj):
        return obj.current_entries >= obj.max_entries

    def get_match_name(self, obj):
        return f"{obj.match.team_a.short_name} vs {obj.match.team_b.short_name}"


class ContestDetailSerializer(serializers.ModelSerializer):
    """Full contest detail including prize breakdown"""
    entry_fee_inr = serializers.SerializerMethodField()
    prize_pool_inr = serializers.SerializerMethodField()
    spots_left = serializers.SerializerMethodField()
    match_name = serializers.SerializerMethodField()
    prize_distribution_inr = serializers.SerializerMethodField()
    user_entries = serializers.SerializerMethodField()

    class Meta:
        model = Contest
        fields = [
            'id', 'name', 'contest_type', 'status',
            'entry_fee_inr', 'prize_pool_inr',
            'max_entries', 'current_entries', 'min_entries',
            'spots_left', 'max_teams_per_user',
            'match_name', 'prize_distribution_inr',
            'user_entries',
        ]

    def get_entry_fee_inr(self, obj):
        return round(obj.entry_fee / 100, 2)

    def get_prize_pool_inr(self, obj):
        return round(obj.total_prize_pool / 100, 2)

    def get_spots_left(self, obj):
        return max(0, obj.max_entries - obj.current_entries)

    def get_match_name(self, obj):
        return f"{obj.match.team_a.short_name} vs {obj.match.team_b.short_name}"

    def get_prize_distribution_inr(self, obj):
        """Convert paise to INR in prize distribution"""
        result = []
        for tier in obj.prize_distribution:
            result.append({
                'rank_from': tier['rank_from'],
                'rank_to': tier['rank_to'],
                'prize_inr': round(tier['prize'] / 100, 2),
            })
        return result

    def get_user_entries(self, obj):
        """How many teams this user entered in this contest"""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        return obj.entries.filter(user=request.user).count()


class JoinContestSerializer(serializers.Serializer):
    """Validate joining a contest"""
    team_id = serializers.UUIDField()

    def validate(self, data):
        request = self.context['request']
        contest = self.context['contest']
        user = request.user
        team_id = data['team_id']

        # Contest must be upcoming
        if contest.status != 'upcoming':
            raise serializers.ValidationError(
                {'contest': 'This contest is not open for entries.'}
            )

        # Contest must not be full
        if contest.is_full():
            raise serializers.ValidationError(
                {'contest': 'This contest is full.'}
            )

        # Team must belong to user and be for this match
        from .models import UserTeam
        try:
            team = UserTeam.objects.get(
                id=team_id,
                user=user,
                match=contest.match
            )
        except UserTeam.DoesNotExist:
            raise serializers.ValidationError(
                {'team_id': 'Team not found or does not belong to this match.'}
            )

        # Team must not be locked (it will be locked at match start)
        # Check same team not already in this contest
        if ContestEntry.objects.filter(
            contest=contest,
            team=team
        ).exists():
            raise serializers.ValidationError(
                {'team_id': 'This team is already entered in this contest.'}
            )

        # Check max teams per user per contest
        user_entries_count = ContestEntry.objects.filter(
            contest=contest,
            user=user
        ).count()
        if user_entries_count >= contest.max_teams_per_user:
            raise serializers.ValidationError(
                {'team_id': f'You can enter maximum {contest.max_teams_per_user} teams in this contest.'}
            )

        # Check user has enough wallet balance for paid contests
        if contest.entry_fee > 0:
            try:
                wallet = user.wallet
            except Exception:
                raise serializers.ValidationError(
                    {'wallet': 'Wallet not found. Please contact support.'}
                )

            total_balance = wallet.deposit_balance + wallet.winnings_balance + wallet.bonus_balance
            if total_balance < contest.entry_fee:
                raise serializers.ValidationError(
                    {'wallet': f'Insufficient balance. Need ₹{contest.entry_fee/100:.2f}, '
                               f'you have ₹{total_balance/100:.2f}.'}
                )

        data['team'] = team
        data['contest'] = contest
        return data


class ContestEntrySerializer(serializers.ModelSerializer):
    """A user's entry in a contest"""
    contest_name = serializers.CharField(source='contest.name', read_only=True)
    team_name = serializers.CharField(source='team.name', read_only=True)
    prize_won_inr = serializers.SerializerMethodField()
    entry_fee_inr = serializers.SerializerMethodField()
    match_name = serializers.SerializerMethodField()

    class Meta:
        model = ContestEntry
        fields = [
            'id', 'contest_name', 'team_name',
            'match_name', 'rank',
            'entry_fee_inr', 'prize_won_inr',
            'is_winner', 'joined_at',
        ]

    def get_prize_won_inr(self, obj):
        return round(obj.prize_won / 100, 2)

    def get_entry_fee_inr(self, obj):
        return round(obj.entry_fee_paid / 100, 2)

    def get_match_name(self, obj):
        m = obj.contest.match
        return f"{m.team_a.short_name} vs {m.team_b.short_name}"