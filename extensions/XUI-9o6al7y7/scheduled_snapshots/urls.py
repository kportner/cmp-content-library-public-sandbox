from django.urls import path

from xui.scheduled_snapshots import views

xui_urlpatterns = [
    path('snapshots/configure_schedule/<int:server_id>/', views.configure_snapshot_schedule,
        name='configure_snapshot_schedule'),
    path('snapshots/configure_max/<int:server_id>/',
        views.configure_snapshot_max, name='configure_snapshot_max'),
    path(
        "snapshots/revert/<int:server_id>/<int:snapshot_id>/",
        views.server_revert_to_specific_snapshot,
        name="server_revert_to_specific_snapshot",
    ),
    path(
        "snapshots/create/<int:server_id>/",
        views.server_create_snapshot_respect_max,
        name="server_create_snapshot_respect_max",
    ),
    path(
        "snapshots/sync/<int:server_id>/",
        views.server_sync_snapshot,
        name="server_sync_snapshot",
    )
]
