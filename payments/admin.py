from django.contrib import admin
from .models import Transaction, Withdrawal


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'transaction_type', 'status',
        'amount_inr', 'wallet_bucket', 'created_at'
    ]
    list_filter = ['transaction_type', 'status', 'wallet_bucket']
    search_fields = ['user__email', 'cashfree_order_id', 'cashfree_payment_id']
    readonly_fields = [
        'user', 'transaction_type', 'amount', 'wallet_bucket',
        'cashfree_order_id', 'cashfree_payment_id',
        'idempotency_key', 'created_at',
    ]
    ordering = ['-created_at']

    def amount_inr(self, obj):
        return f"₹{obj.amount / 100:.2f}"
    amount_inr.short_description = 'Amount'

    def has_add_permission(self, request):
        return False   # Transactions are system-generated only

    def has_delete_permission(self, request, obj=None):
        return False   # Never delete financial records


@admin.register(Withdrawal)
class WithdrawalAdmin(admin.ModelAdmin):
    list_display = [
        'user', 'amount_inr', 'status',
        'upi_id', 'bank_account', 'created_at'
    ]
    list_filter = ['status']
    search_fields = ['user__email', 'cashfree_transfer_id']
    readonly_fields = ['user', 'amount', 'cashfree_transfer_id', 'created_at']
    ordering = ['-created_at']

    def amount_inr(self, obj):
        return f"₹{obj.amount / 100:.2f}"
    amount_inr.short_description = 'Amount'