from django.contrib import admin

from .models import CampaignHit, TelegramContact, UserAcquisition


@admin.register(TelegramContact)
class TelegramContactAdmin(admin.ModelAdmin):
    list_display = (
        'telegram_id', 'username', 'first_name', 'last_name',
        'came_with_token', 'blocked', 'start_count', 'first_seen_at', 'last_seen_at',
    )
    list_filter = ('blocked', 'came_with_token', 'first_seen_at')
    search_fields = ('telegram_id', 'username', 'first_name', 'last_name')
    readonly_fields = ('first_seen_at', 'last_seen_at')
    ordering = ('-last_seen_at',)


@admin.register(CampaignHit)
class CampaignHitAdmin(admin.ModelAdmin):
    list_display = (
        'created_at', 'source', 'medium', 'campaign', 'content',
        'landing_path', 'user',
    )
    list_filter = ('source', 'medium', 'campaign', 'created_at')
    search_fields = ('source', 'medium', 'campaign', 'content', 'term', 'user__username')
    date_hierarchy = 'created_at'
    list_select_related = ('user',)
    ordering = ('-created_at',)

    # Telemetry: browsable, never editable by hand.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UserAcquisition)
class UserAcquisitionAdmin(admin.ModelAdmin):
    list_display = ('user', 'source', 'medium', 'campaign', 'content', 'created_at')
    list_filter = ('source', 'medium', 'campaign', 'created_at')
    search_fields = ('user__username', 'source', 'medium', 'campaign', 'term')
    date_hierarchy = 'created_at'
    list_select_related = ('user',)
    ordering = ('-created_at',)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
