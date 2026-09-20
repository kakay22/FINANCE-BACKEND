from django.urls import path

from .views import (
    SavingsGoalView,
    SavingsDashboardView,
    SavingsTransactionListCreateView,
    SavingsTransactionDetailView,
    TransactionProofView,
)


urlpatterns = [
    path(
        "goal/",
        SavingsGoalView.as_view(),
        name="savings-goal",
    ),

    path(
        "dashboard/",
        SavingsDashboardView.as_view(),
        name="savings-dashboard",
    ),

    path(
        "transactions/",
        SavingsTransactionListCreateView.as_view(),
        name="savings-transactions",
    ),

    path(
        "transactions/<int:pk>/",
        SavingsTransactionDetailView.as_view(),
        name="savings-transaction-detail",
    ),

    path(
        "transactions/<int:transaction_id>/proof/",
        TransactionProofView.as_view(),
        name="transaction-proof",
    ),
]