from django.db import models
from django.conf import settings
import uuid


class Transaction(models.Model):
    """Every single money movement — immutable audit trail"""

    TYPE_CHOICES = [
        ('deposit', 'Deposit'),
        ('withdrawal', 'Withdrawal'),
        ('contest_entry', 'Contest Entry'),
        ('prize_credit', 'Prize Credit'),
        ('refund', 'Refund'),
        ('bonus', 'Bonus Credit'),
        ('tds', 'TDS Deduction'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    WALLET_BUCKET_CHOICES = [
        ('deposit', 'Deposit Balance'),
        ('winnings', 'Winnings Balance'),
        ('bonus', 'Bonus Balance'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')

    # Amount always in paise
    amount = models.BigIntegerField()
    wallet_bucket = models.CharField(max_length=10, choices=WALLET_BUCKET_CHOICES)

    # Cashfree references
    cashfree_order_id = models.CharField(max_length=200, blank=True, db_index=True)
    cashfree_payment_id = models.CharField(max_length=200, blank=True)
    cashfree_signature = models.CharField(max_length=500, blank=True)

    # What this transaction is for
    description = models.CharField(max_length=300, blank=True)
    contest_entry = models.ForeignKey(
        'contests.ContestEntry', null=True, blank=True, on_delete=models.SET_NULL
    )

    # Idempotency — prevent double-processing webhooks
    idempotency_key = models.CharField(max_length=200, unique=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'transactions'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.transaction_type} — ₹{self.amount/100:.2f} — {self.user.email}"


class Withdrawal(models.Model):
    """Withdrawal request from user — processed via Cashfree Payouts"""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('failed', 'Failed'),
        ('rejected', 'Rejected'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='withdrawals')
    amount = models.BigIntegerField()                        # In paise
    status = models.CharField(max_length=15, choices=STATUS_CHOICES, default='pending')

    # Where to send money
    bank_account = models.CharField(max_length=20, blank=True)
    bank_ifsc = models.CharField(max_length=11, blank=True)
    upi_id = models.CharField(max_length=100, blank=True)

    # Cashfree Payout reference
    cashfree_transfer_id = models.CharField(max_length=200, blank=True)
    rejection_reason = models.CharField(max_length=300, blank=True)

    # Admin who processed it
    processed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='processed_withdrawals'
    )
    processed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'withdrawals'

    def __str__(self):
        return f"₹{self.amount/100:.2f} withdrawal by {self.user.email} — {self.status}"