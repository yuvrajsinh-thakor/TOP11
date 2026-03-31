from django.db import models
import uuid


class PointsRule(models.Model):
    """Admin-configurable scoring rules (like Dream11's scoring system)"""

    SPORT_CHOICES = [
        ('cricket', 'Cricket'),
    ]

    FORMAT_CHOICES = [
        ('T20', 'T20'),
        ('ODI', 'ODI'),
        ('TEST', 'Test'),
        ('ALL', 'All Formats'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sport = models.CharField(max_length=20, choices=SPORT_CHOICES, default='cricket')
    format = models.CharField(max_length=5, choices=FORMAT_CHOICES, default='ALL')
    event_name = models.CharField(max_length=100)           # e.g. "run", "wicket", "catch"
    event_code = models.CharField(max_length=50, unique=True)  # e.g. "RUN", "WICKET", "CATCH"
    points = models.DecimalField(max_digits=6, decimal_places=2)  # Can be negative (duck = -2)
    description = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'points_rules'

    def __str__(self):
        return f"{self.event_name}: {'+' if self.points >= 0 else ''}{self.points} pts"


class PlayerMatchScore(models.Model):
    """Live/final fantasy points for a real player in a specific match"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    player = models.ForeignKey('matches.Player', on_delete=models.CASCADE, related_name='match_scores')
    match = models.ForeignKey('matches.Match', on_delete=models.CASCADE, related_name='player_scores')

    # Actual in-game stats
    runs_scored = models.IntegerField(default=0)
    balls_faced = models.IntegerField(default=0)
    fours = models.IntegerField(default=0)
    sixes = models.IntegerField(default=0)
    is_out = models.BooleanField(default=False)
    wickets_taken = models.IntegerField(default=0)
    runs_conceded = models.IntegerField(default=0)
    overs_bowled = models.DecimalField(max_digits=4, decimal_places=1, default=0)
    maiden_overs = models.IntegerField(default=0)
    catches = models.IntegerField(default=0)
    stumpings = models.IntegerField(default=0)
    run_outs_direct = models.IntegerField(default=0)
    run_outs_indirect = models.IntegerField(default=0)

    # Computed fantasy points
    total_fantasy_points = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    points_breakdown = models.JSONField(default=dict)       # {"RUN": 45, "WICKET": 50, ...}

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'player_match_scores'
        unique_together = ('player', 'match')

    def __str__(self):
        return f"{self.player.name} in {self.match} — {self.total_fantasy_points} pts"


class Leaderboard(models.Model):
    """Contest leaderboard — rank of each entry in each contest"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    contest = models.ForeignKey('contests.Contest', on_delete=models.CASCADE, related_name='leaderboard')
    contest_entry = models.ForeignKey('contests.ContestEntry', on_delete=models.CASCADE)
    user = models.ForeignKey('accounts.User', on_delete=models.CASCADE)
    team = models.ForeignKey('contests.UserTeam', on_delete=models.CASCADE)

    rank = models.IntegerField(db_index=True)
    total_points = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    prize_amount = models.BigIntegerField(default=0)        # In paise

    last_updated = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'leaderboard'
        ordering = ['rank']
        unique_together = ('contest', 'contest_entry')

    def __str__(self):
        return f"Rank {self.rank} — {self.user.email} — {self.contest.name}"


class AuditLog(models.Model):
    """Every admin action recorded for security"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    admin_user = models.ForeignKey('accounts.User', on_delete=models.CASCADE, related_name='audit_logs')
    action = models.CharField(max_length=200)
    model_name = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=100, blank=True)
    old_value = models.JSONField(null=True, blank=True)
    new_value = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'audit_logs'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.admin_user.email} — {self.action}"