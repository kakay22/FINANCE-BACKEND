from django.urls import path

from .views import (
    ChangePasswordView,
    RegisterView,
    ProfileView,
    PublicProfileView,
    GoalMemberListView,
)


urlpatterns = [
    path(
        "register/",
        RegisterView.as_view(),
        name="register",
    ),

    path(
        "profile/",
        ProfileView.as_view(),
        name="profile",
    ),

    path(
        "users/<int:user_id>/",
        PublicProfileView.as_view(),
        name="public-profile",
    ),

    path(
        "change-password/",
        ChangePasswordView.as_view(),
        name="change-password",
    ),
    path(
        "users/",
        GoalMemberListView.as_view(),
        name="goal-member-list",
    ),
]