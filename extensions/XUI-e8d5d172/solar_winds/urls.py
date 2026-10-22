from django.urls import path
from xui.solar_winds import views

xui_urlpatterns = [
    # SolarWinds REST connection urls
    path('solarwinds/add_credentials/', views.add_credentials,
        name='add_credentials'),
    path('solarwinds/edit_credentials/', views.edit_credentials,
        name='edit_credentials'),
    path('solarwinds/delete_credentials/',
        views.delete_credentials, name='delete_credentials'),
    path('solarwinds/verify_connection/', views.verify_credentials,
        name='verify_credentials'),

    # SolarWinds server connection urls
    path('solarwinds/add_server_credentials/', views.add_server_credentials,
        name='add_server_credentials'),
    path('solarwinds/install_agent/<int:server_id>', views.install_agent,
        name='install_sam_agent'),
    path('solarwinds/edit_server_credentials/', views.edit_server_credentials,
        name='edit_server_credentials'),
    path('solarwinds/delete_server_credentials/', views.delete_server_credentials,
        name='delete_server_credentials'),
    path('solarwinds/verify_server_connection/', views.verify_server_credentials,
        name='verify_server_credentials'),

]
