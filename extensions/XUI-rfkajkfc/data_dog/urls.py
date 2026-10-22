from django.urls import path
from xui.data_dog import views

xui_urlpatterns = [
    # DataDog connection urls
    path('datadog/add_credentials/', views.add_credentials,
        name='add_data_dog_credentials'),
    path('datadog/edit_credentials/',views.edit_credentials, 
        name='edit_data_dog_credentials'),
    path('datadog/delete_credentials/', views.delete_credentials,
        name='delete_data_dog_credentials'),
    path('datadog/verify_credentials/', views.verify_credentials,
        name='verify_data_dog_credentials'),
    path('datadog/install_agent/<int:server_id>/', views.install_agent,
        name='install_data_dog_agent'),
    path('datadog/uninstall_datadog_agent/<int:server_id>/', views.uninstall_agent,
        name='uninstall_datadog_agent'),
]
