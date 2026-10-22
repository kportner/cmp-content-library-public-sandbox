from django.urls import path
from xui.openstack_reports.views import (
    get_utilization_report_data
)

xui_urlpatterns = [
    path("xui/openstack_reports/get_utilization_report_data/",
        get_utilization_report_data, name="get_utilization_report_data"),
]
