from django.urls import path
from xui.tintri import views

xui_urlpatterns = [
    # ConnectionInfo urls
    path('tintri/create_endpoint/', views.edit_tintri_endpoint,
        name='create_tintri_endpoint'),
    path('tintri/edit_endpoint/<int:endpoint_id>/',
        views.edit_tintri_endpoint, name='edit_tintri_endpoint'),
    path('tintri/delete_endpoint/', views.delete_tintri_endpoint,
        name='delete_tintri_endpoint'),
    path('tintri/verify_endpoint/', views.verify_tintri_endpoint,
        name='verify_tintri_endpoint'),
]
