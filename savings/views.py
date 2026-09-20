from decimal import Decimal

from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404
from django.utils import timezone

from rest_framework import generics, status
from rest_framework.parsers import (
    FormParser,
    JSONParser,
    MultiPartParser,
)
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from notifications.models import Notification
from notifications.utils import create_notification

from .models import (
    SavingsGoal,
    SavingsTransaction,
    TransactionProof,
)

from .serializers import (
    SavingsGoalSerializer,
    SavingsTransactionSerializer,
    TransactionProofSerializer,
)


class UserGoalMixin:
    def get_goal(self):
        return get_object_or_404(
            SavingsGoal,
            members=self.request.user,
            is_active=True,
        )


class SavingsGoalView(
    UserGoalMixin,
    APIView,
):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        goal = self.get_goal()

        serializer = SavingsGoalSerializer(
            goal,
            context={"request": request},
        )

        return Response(serializer.data)


class SavingsTransactionListCreateView(
    UserGoalMixin,
    generics.ListCreateAPIView,
):
    permission_classes = [IsAuthenticated]

    serializer_class = SavingsTransactionSerializer

    def get_queryset(self):
        goal = self.get_goal()

        return (
            SavingsTransaction.objects
            .filter(goal=goal)
            .select_related("user", "goal")
            .prefetch_related("proof")
            .order_by(
                "-transaction_date",
                "-created_at",
            )
        )

    def perform_create(self, serializer):
        goal = self.get_goal()

        transaction = serializer.save(
            user=self.request.user,
            goal=goal,
        )

        user = self.request.user

        if transaction.transaction_type == SavingsTransaction.DEPOSIT:
            # Notify the person who deposited
            create_notification(
                user=user,
                notification_type=Notification.TRANSACTION,
                title="Money deposited",
                message=(
                    f"₱{transaction.amount:,.2f} "
                    "was added to your savings."
                ),
            )

            # Notify the other members
            other_members = goal.members.exclude(
                id=user.id
            )

            for member in other_members:
                create_notification(
                    user=member,
                    notification_type=Notification.TRANSACTION,
                    title="New deposit",
                    message=(
                        f"{user.username} deposited "
                        f"₱{transaction.amount:,.2f} "
                        "into the shared savings fund."
                    ),
                )

        elif transaction.transaction_type == SavingsTransaction.TRANSFER:
            recipient = transaction.recipient

            create_notification(
                user=user,
                notification_type=Notification.TRANSACTION,
                title="Transfer completed",
                message=(
                    f"₱{transaction.amount:,.2f} "
                    f"was transferred to "
                    f"{recipient.username}."
                ),
            )

            create_notification(
                user=recipient,
                notification_type=Notification.TRANSACTION,
                title="Money received",
                message=(
                    f"You received "
                    f"₱{transaction.amount:,.2f} "
                    f"from {user.username}."
                ),
            )


class SavingsTransactionDetailView(
    UserGoalMixin,
    generics.RetrieveUpdateDestroyAPIView,
):
    permission_classes = [IsAuthenticated]

    serializer_class = SavingsTransactionSerializer

    def get_queryset(self):
        goal = self.get_goal()

        return (
            SavingsTransaction.objects
            .filter(goal=goal)
            .select_related("user", "goal")
            .prefetch_related("proof")
        )

    def perform_update(self, serializer):
        transaction = self.get_object()

        if transaction.user != self.request.user:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied(
                "You can only edit your own transactions."
            )

        serializer.save()

    def perform_destroy(self, instance):
        if instance.user != self.request.user:
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied(
                "You can only delete your own transactions."
            )

        instance.delete()


class TransactionProofView(APIView):
    permission_classes = [IsAuthenticated]

    parser_classes = (
        MultiPartParser,
        FormParser,
        JSONParser,
    )

    def post(self, request, transaction_id):
        transaction = get_object_or_404(
            SavingsTransaction,
            id=transaction_id,
            goal__members=request.user,
        )

        if transaction.user != request.user:
            return Response(
                {
                    "detail": (
                        "Only the person who created "
                        "the transaction can upload proof."
                    )
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        if hasattr(transaction, "proof"):
            return Response(
                {
                    "detail": (
                        "This transaction already has proof."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        file = request.FILES.get("file")

        if not file:
            return Response(
                {
                    "detail": "A proof file is required."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = TransactionProofSerializer(
            data={"file": file},
        )

        serializer.is_valid(
            raise_exception=True
        )

        proof = serializer.save(
            transaction=transaction,
        )

        return Response(
            TransactionProofSerializer(proof).data,
            status=status.HTTP_201_CREATED,
        )


class SavingsDashboardView(
    UserGoalMixin,
    APIView,
):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        goal = self.get_goal()

        transactions = (
            SavingsTransaction.objects
            .filter(goal=goal)
            .select_related("user")
            .prefetch_related("proof")
            .order_by(
                "-transaction_date",
                "-created_at",
            )
        )

        # --------------------------------------------------
        # TOTAL CONTRIBUTIONS
        # --------------------------------------------------

        total_contributions = (
            transactions.aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

        # --------------------------------------------------
        # SHARED MEMBERS
        # --------------------------------------------------

        member_ids = list(
            goal.members.values_list(
                "id",
                flat=True,
            )
        )

        # --------------------------------------------------
        # BORROWINGS
        #
        # A borrowing is money taken out of the shared
        # housing savings.
        # --------------------------------------------------

        from borrowings.models import (
            Borrowing,
            Repayment,
        )

        borrowings = Borrowing.objects.filter(
            Q(borrower_id__in=member_ids)
            | Q(lender_id__in=member_ids)
        ).distinct()

        # --------------------------------------------------
        # TOTAL BORROWED
        # --------------------------------------------------

        total_borrowed = (
            borrowings.aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

        # --------------------------------------------------
        # TOTAL REPAYMENTS
        # --------------------------------------------------

        total_repaid = (
            Repayment.objects.filter(
                borrowing__in=borrowings,
            ).aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

        # --------------------------------------------------
        # OUTSTANDING BORROWINGS
        # --------------------------------------------------

        outstanding_borrowings = max(
            total_borrowed - total_repaid,
            Decimal("0.00"),
        )

        # --------------------------------------------------
        # AVAILABLE SAVINGS
        #
        # This is the actual money still available for
        # the housing goal.
        # --------------------------------------------------

        available_savings = max(
            total_contributions
            - outstanding_borrowings,
            Decimal("0.00"),
        )

        # --------------------------------------------------
        # REMAINING GOAL
        # --------------------------------------------------

        remaining_amount = max(
            goal.target_amount - available_savings,
            Decimal("0.00"),
        )

        # --------------------------------------------------
        # PROGRESS
        # --------------------------------------------------

        if goal.target_amount > 0:
            progress_percentage = (
                available_savings
                / goal.target_amount
            ) * Decimal("100")

            progress_percentage = min(
                progress_percentage,
                Decimal("100.00"),
            )
        else:
            progress_percentage = Decimal("0.00")

        # --------------------------------------------------
        # TRANSACTION COUNT
        # --------------------------------------------------

        total_transactions = transactions.count()

        # --------------------------------------------------
        # CONTRIBUTIONS BY USER
        # --------------------------------------------------

        contribution_data = (
            transactions
            .values(
                "user_id",
                "user__username",
            )
            .annotate(
                total=Sum("amount"),
            )
            .order_by("-total")
        )

        contributions = [
            {
                "user_id": item["user_id"],
                "username": item["user__username"],
                "amount": item["total"],
            }
            for item in contribution_data
        ]

        # --------------------------------------------------
        # MONTHLY AVERAGE
        # --------------------------------------------------

        today = timezone.now().date()

        months_elapsed = (
            (today.year - goal.start_date.year) * 12
            + today.month
            - goal.start_date.month
        )

        months_elapsed = max(
            months_elapsed,
            1,
        )

        average_monthly_savings = (
            total_contributions
            / Decimal(months_elapsed)
        )

        # --------------------------------------------------
        # ESTIMATED TIME TO GOAL
        # --------------------------------------------------

        if (
            remaining_amount > 0
            and average_monthly_savings > 0
        ):
            estimated_months_remaining = (
                remaining_amount
                / average_monthly_savings
            )
        else:
            estimated_months_remaining = None

        # --------------------------------------------------
        # RECENT TRANSACTIONS
        # --------------------------------------------------

        recent_transactions = [
            {
                "id": transaction.id,
                "user": {
                    "id": transaction.user.id,
                    "username": transaction.user.username,
                },
                "transaction_type": (
                    transaction.transaction_type
                ),
                "amount": transaction.amount,
                "transaction_date": (
                    transaction.transaction_date
                ),
                "bank_reference": (
                    transaction.bank_reference
                ),
                "notes": transaction.notes,
                "has_proof": hasattr(
                    transaction,
                    "proof",
                ),
            }
            for transaction in transactions[:5]
        ]

        # --------------------------------------------------
        # RESPONSE
        # --------------------------------------------------

        return Response(
            {
                "goal": SavingsGoalSerializer(
                    goal,
                    context={
                        "request": request,
                    },
                ).data,

                # Original contributions
                "total_saved": total_contributions,

                "total_contributions": (
                    total_contributions
                ),

                # Borrowing taken from savings
                "total_borrowed": total_borrowed,

                # Borrowing minus repayments
                "outstanding_borrowings": (
                    outstanding_borrowings
                ),

                # Actual available housing money
                "available_savings": available_savings,

                # Amount still needed for target
                "remaining_amount": remaining_amount,

                "progress_percentage": (
                    progress_percentage
                ),

                "total_transactions": (
                    total_transactions
                ),

                "average_monthly_savings": (
                    average_monthly_savings
                ),

                "estimated_months_remaining": (
                    estimated_months_remaining
                ),

                "contributions": contributions,

                "recent_transactions": (
                    recent_transactions
                ),
            }
        )