from django.contrib import admin

from basebox.models.base import ScheduledTaskLog
from basebox.models.error_log import ErrorLog


@admin.register(ScheduledTaskLog)
class ScheduledTaskLogAdmin(admin.ModelAdmin):
    list_display = ['name', 'start_time', 'end_time', 'status', 'date_created']
    list_filter = ['name', 'start_time', 'end_time', 'status', 'date_created']
    search_fields = ['name', 'start_time', 'end_time', 'status']
    readonly_fields = ['date_created', 'last_updated']
    exclude = ['json_meta']
    list_per_page = 25
    date_hierarchy = 'date_created'


@admin.register(ErrorLog)
class ErrorLogAdmin(admin.ModelAdmin):
    list_display = ['level', 'status_code', 'message', 'traceback', 'path',
        'method', 'user', 'date_created', 'last_updated']
    list_filter = ['level', 'status_code', 'method']
    search_fields = ['message', 'traceback', 'path', 'user']
    ordering = ['-date_created']
    readonly_fields = [
        'uuid', 'level', 'status_code', 'message', 'traceback', 'path',
        'method', 'user', 'date_created', 'last_updated',
    ]
    exclude = ['json_meta', 'is_active', 'type']
    list_per_page = 50
    date_hierarchy = 'date_created'


    def short_message(self, obj):
        return obj.message[:120] if obj.message else ''
    short_message.short_description = 'Message'

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
