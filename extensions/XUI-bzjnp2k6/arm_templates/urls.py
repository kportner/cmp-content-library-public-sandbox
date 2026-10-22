from django.urls import re_path

from xui.arm_templates import views

xui_urlpatterns = [
    re_path(
        r"^arm_templates/create/$",
        views.create_arm_blueprint,
        name="create_arm_blueprint",
    ),
    re_path(
        r"^arm_templates/(?P<blueprint_id>\d+)/edit/$",
        views.edit_arm_blueprint,
        name="edit_arm_blueprint",
    ),
    re_path(
        r"^arm_templates/(?P<blueprint_id>\d+)/delete/$",
        views.delete_arm_blueprint,
        name="delete_arm_blueprint",
    ),
    re_path(
        r"^arm_templates/(?P<blueprint_id>\d+)/sync/$",
        views.sync_arm_blueprint,
        name="sync_arm_blueprint",
    ),
    re_path(
        r"^arm_templates/conn_info/create_git_ci/$",
        views.create_connection_info,
        name="arm_ci_create",
    ),
    re_path(
        r"^arm_templates/conn_info/(?P<ci_id>\d+)/edit/$",
        views.edit_connectioninfo,
        name="arm_ci_edit",
    ),
    re_path(
        r"^arm_templates/conn_info/(?P<ci_id>\d+)/delete/$",
        views.delete_connectioninfo,
        name="arm_ci_delete",
    ),
]
