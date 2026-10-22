from django.urls import path
from xui.new_relic import views

xui_urlpatterns = [
    path('new_relic/add_credentials/', views.add_credentials,
        name='add_new_relic_credentials'),
    path('new_relic/verify_credentials/', views.verify_new_relic_credentials,
        name='verify_new_relic_credentials'),
    path('new_relic/delete_credentials/', views.delete_new_relic_credentials,
        name='delete_new_relic_credentials'),
    path('new_relic/edit_credentials/', views.edit_new_relic_credentials,
        name='edit_new_relic_credentials'),

    path('new_relic/install_agent/<int:server_id>', views.install_agent,
        name='install_new_relic_agent'),
    path('new_relic/uninstall_agent/<int:server_id>', views.uninstall_agent,
        name='uninstall_new_relic_agent'),
]
