from django.urls import path, re_path
from xui.nsxt.views import add_security_tag, remove_security_tag

xui_urlpatterns = [
    path(
        "add_security_tag/<int:server_id>/",
        add_security_tag,
        name="add_security_tag",
    ),
    re_path(
        r"^remove_security_tag/(?P<server_id>\d+)/tag/(?P<tag_name>[\w\-]+)/$",
        remove_security_tag,
        name="remove_security_tag",
    ),
]
