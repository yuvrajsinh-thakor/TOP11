from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import CricketTeam, Player, Match, Squad
from top11_project.admin_helpers import log_admin_action, get_client_ip


@admin.register(CricketTeam)
class CricketTeamAdmin(admin.ModelAdmin):
    list_display = ['name', 'short_name', 'country', 'logo_preview']
    search_fields = ['name', 'short_name']

    def logo_preview(self, obj):
        if obj.logo:
            return format_html(
                '<img src="{}" style="height:30px;border-radius:4px;">',
                obj.logo.url
            )
        return '—'
    logo_preview.short_description = 'Logo'


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ['name', 'role_badge', 'country', 'batting_style', 'is_active']
    list_filter = ['role', 'country', 'is_active']
    search_fields = ['name']
    list_editable = ['is_active']

    def role_badge(self, obj):
        colors = {
            'BAT': '#185FA5', 'BOW': '#993C1D',
            'AR': '#0F6E56', 'WK': '#854F0B'
        }
        color = colors.get(obj.role, '#888')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;">{}</span>',
            color, obj.role
        )
    role_badge.short_description = 'Role'


class SquadInline(admin.TabularInline):
    model = Squad
    extra = 3
    fields = ['player', 'team', 'fantasy_credit', 'is_playing_xi', 'is_announced']
    autocomplete_fields = ['player']

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('player', 'team')


@admin.register(Match)
class MatchAdmin(admin.ModelAdmin):
    list_display = [
        'match_display', 'format', 'status_badge',
        'scheduled_at', 'player_count', 'contest_count', 'is_locked'
    ]
    list_filter = ['status', 'format']
    search_fields = ['team_a__name', 'team_b__name', 'series_name']
    list_editable = []
    inlines = [SquadInline]
    autocomplete_fields = ['team_a', 'team_b', 'winner']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['lock_squads', 'mark_live', 'mark_completed']

    fieldsets = (
        ('Match', {'fields': ('team_a', 'team_b', 'format', 'series_name', 'venue')}),
        ('Schedule', {'fields': ('scheduled_at', 'squads_locked_at', 'status')}),
        ('Result', {'fields': ('winner', 'result_summary'), 'classes': ('collapse',)}),
        ('CricAPI', {'fields': ('cricapi_match_id',), 'classes': ('collapse',)}),
        ('Timestamps', {'fields': ('created_at', 'updated_at'), 'classes': ('collapse',)}),
    )

    def match_display(self, obj):
        return f"{obj.team_a.short_name} vs {obj.team_b.short_name}"
    match_display.short_description = 'Match'

    def status_badge(self, obj):
        colors = {
            'upcoming': '#185FA5', 'live': '#1D9E75',
            'completed': '#888780', 'cancelled': '#E24B4A'
        }
        color = colors.get(obj.status, '#888')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 8px;'
            'border-radius:4px;font-size:11px;">{}</span>',
            color, obj.status.upper()
        )
    status_badge.short_description = 'Status'

    def player_count(self, obj):
        count = obj.squads.count()
        color = 'green' if count >= 22 else 'orange' if count > 0 else 'red'
        return format_html(
            '<span style="color:{};">{}</span>', color, count
        )
    player_count.short_description = 'Players'

    def contest_count(self, obj):
        return obj.contests.count()
    contest_count.short_description = 'Contests'

    def is_locked(self, obj):
        if obj.squads_locked_at and timezone.now() > obj.squads_locked_at:
            return format_html('<span style="color:red;">Locked</span>')
        return format_html('<span style="color:green;">Open</span>')
    is_locked.short_description = 'Squad'

    def lock_squads(self, request, queryset):
        count = 0
        for match in queryset.filter(squads_locked_at__isnull=True):
            match.squads_locked_at = timezone.now()
            match.save()
            log_admin_action(
                request.user, f'Squad locked for {match}',
                'Match', match.id, ip_address=get_client_ip(request)
            )
            count += 1
        self.message_user(request, f'{count} match squads locked.')
    lock_squads.short_description = 'Lock squads for selected matches'

    def mark_live(self, request, queryset):
        count = queryset.filter(status='upcoming').update(status='live')
        self.message_user(request, f'{count} matches marked as live.')
    mark_live.short_description = 'Mark selected matches as LIVE'

    def mark_completed(self, request, queryset):
        count = queryset.filter(status='live').update(status='completed')
        self.message_user(request, f'{count} matches marked as completed.')
    mark_completed.short_description = 'Mark selected matches as COMPLETED'


@admin.register(Squad)
class SquadAdmin(admin.ModelAdmin):
    list_display = ['player', 'match', 'team', 'fantasy_credit', 'is_playing_xi', 'is_announced']
    list_filter = ['match', 'team', 'is_playing_xi']
    search_fields = ['player__name']
    list_editable = ['fantasy_credit', 'is_playing_xi', 'is_announced']
    autocomplete_fields = ['player', 'match', 'team']