from decimal import Decimal

from django.contrib.auth.models import User
from django.db import models


class SavingsGoal(models.Model):
    name = models.CharField(
        max_length=150,
        default="Housing Fund",
    )

    target_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("50000.00"),
    )

    members = models.ManyToManyField(
        User,
        related_name="shared_savings_goals",
        blank=True,
    )

    start_date = models.DateField(
        auto_now_add=True,
    )

    is_active = models.BooleanField(
        default=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    def __str__(self):
        return self.name

    @property
    def total_saved(self):
        return self.transactions.aggregate(
            total=models.Sum("amount")
        )["total"] or Decimal("0.00")

    @property
    def remaining_amount(self):
        remaining = self.target_amount - self.total_saved
        return max(remaining, Decimal("0.00"))

    @property
    def progress_percentage(self):
        if self.target_amount <= 0:
            return Decimal("0.00")

        progress = (
            self.total_saved / self.target_amount
        ) * Decimal("100")

        return min(progress, Decimal("100.00"))


class SavingsTransaction(models.Model):

    DEPOSIT = "DEPOSIT"
    TRANSFER = "TRANSFER"

    TRANSACTION_TYPES = [
        (DEPOSIT, "Deposit"),
        (TRANSFER, "Transfer"),
    ]

    goal = models.ForeignKey(
        SavingsGoal,
        on_delete=models.CASCADE,
        related_name="transactions",
    )

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="savings_transactions",
    )

    transaction_type = models.CharField(
        max_length=20,
        choices=TRANSACTION_TYPES,
        default=DEPOSIT,
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    transaction_date = models.DateField()

    bank_reference = models.CharField(
        max_length=150,
        blank=True,
    )

    notes = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    recipient = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        related_name="received_savings_transactions",
        null=True,
        blank=True,
    )

    def __str__(self):
        return f"{self.user.username} - ₱{self.amount}"


class TransactionProof(models.Model):
    transaction = models.OneToOneField(
        SavingsTransaction,
        on_delete=models.CASCADE,
        related_name="proof",
    )

    file = models.FileField(
        upload_to="transaction_proofs/",
    )

    uploaded_at = models.DateTimeField(
        auto_now_add=True,
    )

    def __str__(self):
        return f"Proof for transaction #{self.transaction.id}"