from django.urls import path

from xui.s3_file_manager import views

# One route per surface: the table's JSON source, the dialog dispatcher, the
# action POST target (?action=<name>, see views.ACTIONS), downloads, the
# delete-bucket order, and the admin save. Every view re-checks RBAC.
_PREFIX = "xui/s3_file_manager/<int:resource_id>"

xui_urlpatterns = [
    path(f"{_PREFIX}/objects.json", views.objects_json, name="s3_mgmt_objects_json"),
    path(f"{_PREFIX}/dialog/", views.action_dialog, name="s3_mgmt_dialog"),
    path(f"{_PREFIX}/objects/", views.object_action, name="s3_mgmt_objects"),
    path(f"{_PREFIX}/download/", views.download_item, name="s3_mgmt_download"),
    path(f"{_PREFIX}/bucket/delete/", views.delete_bucket,
         name="s3_mgmt_delete_bucket"),
    path(f"{_PREFIX}/widget/", views.s3_dashboard_widget_browser,
         name="s3_mgmt_widget_browser"),
    path("xui/s3_file_manager/admin/settings/", views.save_admin_settings,
         name="s3_mgmt_admin_settings"),
    path("xui/s3_file_manager/sync-buckets/", views.sync_s3_buckets,
         name="s3_mgmt_sync_buckets"),
]
