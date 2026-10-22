from django.urls import re_path
from xui.git_management import views


xui_urlpatterns = [
    re_path(
        r"^git_management/git_config/(?P<config_type>.*)/create/$",
        views.create_git_config,
        name="git_config_create",
    ),
    re_path(
        r"^git_management/git_config/(?P<config_type>.*)/edit/(?P<config_name>.*)/$",
        views.edit_git_config,
        name="git_config_edit",
    ),
    re_path(
        r"^git_management/git_config/(?P<config_type>.*)/delete/(?P<config_name>.*)/$",
        views.delete_git_config,
        name="git_config_delete",
    ),
    re_path(
        r"^git_management/commits/(?P<content_type>.*)/(?P<content_id>.*)/$",
        views.create_git_commit,
        name="git_commit_create",
    ),
    re_path(
        r"^git_management/commits/(?P<content_type>.*)/export_multiple$",
        views.export_multiple,
        name="export_multiple",
    ),
]

