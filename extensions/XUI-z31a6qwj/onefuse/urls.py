from django.urls import re_path
from xui.onefuse import views

xui_urlpatterns = [
    re_path(r'^onefuse_admin', views.onefuse_admin, name='onefuse_admin'),
    re_path(r'^setup_onefuse', views.setup_onefuse, name='setup_onefuse')
]