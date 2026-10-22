from django.urls import re_path

from xui.jupyter_notebook import views

xui_urlpatterns = [
    re_path(r"^notebook", views.jupyter_notebook_view, name="django_notebook"),
]
