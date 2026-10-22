from django.urls import path, re_path
from xui.veeam import views

xui_urlpatterns = [
    path('veeam/install_agent/<int:server_id>/',
        views.install_agent,
        name='install_agent'),
    path('veeam/refresh_agent/<int:server_id>/',
        views.refresh_agent,
        name='refresh_agent'),
    path('veeam/take_backup/<int:server_id>/',
        views.take_backup,
        name='take_backup'),

    # restore a backup
    re_path(r'^veeam/restore_backup/(?P<server_id>\d+)/(?P<restore_point_href>[\w-]+)/$',
        views.restore_backup,
        name='restore_backup'),
    # restore a backup to cloud
    re_path(r'^veeam/restore_backup_to_cloud/(?P<backup_name>.*)/$',
        views.restore_backup_to_cloud,
        name='restore_to_cloud'),

    # restore backup to ec2
    re_path(r'^veeam/restore_backup_to_ec2_cloud/(?P<backup_name>.*)/$',
        views.restore_backup_to_ec2_cloud,
        name='restore_to_ec2_cloud'),
    path('veeam/get_aws_vpc/',
        views.get_aws_vpc,
        name='get_aws_vpc'),
    path('veeam/get_aws_security_groups/',
        views.get_aws_security_groups,
        name='get_aws_security_groups'),
    path('veeam/get_aws_availability_zones/',
        views.get_aws_availability_zones,
        name='get_aws_availability_zones'),

    # VEEAM ConnectionInfo urls
    path('veeam/create_endpoint/', views.edit_veeam_endpoint,
        name='create_veeam_endpoint'),
    path('veeam/edit_endpoint/<int:endpoint_id>/',
        views.edit_veeam_endpoint, name='edit_veeam_endpoint'),
    path('veeam/delete_endpoint/', views.delete_veeam_endpoint,
        name='delete_veeam_endpoint'),
    path('veeam/verify_endpoint/', views.verify_veeam_endpoint,
        name='verify_veeam_endpoint'),
]
