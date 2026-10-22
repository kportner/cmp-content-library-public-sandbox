from django.urls import path
from . import views

xui_urlpatterns = [
    path("mfa/configure/", views.configure_mfa, name="configure_mfa"),
    path(
        "mfa/verify/",
        views.verify_second_factor_totp,
        name="verify_second_factor_totp",
    ),
    path("mfa/disable/", views.disable_mfa, name="mfa_disable"),
    path("mfa/enable/", views.enable_mfa, name="mfa_enable"),
    path("mfa/qr_code/", views.mfa_qr_code, name="mfa_qr_code"),
    path(
        "mfa/users/json/",
        views.MFAUserListJSONView.as_view(),
        name="mfa_table_json",
    ),
]
