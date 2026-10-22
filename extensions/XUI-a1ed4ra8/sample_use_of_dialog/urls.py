from django.urls import path
from xui.sample_use_of_dialog import views

xui_urlpatterns = [
    path('add_sample_message/<int:server_id>/', views.add_sample_message,
        name='add_sample_message'),
    path('delete_sample_message/<int:server_id>/message/<int:message_id>/',
        views.delete_sample_message, name='delete_sample_message'),
]
