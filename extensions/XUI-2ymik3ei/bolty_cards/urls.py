from django.urls import path
from xui.bolty_cards import views

xui_urlpatterns = [
    path('bolty_cards/get_canvas/', views.get_canvas, name='get_canvas'),
]