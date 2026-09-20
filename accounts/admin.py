from django.contrib import admin
from .models import UserProfile


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "display_name",
        "created_at",
    )

    search_fields = (
        "user__username",
        "user__email",
        "display_name",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )