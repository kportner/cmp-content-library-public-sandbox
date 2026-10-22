from django.urls import path
from xui.openshift import views

xui_urlpatterns = [
    path('openshift/add_credentials/', views.add_credentials,
        name='add_openshift_credentials'),
    path('openshift/edit_credentials/', views.edit_openshift_credentials,
        name='edit_openshift_credentials'),
    path('openshift/verify_credentials/', views.verify_credentials,
        name='verify_openshift_credentials'),
    path('openshift/delete_openshift_credentials/', views.delete_credentials,
        name='delete_openshift_credentials'),
]
