from decimal import Decimal

from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import Notification
from notifications.utils import create_notification

from .models import Borrowing, Repayment
from .serializers import (
    BorrowingSerializer,
    RepaymentSerializer,
)


class UserBorrowingMixin:

    def get_queryset_for_user(self):
        user = self.request.user

        return (
            Borrowing.objects
            .filter(
                Q(borrower=user)
                |
                Q(lender=user)
            )
            .select_related(
                "borrower",
                "lender",
            )
            .prefetch_related(
                "repayments",
            )
            .distinct()
        )


class BorrowingListCreateView(
    UserBorrowingMixin,
    generics.ListCreateAPIView,
):
    permission_classes = [IsAuthenticated]

    serializer_class = BorrowingSerializer

    def get_queryset(self):
        return (
            self.get_queryset_for_user()
            .order_by(
                "-borrowed_date",
                "-created_at",
            )
        )

    def perform_create(self, serializer):
        borrowing = serializer.save()

        borrower = borrowing.borrower
        lender = borrowing.lender
        amount = borrowing.amount

        # --------------------------------------------------
        # NOTIFY BORROWER
        # --------------------------------------------------

        create_notification(
            user=borrower,
            notification_type=Notification.BORROWING,
            title="Borrowing recorded",
            message=(
                f"₱{amount:,.2f} was recorded "
                f"as borrowed from "
                f"{lender.username}."
            ),
        )

        # --------------------------------------------------
        # NOTIFY LENDER
        # --------------------------------------------------

        if lender != borrower:
            create_notification(
                user=lender,
                notification_type=Notification.BORROWING,
                title="New borrowing",
                message=(
                    f"{borrower.username} recorded a "
                    f"₱{amount:,.2f} borrowing from you."
                ),
            )


class BorrowingDetailView(
    UserBorrowingMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsAuthenticated]

    serializer_class = BorrowingSerializer

    def get_queryset(self):
        return self.get_queryset_for_user()


class BorrowingRepaymentListCreateView(
    generics.ListCreateAPIView,
):
    permission_classes = [IsAuthenticated]

    serializer_class = RepaymentSerializer

    def get_borrowing(self):
        user = self.request.user

        return get_object_or_404(
            Borrowing.objects.filter(
                Q(borrower=user)
                |
                Q(lender=user)
            ).distinct(),
            id=self.kwargs["borrowing_id"],
        )

    def get_queryset(self):
        borrowing = self.get_borrowing()

        return (
            Repayment.objects
            .filter(
                borrowing=borrowing,
            )
            .order_by(
                "-repayment_date",
                "-created_at",
            )
        )

    def perform_create(self, serializer):
        borrowing = self.get_borrowing()

        remaining = self.get_remaining_amount(
            borrowing
        )

        amount = serializer.validated_data[
            "amount"
        ]

        if amount > remaining:
            from rest_framework.exceptions import (
                ValidationError,
            )

            raise ValidationError({
                "amount": (
                    f"Repayment cannot exceed the "
                    f"remaining borrowing balance of "
                    f"₱{remaining:,.2f}."
                )
            })

        # --------------------------------------------------
        # CREATE REPAYMENT
        # --------------------------------------------------

        repayment = serializer.save(
            borrowing=borrowing,
        )

        # --------------------------------------------------
        # UPDATE BORROWING STATUS
        # --------------------------------------------------

        self.update_borrowing_status(
            borrowing
        )

        # --------------------------------------------------
        # NOTIFY BORROWER
        # --------------------------------------------------

        create_notification(
            user=borrowing.borrower,
            notification_type=Notification.REPAYMENT,
            title="Repayment recorded",
            message=(
                f"₱{repayment.amount:,.2f} "
                "repayment was recorded."
            ),
        )

        # --------------------------------------------------
        # NOTIFY LENDER
        # --------------------------------------------------

        if borrowing.lender != borrowing.borrower:
            create_notification(
                user=borrowing.lender,
                notification_type=Notification.REPAYMENT,
                title="Repayment received",
                message=(
                    f"{borrowing.borrower.username} "
                    f"repaid "
                    f"₱{repayment.amount:,.2f}."
                ),
            )

    def get_remaining_amount(self, borrowing):
        total_repaid = (
            borrowing.repayments.aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

        return max(
            borrowing.amount - total_repaid,
            Decimal("0.00"),
        )

    def update_borrowing_status(
        self,
        borrowing,
    ):
        remaining = self.get_remaining_amount(
            borrowing
        )

        today = timezone.now().date()

        if remaining <= Decimal("0.00"):
            borrowing.status = Borrowing.PAID

        elif borrowing.due_date < today:
            borrowing.status = Borrowing.OVERDUE

        else:
            borrowing.status = Borrowing.ACTIVE

        borrowing.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )


class BorrowingRepaymentDetailView(
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsAuthenticated]

    serializer_class = RepaymentSerializer

    def get_queryset(self):
        user = self.request.user

        return (
            Repayment.objects
            .filter(
                Q(
                    borrowing__borrower=user
                )
                |
                Q(
                    borrowing__lender=user
                )
            )
            .select_related(
                "borrowing",
            )
            .distinct()
        )

    def perform_update(self, serializer):
        repayment = self.get_object()
        borrowing = repayment.borrowing

        new_amount = serializer.validated_data.get(
            "amount",
            repayment.amount,
        )

        # Total repayments excluding the repayment
        # currently being edited.
        other_repaid = (
            borrowing.repayments
            .exclude(
                id=repayment.id
            )
            .aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

        remaining_before_this_repayment = (
            borrowing.amount
            - other_repaid
        )

        if new_amount > (
            remaining_before_this_repayment
        ):
            from rest_framework.exceptions import (
                ValidationError,
            )

            raise ValidationError({
                "amount": (
                    "This repayment would exceed "
                    "the remaining borrowing balance."
                )
            })

        serializer.save()

        self.update_borrowing_status(
            borrowing
        )

    def perform_destroy(self, instance):
        borrowing = instance.borrowing

        instance.delete()

        self.update_borrowing_status(
            borrowing
        )

    def update_borrowing_status(
        self,
        borrowing,
    ):
        total_repaid = (
            borrowing.repayments.aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

        remaining = max(
            borrowing.amount - total_repaid,
            Decimal("0.00"),
        )

        today = timezone.now().date()

        if remaining <= Decimal("0.00"):
            borrowing.status = Borrowing.PAID

        elif borrowing.due_date < today:
            borrowing.status = Borrowing.OVERDUE

        else:
            borrowing.status = Borrowing.ACTIVE

        borrowing.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )


class BorrowingSummaryView(
    APIView,
):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        borrowings = (
            Borrowing.objects
            .filter(
                Q(
                    borrower=request.user
                )
                |
                Q(
                    lender=request.user
                )
            )
            .prefetch_related(
                "repayments",
            )
            .distinct()
        )

        total_borrowed = Decimal("0.00")
        total_repaid = Decimal("0.00")
        remaining_amount = Decimal("0.00")

        active_count = 0
        overdue_count = 0
        paid_count = 0

        for borrowing in borrowings:

            total_borrowed += borrowing.amount

            repaid = (
                borrowing.repayments.aggregate(
                    total=Sum("amount")
                )["total"]
                or Decimal("0.00")
            )

            total_repaid += repaid

            remaining = max(
                borrowing.amount - repaid,
                Decimal("0.00"),
            )

            remaining_amount += remaining

            if remaining <= Decimal("0.00"):
                paid_count += 1

            elif (
                borrowing.due_date
                < timezone.now().date()
            ):
                overdue_count += 1

            else:
                active_count += 1

        return Response({
            "total_borrowed": total_borrowed,
            "total_repaid": total_repaid,
            "remaining_amount": remaining_amount,
            "active_count": active_count,
            "overdue_count": overdue_count,
            "paid_count": paid_count,
            "total_count": borrowings.count(),
        })