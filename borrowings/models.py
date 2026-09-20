from django.contrib.auth.models import User
from django.db import models


class Borrowing(models.Model):

    ACTIVE = "ACTIVE"
    PAID = "PAID"
    OVERDUE = "OVERDUE"

    STATUS_CHOICES = [
        (ACTIVE, "Active"),
        (PAID, "Paid"),
        (OVERDUE, "Overdue"),
    ]

    borrower = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="borrowings",
    )

    lender = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="loans_given",
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    borrowed_date = models.DateField()

    due_date = models.DateField()

    reason = models.TextField(
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=ACTIVE,
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

    def __str__(self):
        return f"₱{self.amount} - {self.borrower.username}"


class Repayment(models.Model):

    borrowing = models.ForeignKey(
        Borrowing,
        on_delete=models.CASCADE,
        related_name="repayments",
    )

    amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
    )

    repayment_date = models.DateField()

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

    def __str__(self):
        return f"₱{self.amount} repayment"