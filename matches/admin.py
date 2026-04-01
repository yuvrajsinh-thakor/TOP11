from django.contrib import admin
from django.utils.html import format_html
from .models import CricketTeam, Player, Match, Squad


@admin.register(CricketTeam)
class CricketTeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'country']
    search_fields = ['name', 'short_name']


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ['name', 'role', 'country', 'is_active']
    list_filter = ['role', 'country', 'is_active']
    search_fields = ['name']
    list_editable = ['is_active']


class SquadInline(admin.TabularInline):
    """
    Show all squad players directly inside the Match admin page.
    Admin can add/edit players and their credits right there.
    """
    model = Squad
    extra = 5
    fields = ['player', 'team', 'fantasy_credit', 'is_playing_xi', 'is_announced']
    autocomplete_fields = ['player']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('player', 'team')


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = [
        'match_name', 'format', 'status',
        'scheduled_at', 'squads_locked_at', 'player_count'
    ]
    list_filter = ['status', 'format']
    search_fields = ['team_a__name', 'team_b__name', 'series_name']
    list_editable = ['status']
    inlines = [SquadInline]
    autocomplete_fields = ['team_a', 'team_b', 'winner']

    readonly_fields = ['created_at', 'updated_at']

    fieldsets = (
        ('Match Info', {
            'fields': ('team_a', 'team_b', 'format', 'series_name', 'venue')
        }),
        ('Schedule', {
            'fields': ('scheduled_at', 'squads_locked_at', 'status')
        }),
        ('Result', {
            'fields': ('winner', 'result_summary'),
            'classes': ('collapse',),
        }),
        ('External API', {
            'fields': ('cricapi_match_id',),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def match_name(self, obj):
        return f"{obj.team_a.short_name} vs {obj.team_b.short_name}"
    match_name.short_description = 'Match'

    def player_count(self, obj):
        count = obj.squads.count()
        color = 'green' if count >= 22 else 'orange' if count > 0 else 'red'
        return format_html(
            '<span style="color: {}; font-weight: bold;">{} players</span>',
            color, count
        )
    player_count.short_description = 'Squad size'


@admin.register(Squad)
class SquadAdmin(admin.ModelAdmin):
    list_display = ['player', 'match', 'team', 'fantasy_credit', 'is_playing_xi']
    list_filter = ['match', 'team', 'is_playing_xi']
    search_fields = ['player__name']
    list_editable = ['fantasy_credit', 'is_playing_xi']
    autocomplete_fields = ['player', 'match', 'team']