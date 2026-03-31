from django.db import models
import uuid


class Player(models.Model):
    """Real-world cricket player"""

    ROLE_CHOICES = [
        ('BAT', 'Batsman'),
        ('BOW', 'Bowler'),
        ('AR', 'All-rounder'),
        ('WK', 'Wicketkeeper'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=150)
    country = models.CharField(max_length=100, blank=True)
    role = models.CharField(max_length=5, choices=ROLE_CHOICES)
    batting_style = models.CharField(max_length=50, blank=True)
    bowling_style = models.CharField(max_length=80, blank=True)
    photo = models.ImageField(upload_to='players/', blank=True, null=True)
    is_active = models.BooleanField(default=True)

    # External API ID (CricAPI player ID for matching live data)
    cricapi_id = models.CharField(max_length=100, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'players'

    def __str__(self):
        return f"{self.name} ({self.role})"


class CricketTeam(models.Model):
    """Real-world cricket team (India, Australia, CSK, MI, etc.)"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=100)
    short_name = models.CharField(max_length=10)           # e.g. IND, AUS, CSK
    logo = models.ImageField(upload_to='teams/', blank=True, null=True)
    country = models.CharField(max_length=100, blank=True)

    class Meta:
        db_table = 'cricket_teams'

    def __str__(self):
        return self.name


class Match(models.Model):
    """Upcoming / live / completed cricket match"""

    FORMAT_CHOICES = [
        ('T20', 'T20'),
        ('ODI', 'ODI'),
        ('TEST', 'Test'),
        ('T10', 'T10'),
    ]

    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('live', 'Live'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
        ('abandoned', 'Abandoned'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    team_a = models.ForeignKey(CricketTeam, on_delete=models.CASCADE, related_name='home_matches')
    team_b = models.ForeignKey(CricketTeam, on_delete=models.CASCADE, related_name='away_matches')
    format = models.CharField(max_length=5, choices=FORMAT_CHOICES, default='T20')
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='upcoming')
    venue = models.CharField(max_length=200, blank=True)
    series_name = models.CharField(max_length=200, blank=True)
    scheduled_at = models.DateTimeField()
    squads_locked_at = models.DateTimeField(null=True, blank=True)  # No team changes after this

    # CricAPI match ID for pulling live data
    cricapi_match_id = models.CharField(max_length=100, blank=True, db_index=True)

    # Result
    winner = models.ForeignKey(
        CricketTeam, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='wins'
    )
    result_summary = models.CharField(max_length=300, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'matches'
        ordering = ['scheduled_at']

    def __str__(self):
        return f"{self.team_a.short_name} vs {self.team_b.short_name} — {self.scheduled_at.date()}"


class Squad(models.Model):
    """Which players are in a match squad + their fantasy credit value"""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    match = models.ForeignKey(Match, on_delete=models.CASCADE, related_name='squads')
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name='squads')
    team = models.ForeignKey(CricketTeam, on_delete=models.CASCADE)

    # Fantasy credit (e.g. 7.5, 8.0, 9.5 — stored as float)
    fantasy_credit = models.DecimalField(max_digits=4, decimal_places=1, default=8.0)

    is_playing_xi = models.BooleanField(default=False)      # Set after toss
    is_announced = models.BooleanField(default=False)       # Playing XI announced

    class Meta:
        db_table = 'squads'
        unique_together = ('match', 'player')               # Player only once per match

    def __str__(self):
        return f"{self.player.name} in {self.match}"