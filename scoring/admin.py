from django.contrib import admin
from .models import PointsRule, PlayerMatchScore, Leaderboard, AuditLog


@admin.register(PointsRule)
class PointsRuleAdmin(admin.ModelAdmin):
    list_display = ['event_name', 'event_code', 'points', 'format', 'is_active']
    list_editable = ['points', 'is_active']
    list_filter = ['sport', 'format', 'is_active']
    search_fields = ['event_name', 'event_code']


@admin.register(PlayerMatchScore)
class PlayerMatchScoreAdmin(admin.ModelAdmin):
    list_display = [
        'player', 'match', 'runs_scored', 'wickets_taken',
        'catches', 'total_fantasy_points'
    ]
    list_filter = ['match']
    search_fields = ['player__name']
    readonly_fields = ['points_breakdown']


@admin.register(Leaderboard)
class LeaderboardAdmin(admin.ModelAdmin):
    list_display = ['rank', 'user', 'team', 'contest', 'total_points', 'prize_amount_inr']
    list_filter = ['contest']
    ordering = ['contest', 'rank']

    def prize_amount_inr(self, obj):
        return f"₹{obj.prize_amount / 100:.2f}"
    prize_amount_inr.short_description = 'Prize'


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ['admin_user', 'action', 'model_name', 'created_at']
    readonly_fields = ['admin_user', 'action', 'old_value', 'new_value', 'ip_address', 'created_at']
    list_filter = ['model_name']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False