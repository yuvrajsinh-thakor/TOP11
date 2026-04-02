from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils.html import format_html
from django.utils import timezone
from django.db.models import Sum
from .models import User, OTPVerification, Wallet
from top11_project.admin_helpers import log_admin_action, get_client_ip


class WalletInline(admin.StackedInline):
    model = Wallet
    readonly_fields = [
        'deposit_balance_inr', 'winnings_balance_inr',
        'bonus_balance_inr', 'total_balance_inr'
    ]
    fields = [
        'deposit_balance_inr', 'winnings_balance_inr',
        'bonus_balance_inr', 'total_balance_inr'
    ]
    can_delete = False
    verbose_name = 'Wallet Balance'

    def deposit_balance_inr(self, obj):
        return f"₹{obj.deposit_balance / 100:.2f}"
    deposit_balance_inr.short_description = 'Deposit balance'

    def winnings_balance_inr(self, obj):
        return f"₹{obj.winnings_balance / 100:.2f}"
    winnings_balance_inr.short_description = 'Winnings balance'

    def bonus_balance_inr(self, obj):
        return f"₹{obj.bonus_balance / 100:.2f}"
    bonus_balance_inr.short_description = 'Bonus balance'

    def total_balance_inr(self, obj):
        return f"₹{obj.total_balance / 100:.2f}"
    total_balance_inr.short_description = 'Total balance'


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = [
        'email', 'full_name', 'is_verified',
        'is_kyc_done', 'kyc_status_badge',
        'wallet_balance', 'is_active', 'created_at'
    ]
    list_filter = [
        'is_verified', 'is_kyc_done',
        'is_active', 'is_staff', 'role'
    ]
    search_fields = ['email', 'full_name', 'mobile', 'pan_number']
    ordering = ['-created_at']
    readonly_fields = [
        'id', 'created_at', 'updated_at',
        'last_login_ip', 'failed_login_attempts', 'lockout_until',
        'referral_code',
    ]
    inlines = [WalletInline]
    actions = ['approve_kyc', 'ban_users', 'unban_users', 'unlock_accounts']

    fieldsets = (
        ('Login', {'fields': ('id', 'email', 'password')}),
        ('Personal info', {'fields': ('full_name', 'mobile', 'avatar', 'role')}),
        ('Account status', {
            'fields': ('is_active', 'is_verified', 'is_kyc_done', 'is_staff', 'is_superuser')
        }),
        ('KYC details', {
            'fields': ('pan_number', 'pan_verified', 'bank_account_number',
                       'bank_ifsc', 'bank_name', 'upi_id'),
            'classes': ('collapse',),
        }),
        ('Security', {
            'fields': ('failed_login_attempts', 'lockout_until', 'last_login_ip', 'device_fingerprint'),
            'classes': ('collapse',),
        }),
        ('Referral', {
            'fields': ('referral_code', 'referred_by'),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('email', 'password1', 'password2', 'is_staff', 'is_superuser'),
        }),
    )

    filter_horizontal = ()
    list_filter = ['is_staff', 'is_verified', 'is_kyc_done', 'is_active']

    def kyc_status_badge(self, obj):
        if obj.is_kyc_done:
            return format_html(
                '<span style="background:#1D9E75;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;">Verified</span>'
            )
        return format_html(
            '<span style="background:#E24B4A;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;">Pending</span>'
        )
    kyc_status_badge.short_description = 'KYC'

    def wallet_balance(self, obj):
        try:
            total = obj.wallet.total_balance
            return f"₹{total / 100:.2f}"
        except Exception:
            return "No wallet"
    wallet_balance.short_description = 'Wallet'

    # --- Admin Actions ---
    def approve_kyc(self, request, queryset):
        count = 0
        for user in queryset:
            if not user.is_kyc_done:
                old = {'is_kyc_done': False}
                user.is_kyc_done = True
                user.pan_verified = True
                user.save()
                log_admin_action(
                    request.user, f'KYC approved for {user.email}',
                    'User', user.id, old, {'is_kyc_done': True},
                    get_client_ip(request)
                )
                count += 1
        self.message_user(request, f'KYC approved for {count} users.')
    approve_kyc.short_description = 'Approve KYC for selected users'

    def ban_users(self, request, queryset):
        count = 0
        for user in queryset.exclude(is_superuser=True):
            user.is_active = False
            user.save()
            log_admin_action(
                request.user, f'User banned: {user.email}',
                'User', user.id, {'is_active': True}, {'is_active': False},
                get_client_ip(request)
            )
            count += 1
        self.message_user(request, f'{count} users banned.')
    ban_users.short_description = 'Ban selected users'

    def unban_users(self, request, queryset):
        count = queryset.update(is_active=True)
        for user in queryset:
            log_admin_action(
                request.user, f'User unbanned: {user.email}',
                'User', user.id, ip_address=get_client_ip(request)
            )
        self.message_user(request, f'{count} users unbanned.')
    unban_users.short_description = 'Unban selected users'

    def unlock_accounts(self, request, queryset):
        count = queryset.update(
            failed_login_attempts=0,
            lockout_until=None
        )
        self.message_user(request, f'{count} accounts unlocked.')
    unlock_accounts.short_description = 'Unlock locked accounts'


@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = [
        'user_email', 'deposit_inr', 'winnings_inr',
        'bonus_inr', 'total_inr'
    ]
    search_fields = ['user__email']
    readonly_fields = [
        'user', 'deposit_balance', 'winnings_balance',
        'bonus_balance', 'updated_at'
    ]
    ordering = ['-deposit_balance']

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def deposit_inr(self, obj):
        return f"₹{obj.deposit_balance / 100:.2f}"
    deposit_inr.short_description = 'Deposit'

    def winnings_inr(self, obj):
        return f"₹{obj.winnings_balance / 100:.2f}"
    winnings_inr.short_description = 'Winnings'

    def bonus_inr(self, obj):
        return f"₹{obj.bonus_balance / 100:.2f}"
    bonus_inr.short_description = 'Bonus'

    def total_inr(self, obj):
        return f"₹{obj.total_balance / 100:.2f}"
    total_inr.short_description = 'Total'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(OTPVerification)
class OTPAdmin(admin.ModelAdmin):
    list_display = ['email', 'otp_type', 'is_used', 'attempts', 'expires_at', 'created_at']
    list_filter = ['otp_type', 'is_used']
    search_fields = ['email']
    readonly_fields = ['email', 'otp', 'otp_type', 'expires_at', 'created_at']

    def has_add_permission(self, request):
        return False