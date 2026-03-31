from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, OTPVerification, Wallet

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ['email', 'full_name', 'is_verified', 'is_kyc_done', 'created_at']
    list_filter = ['is_verified', 'is_kyc_done', 'role']
    search_fields = ['email', 'full_name', 'mobile']
    ordering = ['-created_at']
    fieldsets = (
        (None, {'fields': ('email', 'password')}),
        ('Personal', {'fields': ('full_name', 'mobile', 'avatar')}),
        ('Status', {'fields': ('is_active', 'is_verified', 'is_kyc_done', 'role')}),
        ('KYC', {'fields': ('pan_number', 'pan_verified', 'bank_account_number', 'bank_ifsc', 'upi_id')}),
        ('Security', {'fields': ('failed_login_attempts', 'lockout_until', 'last_login_ip')}),
        ('Referral', {'fields': ('referral_code', 'referred_by')}),
    )
    add_fieldsets = (
        (None, {'fields': ('email', 'password1', 'password2')}),
    )

@admin.register(OTPVerification)
class OTPAdmin(admin.ModelAdmin):
    list_display = ['email', 'otp_type', 'is_used', 'expires_at', 'created_at']
    list_filter = ['otp_type', 'is_used']

@admin.register(Wallet)
class WalletAdmin(admin.ModelAdmin):
    list_display = ['user', 'deposit_balance', 'winnings_balance', 'bonus_balance']
    search_fields = ['user__email']
    readonly_fields = ['user']