from django.contrib import admin

from basebox.models import ErrorLog, ScheduledTaskLog


@admin.register(ScheduledTaskLog)
class ScheduledTaskLogAdmin(admin.ModelAdmin):
    list_display = ["name", "status", "start_time", "end_time", "message"]
    list_filter = ["name", "status"]
    search_fields = ["name", "message"]
    readonly_fields = ["date_created", "last_updated"]
    list_per_page = 25
    date_hierarchy = "start_time"


@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ["level", "status_code", "short_message", "path", "method", "date_created"]
    list_filter = ["level", "status_code", "method"]
    search_fields = ["message", "traceback", "path"]
    readonly_fields = [
        "level",
        "status_code",
        "message",
        "traceback",
        "path",
        "method",
        "date_created",
        "last_updated",
    ]
    list_per_page = 50
    date_hierarchy = "date_created"

    @admin.display(description="Message")
    def short_message(self, obj):
        return obj.message[:120] if obj.message else ""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
