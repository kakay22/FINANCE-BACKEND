from django.urls import path

from .views import (
    BorrowingListCreateView,
    BorrowingDetailView,
    BorrowingRepaymentListCreateView,
    BorrowingRepaymentDetailView,
    BorrowingSummaryView,
)


urlpatterns = [

    path(
        "",
        BorrowingListCreateView.as_view(),
        name="borrowing-list",
    ),

    path(
        "summary/",
        BorrowingSummaryView.as_view(),
        name="borrowing-summary",
    ),

    path(
        "<int:pk>/",
        BorrowingDetailView.as_view(),
        name="borrowing-detail",
    ),

    path(
        "<int:borrowing_id>/repayments/",
        BorrowingRepaymentListCreateView.as_view(),
        name="borrowing-repayments",
    ),

    path(
        "repayments/<int:pk>/",
        BorrowingRepaymentDetailView.as_view(),
        name="borrowing-repayment-detail",
    ),
]