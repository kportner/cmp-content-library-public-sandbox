from django.urls import path
from xui.cloud_formation import views

xui_urlpatterns = [
    path(
        "cloud_formation/create/",
        views.create_cft_blueprint,
        name="cloudformation_create",
    ),
    path(
        "cloud_formation/<int:blueprint_id>/edit/",
        views.edit_cft_blueprint,
        name="edit_cft_blueprint",
    ),
    path(
        "cloud_formation/<int:blueprint_id>/delete/",
        views.delete_cft_blueprint,
        name="delete_cft_blueprint",
    ),
    path(
        "cloud_formation/<int:blueprint_id>/sync/",
        views.sync_cft_blueprint,
        name="sync_cft_blueprint",
    ),
    path(
        "cloud_formation/conn_info/create_git_ci/",
        views.create_connection_info,
        name="cft_ci_create",
    ),
    path(
        "cloud_formation/conn_info/<int:ci_id>/edit/",
        views.edit_connectioninfo,
        name="cft_ci_edit",
    ),
    path(
        "cloud_formation/conn_info/<int:ci_id>/delete/",
        views.delete_connectioninfo,
        name="cft_ci_delete",
    ),
]
