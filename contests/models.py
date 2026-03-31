from django.db import models
from django.conf import settings
import uuid


class Contest(models.Model):
    """A contest linked to a match — users enter with their teams"""

    TYPE_CHOICES = [
        ('h2h', 'Head to Head'),
        ('small', 'Small League'),
        ('mega', 'Mega Contest'),
        ('free', 'Free Contest'),
    ]

    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('live', 'Live'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey('matches.Match', on_delete=models.CASCADE, related_name='contests')
    name = models.CharField(max_length=200)
    contest_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='upcoming')

    # Financials (stored in paise)
    entry_fee = models.BigIntegerField(default=0)           # 0 = free
    total_prize_pool = models.BigIntegerField(default=0)    # Total prize in paise
    max_entries = models.IntegerField(default=100)
    min_entries = models.IntegerField(default=2)            # Min needed or contest cancels
    current_entries = models.IntegerField(default=0)

    # Prize distribution (stored as JSON)
    # Example: [{"rank_from": 1, "rank_to": 1, "prize": 50000},
    #           {"rank_from": 2, "rank_to": 2, "prize": 25000}, ...]
    prize_distribution = models.JSONField(default=list)

    max_teams_per_user = models.IntegerField(default=6)     # Max teams one user can enter

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True,
        on_delete=models.SET_NULL, related_name='created_contests'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'contests'

    def is_full(self):
        return self.current_entries >= self.max_entries

    def __str__(self):
        return f"{self.name} — {self.match}"


class UserTeam(models.Model):
    """A user's 11-player fantasy team for a specific match"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='teams')
    match = models.ForeignKey('matches.Match', on_delete=models.CASCADE, related_name='user_teams')
    name = models.CharField(max_length=100, default='My Team 1')

    captain = models.ForeignKey(
        'matches.Player', on_delete=models.CASCADE, related_name='captained_teams'
    )
    vice_captain = models.ForeignKey(
        'matches.Player', on_delete=models.CASCADE, related_name='vc_teams'
    )

    total_points = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    is_locked = models.BooleanField(default=False)          # Locked when match starts

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_teams'

    def __str__(self):
        return f"{self.user.email} — {self.name} ({self.match})"


class UserTeamPlayer(models.Model):
    """Individual player in a user's team (11 rows per team)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team = models.ForeignKey(UserTeam, on_delete=models.CASCADE, related_name='team_players')
    player = models.ForeignKey('matches.Player', on_delete=models.CASCADE)

    # Points earned by this player in this team
    raw_points = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    multiplier = models.DecimalField(max_digits=3, decimal_places=1, default=1.0)  # 2.0=C, 1.5=VC, 1.0=normal
    final_points = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)

    class Meta:
        db_table = 'user_team_players'
        unique_together = ('team', 'player')

    def __str__(self):
        return f"{self.player.name} in {self.team.name}"


class ContestEntry(models.Model):
    """A user entering a team into a contest (paying entry fee)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name='entries')
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='contest_entries')
    team = models.ForeignKey(UserTeam, on_delete=models.CASCADE, related_name='contest_entries')

    entry_fee_paid = models.BigIntegerField(default=0)      # In paise
    rank = models.IntegerField(null=True, blank=True)
    prize_won = models.BigIntegerField(default=0)           # In paise
    tds_deducted = models.BigIntegerField(default=0)        # In paise

    is_winner = models.BooleanField(default=False)
    prize_credited = models.BooleanField(default=False)     # Has prize been credited to wallet

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'contest_entries'
        unique_together = ('contest', 'team')               # Same team can't enter same contest twice

    def __str__(self):
        return f"{self.user.email} in {self.contest.name}"