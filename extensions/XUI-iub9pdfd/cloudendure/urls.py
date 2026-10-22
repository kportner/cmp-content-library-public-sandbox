from django.urls import path, re_path
from xui.cloudendure import views

xui_urlpatterns = [
    # CloudEndure connection urls
    path('cloudendure/add_cloudendure_endpoint/', views.add_cloudendure_endpoint,
        name='add_cloudendure_endpoint'),
    path('cloudendure/edit_cloudendure_endpoint/', views.edit_cloudendure_endpoint,
        name='edit_cloudendure_endpoint'),
    path('cloudendure/delete_cloudendure_endpoint/', views.delete_cloudendure_endpoint,
        name='delete_cloudendure_endpoint'),
    path('cloudendure/verify_cloudendure_connection/', views.verify_cloudendure_connection,
        name='verify_cloudendure_connection'),
    path('cloudendure/install_cloudendure_agent/<int:server_id>', views.install_cloudendure_agent,
        name='install_cloudendure_agent'),

    # CloudEndure machine actions urls
    re_path(r'^cloudendure/cloudendure_machine_actions/(?P<server_id>\d+)/(?P<action>[\w-]+)/$', views.cloudendure_machine_actions,
        name='cloudendure_machine_actions'),


    # CloudEndure machine migration
    re_path(r'^cloudendure/cloudendure_machine_migration/(?P<project_id>[\w-]+)/(?P<machine_id>[\w-]+)/$', views.cloudendure_machine_migration,
        name='cloudendure_machine_migration'),
    # cloudendure projects
    path('cloudendure/create_cloudendure_project/', views.create_cloudendure_project,
        name='create_cloudendure_project'),

]
