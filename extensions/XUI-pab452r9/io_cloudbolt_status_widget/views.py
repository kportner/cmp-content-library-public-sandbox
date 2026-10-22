from extensions.views import dashboard_extension
from health_check.views import ServiceStatusView


@dashboard_extension(title="System Status", description="System Status Widget")
def widget_view(request):
    ssv = ServiceStatusView(request=request)
    ssv.template_name = "io_cloudbolt_status_widget/templates/index.html"
    return ssv.get(request)
