from django.contrib import admin
from .models import UserTeam, UserTeamPlayer, Contest, ContestEntry


class UserTeamPlayerInline(admin.TabularInline):
    model = UserTeamPlayer
    extra = 0
    readonly_fields = ['player', 'multiplier', 'raw_points', 'final_points']
    fields = ['player', 'multiplier', 'raw_points', 'final_points']

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(UserTeam)
class UserTeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'user', 'match', 'captain', 'total_points', 'is_locked', 'created_at']
    list_filter = ['is_locked', 'match']
    search_fields = ['user__email', 'name']
    readonly_fields = ['user', 'match', 'total_points', 'created_at']
    inlines = [UserTeamPlayerInline]


@admin.register(Contest)
class ContestAdmin(admin.ModelAdmin):
    list_display = ['name', 'match', 'contest_type', 'entry_fee_inr', 'current_entries', 'max_entries', 'status']
    list_filter = ['status', 'contest_type']
    search_fields = ['name']

    def entry_fee_inr(self, obj):
        return f"₹{obj.entry_fee / 100:.0f}" if obj.entry_fee else "Free"
    entry_fee_inr.short_description = 'Entry fee'


@admin.register(ContestEntry)
class ContestEntryAdmin(admin.ModelAdmin):
    list_display = ['user', 'contest', 'team', 'rank', 'prize_won_inr', 'joined_at']
    list_filter = ['contest__match']
    search_fields = ['user__email']
    readonly_fields = ['user', 'contest', 'team', 'entry_fee_paid', 'prize_won']

    def prize_won_inr(self, obj):
        return f"₹{obj.prize_won / 100:.2f}"
    prize_won_inr.short_description = 'Prize won'