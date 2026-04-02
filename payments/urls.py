from django.urls import path
from . import views

urlpatterns = [
    # Wallet
    path('wallet/', views.WalletView.as_view(), name='wallet'),

    # Deposits
    path('deposit/', views.DepositView.as_view(), name='deposit'),
    path('verify-deposit/', views.VerifyDepositView.as_view(), name='verify-deposit'),

    # Webhook (Cashfree calls this)
    path('webhook/cashfree/', views.CashfreeWebhookView.as_view(), name='cashfree-webhook'),

    # Withdrawals
    path('withdraw/', views.WithdrawView.as_view(), name='withdraw'),
    path('withdrawals/', views.WithdrawalHistoryView.as_view(), name='withdrawal-history'),

    # History
    path('transactions/', views.TransactionHistoryView.as_view(), name='transactions'),

    # KYC
    path('kyc/', views.KYCView.as_view(), name='kyc'),
]