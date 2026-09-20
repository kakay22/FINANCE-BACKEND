from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from rest_framework_simplejwt.views import (
    TokenObtainPairView,
    TokenRefreshView,
)


urlpatterns = [
    # Admin
    path(
        "admin/",
        admin.site.urls,
    ),

    # Authentication
    path(
        "api/auth/",
        include("accounts.urls"),
    ),

    path(
        "api/auth/login/",
        TokenObtainPairView.as_view(),
        name="token-login",
    ),

    path(
        "api/auth/refresh/",
        TokenRefreshView.as_view(),
        name="token-refresh",
    ),

    # Savings
    path(
        "api/savings/",
        include("savings.urls"),
    ),

    # Borrowings
    path(
        "api/borrowings/",
        include("borrowings.urls"),
    ),

    #notidications
    path(
        "api/notifications/",
        include("notifications.urls"),
    ),
]


if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )