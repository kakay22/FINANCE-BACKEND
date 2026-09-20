from django.contrib import admin
from .models import SavingsGoal, SavingsTransaction, TransactionProof


@admin.register(SavingsGoal)
class SavingsGoalAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "target_amount",
        "start_date",
        "is_active",
        "created_at",
    )

    list_filter = (
        "is_active",
    )

    search_fields = (
        "name",
    )

    filter_horizontal = (
        "members",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )


@admin.register(SavingsTransaction)
class SavingsTransactionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "goal",
        "transaction_type",
        "amount",
        "transaction_date",
        "bank_reference",
        "created_at",
    )

    list_filter = (
        "transaction_type",
        "transaction_date",
    )

    search_fields = (
        "user__username",
        "bank_reference",
        "notes",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "-transaction_date",
        "-created_at",
    )


@admin.register(TransactionProof)
class TransactionProofAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "transaction",
        "uploaded_at",
    )

    search_fields = (
        "transaction__bank_reference",
        "transaction__user__username",
    )

    readonly_fields = (
        "uploaded_at",
    )