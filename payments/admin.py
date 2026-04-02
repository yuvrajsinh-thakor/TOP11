from django.contrib import admin
from django.utils.html import format_html
from django.utils import timezone
from .models import Transaction, Withdrawal
from top11_project.admin_helpers import log_admin_action, get_client_ip


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'user_email', 'type_badge',
        'status_badge', 'amount_inr', 'wallet_bucket'
    ]
    list_filter = ['transaction_type', 'status', 'wallet_bucket']
    search_fields = ['user__email', 'cashfree_order_id', 'cashfree_payment_id']
    readonly_fields = [
        'user', 'transaction_type', 'amount', 'wallet_bucket',
        'cashfree_order_id', 'cashfree_payment_id',
        'description', 'idempotency_key', 'created_at', 'updated_at',
    ]
    ordering = ['-created_at']
    date_hierarchy = 'created_at'

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def type_badge(self, obj):
        colors = {
            'deposit': '#185FA5', 'withdrawal': '#854F0B',
            'contest_entry': '#534AB7', 'prize_credit': '#1D9E75',
            'refund': '#888780', 'tds': '#E24B4A', 'bonus': '#0F6E56'
        }
        color = colors.get(obj.transaction_type, '#888')
        return format_html(
            '<span style="background:{};color:#fff;padding:2px 6px;'
            'border-radius:4px;font-size:11px;">{}</span>',
            color, obj.transaction_type.upper()
        )
    type_badge.short_description = 'Type'

    def status_badge(self, obj):
        colors = {
            'success': '#1D9E75', 'pending': '#BA7517',
            'failed': '#E24B4A', 'refunded': '#888780'
        }
        color = colors.get(obj.status, '#888')
        return format_html(
            '<span style="color:{};">{}</span>',
            color, obj.status.upper()
        )
    status_badge.short_description = 'Status'

    def amount_inr(self, obj):
        return f"₹{obj.amount / 100:.2f}"
    amount_inr.short_description = 'Amount'

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = [
        'created_at', 'user_email', 'amount_inr',
        'method', 'status_badge', 'processed_by_name'
    ]
    list_filter = ['status']
    search_fields = ['user__email', 'cashfree_transfer_id', 'upi_id']
    readonly_fields = [
        'user', 'amount', 'bank_account', 'bank_ifsc',
        'upi_id', 'cashfree_transfer_id', 'created_at'
    ]
    ordering = ['-created_at']
    actions = ['approve_withdrawals', 'reject_withdrawals']

    fieldsets = (
        ('Withdrawal info', {
            'fields': ('user', 'amount', 'status')
        }),
        ('Payment details', {
            'fields': ('bank_account', 'bank_ifsc', 'upi_id', 'cashfree_transfer_id')
        }),
        ('Processing', {
            'fields': ('processed_by', 'processed_at', 'rejection_reason')
        }),
        ('Timestamps', {
            'fields': ('created_at',), 'classes': ('collapse',)
        }),
    )

    def user_email(self, obj):
        return obj.user.email
    user_email.short_description = 'User'

    def amount_inr(self, obj):
        return f"₹{obj.amount / 100:.2f}"
    amount_inr.short_description = 'Amount'

    def method(self, obj):
        if obj.upi_id:
            return f"UPI: {obj.upi_id}"
        if obj.bank_account:
            return f"Bank: ...{obj.bank_account[-4:]}"
        return '—'
    method.short_description = 'Method'

    def status_badge(self, obj):
        colors = {
            'pending': '#BA7517', 'processing': '#185FA5',
            'success': '#1D9E75', 'failed': '#E24B4A', 'rejected': '#888780'
        }
        color = colors.get(obj.status, '#888')
        return format_html(
            '<span style="color:{};">{}</span>',
            color, obj.status.upper()
        )
    status_badge.short_description = 'Status'

    def processed_by_name(self, obj):
        return obj.processed_by.email if obj.processed_by else '—'
    processed_by_name.short_description = 'Processed by'

    def approve_withdrawals(self, request, queryset):
        count = 0
        for w in queryset.filter(status='pending'):
            w.status = 'processing'
            w.processed_by = request.user
            w.processed_at = timezone.now()
            w.save()
            log_admin_action(
                request.user, f'Withdrawal approved: ₹{w.amount/100:.2f} for {w.user.email}',
                'Withdrawal', w.id, ip_address=get_client_ip(request)
            )
            count += 1
        self.message_user(request, f'{count} withdrawals approved for processing.')
    approve_withdrawals.short_description = 'Approve selected withdrawals'

    def reject_withdrawals(self, request, queryset):
        from payments.models import Transaction
        from accounts.models import Wallet
        count = 0
        for w in queryset.filter(status__in=['pending', 'processing']):
            # Refund to wallet
            wallet = w.user.wallet
            wallet.winnings_balance += w.amount
            wallet.save()
            Transaction.objects.create(
                user=w.user,
                transaction_type='refund',
                status='success',
                amount=w.amount,
                wallet_bucket='winnings',
                description=f'Refund: withdrawal rejected by admin',
                idempotency_key=f'admin_reject_{w.id}',
            )
            w.status = 'rejected'
            w.rejection_reason = 'Rejected by admin'
            w.processed_by = request.user
            w.processed_at = timezone.now()
            w.save()
            log_admin_action(
                request.user, f'Withdrawal rejected: ₹{w.amount/100:.2f} for {w.user.email}',
                'Withdrawal', w.id, ip_address=get_client_ip(request)
            )
            count += 1
        self.message_user(request, f'{count} withdrawals rejected and refunded.')
    reject_withdrawals.short_description = 'Reject and refund selected withdrawals'