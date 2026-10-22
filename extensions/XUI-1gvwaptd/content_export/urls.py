from django.urls import path, re_path
from xui.content_export import views

xui_urlpatterns = [
    path('content_export/export_content_list/', views.export_content_list,
        name='export_content_list'),
    re_path(r'content_export/export_content_edit/(?P<id>\d+)/(?P<collections>[\w-]+)/$', views.export_content_edit,
        name='export_content_edit')
]