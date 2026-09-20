from decimal import Decimal

from django.contrib.auth.models import User
from django.db.models import Sum
from django.utils import timezone

from rest_framework import serializers

from .models import Borrowing, Repayment


class UserSimpleSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = (
            "id",
            "username",
        )


class RepaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Repayment

        fields = (
            "id",
            "borrowing",
            "amount",
            "repayment_date",
            "bank_reference",
            "notes",
            "created_at",
        )

        read_only_fields = (
            "id",
            "borrowing",
            "created_at",
        )

    def validate_amount(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError(
                "Repayment amount must be greater than zero."
            )

        return value


class BorrowingSerializer(serializers.ModelSerializer):

    borrower = UserSimpleSerializer(
        read_only=True,
    )

    lender = UserSimpleSerializer(
        read_only=True,
    )

    borrower_id = serializers.IntegerField(
        write_only=True,
        required=False,
    )

    lender_id = serializers.IntegerField(
        write_only=True,
        required=False,
    )

    total_repaid = serializers.SerializerMethodField()

    remaining_amount = serializers.SerializerMethodField()

    repayment_percentage = serializers.SerializerMethodField()

    repayments = RepaymentSerializer(
        many=True,
        read_only=True,
    )

    class Meta:
        model = Borrowing

        fields = (
            "id",
            "borrower",
            "borrower_id",
            "lender",
            "lender_id",
            "amount",
            "borrowed_date",
            "due_date",
            "reason",
            "status",
            "notes",
            "total_repaid",
            "remaining_amount",
            "repayment_percentage",
            "repayments",
            "created_at",
            "updated_at",
        )

        read_only_fields = (
            "id",
            "borrower",
            "lender",
            "status",
            "total_repaid",
            "remaining_amount",
            "repayment_percentage",
            "repayments",
            "created_at",
            "updated_at",
        )

    # ---------------------------------------------------------
    # BASIC AMOUNT VALIDATION
    # ---------------------------------------------------------

    def validate_amount(self, value):
        if value <= Decimal("0.00"):
            raise serializers.ValidationError(
                "Borrowing amount must be greater than zero."
            )

        return value

    # ---------------------------------------------------------
    # SHARED FUND HELPERS
    # ---------------------------------------------------------

    def get_shared_goal(self):
        request = self.context.get("request")

        if not request or not request.user.is_authenticated:
            raise serializers.ValidationError(
                "Authentication is required."
            )

        from savings.models import SavingsGoal

        goal = (
            SavingsGoal.objects
            .filter(
                members=request.user,
                is_active=True,
            )
            .first()
        )

        if not goal:
            raise serializers.ValidationError({
                "detail": (
                    "You are not a member of an active "
                    "shared savings goal."
                )
            })

        return goal

    def get_total_savings(self, goal):
        from savings.models import SavingsTransaction

        total = (
            SavingsTransaction.objects
            .filter(goal=goal)
            .aggregate(
                total=Sum("amount")
            )["total"]
        )

        return total or Decimal("0.00")

    def get_outstanding_amount(self, borrowing):
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

    def get_total_outstanding_borrowings(
        self,
        goal,
        exclude_id=None,
    ):
        """
        Calculate how much money from the shared savings
        fund is currently tied up in borrowings.

        The current borrowing can be excluded when editing it.
        """

        from django.db.models import Q

        borrowings = Borrowing.objects.filter(
            Q(
                borrower__in=goal.members.all()
            )
            |
            Q(
                lender__in=goal.members.all()
            )
        ).distinct()

        if exclude_id is not None:
            borrowings = borrowings.exclude(
                id=exclude_id
            )

        total = Decimal("0.00")

        for borrowing in borrowings:
            total += self.get_outstanding_amount(
                borrowing
            )

        return total

    # ---------------------------------------------------------
    # CREATE / VALIDATE
    # ---------------------------------------------------------

    def validate(self, attrs):
        borrower_id = attrs.get(
            "borrower_id"
        )

        lender_id = attrs.get(
            "lender_id"
        )

        # During UPDATE these aren't submitted by the
        # frontend, so use the existing users.
        if self.instance:
            borrower_id = (
                borrower_id
                if borrower_id is not None
                else self.instance.borrower_id
            )

            lender_id = (
                lender_id
                if lender_id is not None
                else self.instance.lender_id
            )

        if borrower_id == lender_id:
            raise serializers.ValidationError({
                "lender_id": (
                    "Borrower and lender must be "
                    "different users."
                )
            })

        goal = self.get_shared_goal()

        member_ids = set(
            goal.members.values_list(
                "id",
                flat=True,
            )
        )

        if borrower_id not in member_ids:
            raise serializers.ValidationError({
                "borrower_id": (
                    "The borrower must be a member "
                    "of your shared savings goal."
                )
            })

        if lender_id not in member_ids:
            raise serializers.ValidationError({
                "lender_id": (
                    "The lender must be a member "
                    "of your shared savings goal."
                )
            })

        # -----------------------------------------------------
        # FUND VALIDATION
        # -----------------------------------------------------

        if "amount" in attrs:
            new_amount = attrs["amount"]

            total_savings = self.get_total_savings(
                goal
            )

            if self.instance:
                # Amount already tied up by THIS borrowing.
                current_outstanding = (
                    self.get_outstanding_amount(
                        self.instance
                    )
                )

                # Amount already repaid cannot be lost.
                total_repaid = (
                    self.get_total_repaid(
                        self.instance
                    )
                )

                if new_amount < total_repaid:
                    raise serializers.ValidationError({
                        "amount": (
                            f"The borrowing amount cannot be "
                            f"less than the amount already "
                            f"repaid ({total_repaid})."
                        )
                    })

                # Available fund if this borrowing is
                # temporarily removed from the calculation.
                other_outstanding = (
                    self.get_total_outstanding_borrowings(
                        goal,
                        exclude_id=self.instance.id,
                    )
                )

                available_for_this_borrowing = (
                    total_savings
                    - other_outstanding
                )

                new_outstanding = (
                    new_amount
                    - total_repaid
                )

                if new_outstanding > (
                    available_for_this_borrowing
                ):
                    raise serializers.ValidationError({
                        "amount": (
                            "The new borrowing amount would "
                            "exceed the available shared "
                            "savings fund."
                        )
                    })

            else:
                outstanding = (
                    self.get_total_outstanding_borrowings(
                        goal
                    )
                )

                available_savings = (
                    total_savings
                    - outstanding
                )

                if new_amount > available_savings:
                    raise serializers.ValidationError({
                        "amount": (
                            "Borrowing amount exceeds the "
                            "available shared savings fund."
                        )
                    })

        return attrs

    # ---------------------------------------------------------
    # CREATE
    # ---------------------------------------------------------

    def create(self, validated_data):

        borrower_id = validated_data.pop(
            "borrower_id"
        )

        lender_id = validated_data.pop(
            "lender_id"
        )

        borrower = User.objects.get(
            id=borrower_id
        )

        lender = User.objects.get(
            id=lender_id
        )

        return Borrowing.objects.create(
            borrower=borrower,
            lender=lender,
            **validated_data,
        )

    # ---------------------------------------------------------
    # UPDATE
    # ---------------------------------------------------------

    def update(
        self,
        instance,
        validated_data,
    ):

        # Borrower and lender are intentionally not editable
        # from the edit page.
        validated_data.pop(
            "borrower_id",
            None,
        )

        validated_data.pop(
            "lender_id",
            None,
        )

        instance = super().update(
            instance,
            validated_data,
        )

        # Recalculate status after editing.
        remaining = self.get_remaining_amount(
            instance
        )

        today = timezone.now().date()

        if remaining <= Decimal("0.00"):
            instance.status = Borrowing.PAID

        elif instance.due_date < today:
            instance.status = Borrowing.OVERDUE

        else:
            instance.status = Borrowing.ACTIVE

        instance.save(
            update_fields=[
                "status",
                "updated_at",
            ]
        )

        return instance

    # ---------------------------------------------------------
    # REPAYMENT CALCULATIONS
    # ---------------------------------------------------------

    def get_total_repaid(self, obj):
        return (
            obj.repayments.aggregate(
                total=Sum("amount")
            )["total"]
            or Decimal("0.00")
        )

    def get_remaining_amount(self, obj):
        total_repaid = self.get_total_repaid(
            obj
        )

        remaining = (
            obj.amount - total_repaid
        )

        return max(
            remaining,
            Decimal("0.00"),
        )

    def get_repayment_percentage(self, obj):
        if obj.amount <= Decimal("0.00"):
            return Decimal("0.00")

        total_repaid = self.get_total_repaid(
            obj
        )

        percentage = (
            total_repaid / obj.amount
        ) * Decimal("100")

        return min(
            percentage,
            Decimal("100.00"),
        )