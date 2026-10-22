import json

from django.templatetags.static import static
from django.contrib import messages

from django.http import HttpResponse, JsonResponse
from django.core.management import call_command
from django.shortcuts import render, get_object_or_404
from settings import PROSERV_DIR, DEBUG
from extensions.views import (
    admin_extension,
    tab_extension,
    dashboard_extension,
    TabExtensionDelegate
)
from resourcehandlers.models import ResourceHandler
from resourcehandlers.azure_arm.models import AzureARMHandler
from resourcehandlers.gcp.models import GCPHandler
from utilities.logger import ThreadLogger
from xui.kumo_integration_kit.utils import (
    get_currency,
    get_credentials_from_db,
    get_adapter_id,
    ApiResponse,
    get_custom_setting,
    update_custom_setting,
    _update_or_create_recurring_job,
    _update_or_create_rh_currency_job,
    get_default_rh_currency,
    get_api_validation,
    is_aws_based_handler
)
from xui.kumo_integration_kit.apis.dashboard_widget import (
    get_cost_summary_widget_data,
    get_expensive_services_widget_data,
    get_cost_efficiecy_widget_data
)
from xui.kumo_integration_kit.apis.admin import (
    get_widget_currency,
)
from utilities.models import ConnectionInfo
from infrastructure.models import Server
from django.forms.models import model_to_dict
from django.core.serializers.json import DjangoJSONEncoder
from jobs.models import RecurringJob

try:
    from xui.kumo_integration_kit import CURRENT_VERSION
except ImportError:
    CURRENT_VERSION = ''

logger = ThreadLogger(__name__)

class ResourceHandlerTabBaseClass(TabExtensionDelegate):
    """
    To control the visibility of the resource handler tabs
    """
    def should_display(self):
        rh = self.instance.cast()
        ci = ConnectionInfo.objects.filter(name__iexact='Kumolus Kit Creds')

        if ci:
            if ci.first().ip and ci.first().password:
                return is_aws_based_handler(rh) \
                    or isinstance(rh, AzureARMHandler) \
                    or isinstance(rh, GCPHandler)
        else:
            return False


class ComplianceRhTabBaseClass(TabExtensionDelegate):
    """
    To control the visibility of the resource handler tabs
    """
    def should_display(self):
        rh = self.instance.cast()
        ci = ConnectionInfo.objects.filter(name__iexact='Kumolus Kit Creds')

        if ci:
            if ci.first().ip and ci.first().password:
                return is_aws_based_handler(rh) \
                    or isinstance(rh, AzureARMHandler) 
        else:
            return False


class ServerTabBaseClass(TabExtensionDelegate):
    """
    To control the visibility of the server tabs
    """
    def should_display(self):
        try:
            server_instance = self.instance.resource_handler.type_slug
            if (
                server_instance == "aws"
                or server_instance == "awsjit"
                or server_instance == "azure_arm"
            ):
                return True
        except:
            pass
        return False


class HandlerInitializer:
    """
    To compute the initial variables when a resource handler tab is shown.
    """
    def __init__(self, resource_handler) -> None:
        self.resource_handler = resource_handler

    def get_handler(self):
        return get_object_or_404(ResourceHandler, pk=int(self.resource_handler)).cast()

    def get_handler_type(self):
        handler_which_type = self.handler.resource_technology.type_slug
        if (
            handler_which_type == "aws"
            or handler_which_type == "awsjit"
        ):
            return "AWS"
        elif handler_which_type == "azure_arm":
            return "Azure"    
        else:
            return handler_which_type.upper()

    def get_provider_account_id(self):
        aws_adapter, azure_adapters, gcp_adapters = get_adapter_id()
        provider_account_id = ""
        if self.handler_type == "AWS":
            provider_account_id = str(self.handler.account_id)
        elif self.handler_type == "GCP":
            provider_account_id = list(self.handler.gcp_projects.filter(
                                       imported=True).values_list(
                                       "gcp_id", flat=True))
            provider_account_id = list(set(provider_account_id) & set(gcp_adapters.keys()))
            if not provider_account_id:
                return []
        elif self.handler_type == "Azure":
            provider_account_id = str(self.handler.serviceaccount)
        return provider_account_id

    def get_rh_currency(self):
        # rh_currency = get_currency(self.provider_account_id, self.handler)
        return get_default_rh_currency(self.handler)

    def get_customer_credentials(self):
        return get_credentials_from_db()

    def get_kumo_adapter_id(self):
        # if self.provider_account_id and self.KUMO_WEB_HOST:
        #     if self.handler_type in ["AWS", "Azure", "GCP"]:
        #         if validate_api(self.KUMO_API_KEY):
        #             kumo_adapter_id = get_adapter_id(self.provider_account_id)
        #             return kumo_adapter_id
        return ""

    def initialize(self):
        self.handler = self.get_handler()
        self.handler_type = self.get_handler_type()
        self.provider_account_id = self.get_provider_account_id()
        self.KUMO_WEB_HOST, self.KUMO_API_KEY = self.get_customer_credentials()
        self.kumo_adapter_id = self.get_kumo_adapter_id()
        self.currency = self.get_rh_currency()
        self.validation = True if self.kumo_adapter_id else False
        return self


@tab_extension(model=ResourceHandler, title="Spend",
               description='Cost details of Resource Handler',
               delegate=ResourceHandlerTabBaseClass)
def display_a_tab(request, resource_handler):
    """
    To display Spend tab in resource handler

    Args:
        request (http request)
        resource_handler (int): selected resource handlers id

    Returns:
        html: renders html file python dictionary with various required parameters
    """
    rh = HandlerInitializer(resource_handler=resource_handler).initialize()
    return render(request, 'kumo_integration_kit/templates/spendings.html',
                  {'handler_type': rh.handler_type,
                   'rh_id': rh.handler.id,
                   'acc_currency': rh.currency,
                   'handler_normal_id': rh.provider_account_id,
                   'normal_adapter_id': rh.kumo_adapter_id,
                   'KUMO_WEB_HOST': rh.KUMO_WEB_HOST,
                   'validation': get_api_validation(request)})


@tab_extension(model=ResourceHandler, title="Efficiency",
               description='Services details of Resource Handler',
               delegate=ResourceHandlerTabBaseClass)
def display_b_tab(request, resource_handler):
    """
    To display Efficiency tab in resource handler

    Args:
        request (http request)
        resource_handler (int): selected resource handlers id

    Returns:
        html: renders html file python dictionary with various required parameters
    """
    rh = HandlerInitializer(resource_handler=resource_handler).initialize()
    return render(request, 'kumo_integration_kit/templates/efficiency.html',
                  {'handler_type': rh.handler_type,
                   'rh_id': rh.handler.id,
                   'acc_currency': "USD",
                   'handler_normal_id': rh.provider_account_id,
                   'normal_adapter_id': rh.kumo_adapter_id,
                   'KUMO_WEB_HOST': rh.KUMO_WEB_HOST,
                   'validation': get_api_validation(request)})


@tab_extension(model=ResourceHandler, title="Compliance",
               description='Compliance details of Resource Handler',
               delegate=ComplianceRhTabBaseClass)
def display_c_tab(request, resource_handler):
    """
    To display Compliance tab in resource handler

    Args:
        request (http request)
        resource_handler (int): selected resource handlers id

    Returns:
        html: renders html file python dictionary with various required parameters
    """
    rh = HandlerInitializer(resource_handler=resource_handler).initialize()
    return render(request, 'kumo_integration_kit/templates/compliance.html',
                  {'handler_type': rh.handler_type,
                   'rh_id': rh.handler.id,
                   'acc_currency': rh.currency,
                   'handler_normal_id': rh.provider_account_id,
                   'normal_adapter_id': rh.kumo_adapter_id,
                   'KUMO_WEB_HOST': rh.KUMO_WEB_HOST,
                   'validation': get_api_validation(request)})


@tab_extension(
    title='Costs',  # `title` is what end users see on the tab
    description='Server related cost details',
    model=Server, # Required: the model this extension is for
    delegate=ServerTabBaseClass
)
def display_server(request, obj_id):
    """
    To display the detailed billing data on server tab.
    """
    # Instantiate the server instance using the ID passed in.
    server = Server.objects.get(id=obj_id)
    rh = HandlerInitializer(resource_handler=server.resource_handler.id).initialize()
    server_data = {
        'resource_handler_svr_id': server.resource_handler_svr_id,
        'id': server.id,
        'type_slug': server.resource_handler.resource_technology.type_slug,
        'obj_id': obj_id,
        'acc_currency': rh.currency,
        'validation': get_api_validation(request)
    }

    rightsizing_docs_url = get_custom_setting("documentation_link") \
                        or get_custom_setting("default_documentation_link")

    # In case the settings are not configured, we include a static link to the documentation.
    # Even though it is not ideal, it is better than throwing an error
    if not rightsizing_docs_url:
        rightsizing_docs_url = \
            "https://docs.cloudbolt.io/articles/#!cloudbolt-csmp-latest/right-sizing-in-cloudbolt-csmp"
        logger.warning("No documentation link found in settings. Using default link: %s",
                       rightsizing_docs_url)

    json_parsed_data = json.dumps(server_data)
    return render(request, 'kumo_integration_kit/templates/server_cost.html',
                  dict(SERVER=json_parsed_data, rightsizing_docs_url=rightsizing_docs_url))


@admin_extension(title="Cost and Security Management",
                 description="Initial configuration setting")
def display_admin(request, **kwargs):
    """
    To show the Admin tab in Admin section of CMP

    Args:
        request (http request)

    Returns:
        html: renders admin.html file
    """
    rj_status, rj_id = _update_or_create_recurring_job()
    rh_currency_rj_status, rh_currency_rj_id \
        = _update_or_create_rh_currency_job()
    host, secret = get_credentials_from_db()
    rightsizing_docs_url = get_custom_setting("documentation_link") \
                        or get_custom_setting("default_documentation_link")

    return render(request, 'kumo_integration_kit/templates/admin.html',
                  context={'docstring': 'CSMP integration setup',
                           'current_version': CURRENT_VERSION,
                           'rj_status': rj_status, 'rj_id': rj_id,
                           'rh_currency_rj_status': rh_currency_rj_status,
                           'rh_currency_rj_id': rh_currency_rj_id,
                           'domain': host,
                           'rightsizing_docs_url': rightsizing_docs_url})


@dashboard_extension()
def cost_summary(request):
    """
    Describe the extension here or using the `description` kwarg to the
    decorator. This text is for admins and is displayed in tooltips on the
    Extensions Management admin page.
    """
    piechart_data, barchart_data, barchart_series_data, \
        piechart_series_data, message_status, job_id, first_run, \
        last_job_status = get_cost_summary_widget_data()
    widget_currency = get_widget_currency()
    return render(request, 'kumo_integration_kit/templates/widget_cost_summary.html', {
        'piechart_data': json.dumps(piechart_data),
        'barchart_data': json.dumps(barchart_data),
        'barchart_series_data': json.dumps(barchart_series_data),
        'piechart_series_data': json.dumps(piechart_series_data),
        'message_status': message_status,
        'job_id': job_id,
        "widget_currency": widget_currency,
        "first_run": first_run,
        "last_job_status": last_job_status,
    })


@dashboard_extension()
def expensive_services(request):
    """
    Describe the extension here or using the `description` kwarg to the
    decorator. This text is for admins and is displayed in tooltips on the
    Extensions Mgmt admin page.
    """
    response_data, barchart_series_data, message_status, job_id, first_run, \
    last_job_status = get_expensive_services_widget_data()
    widget_currency = get_widget_currency()
    return render(request, 'kumo_integration_kit/templates/widget_expensive_services.html', {
        "status": True,
        "response_data": json.dumps(response_data),
        "barchart_series_data": json.dumps(barchart_series_data),
        "message_status": message_status,
        "job_id": job_id,
        "widget_currency": widget_currency,
        "first_run": first_run,
        "last_job_status": last_job_status,
    })


@dashboard_extension()
def cost_efficiency(request):
    """
    Describe the extension here or using the `description` kwarg to the
    decorator. This text is for admins and is displayed in tooltips on the
    Extensions Mgmt admin page.
    """
    total_potential_benefits, potential_data, benefits_across_rh, message_status, job_id, \
    first_run, last_job_status = get_cost_efficiecy_widget_data()
    widget_currency = get_widget_currency()
    return render(request, 'kumo_integration_kit/templates/widget_cost_efficiency.html', {
        "total_potential_benefits": "{0:,.1f}".format(total_potential_benefits),
        "potential_data": json.dumps(potential_data),
        "benefits_across_rh": json.dumps(benefits_across_rh),
        "message_status": message_status,
        "job_id": job_id,
        "widget_currency": widget_currency,
        "first_run": first_run,
        "last_job_status": last_job_status,
        })


@dashboard_extension()
def spend_details(request):
    """
    Describe the extension here or using the `description` kwarg to the
    decorator. This text is for admins and is displayed in tooltips on the
    Extensions Mgmt admin page.
    """
    widget_currency = get_widget_currency()
    recurring_job = RecurringJob.objects.filter(name__icontains="CSMP Dashboard Widget Data Caching")
    job_id = recurring_job.first().id if recurring_job else None

    return render(request, 'kumo_integration_kit/templates/widget_spend_details.html', {
        "widget_currency": widget_currency,
        "job_id": job_id
    })


@dashboard_extension()
def compliance_summary(request):
    """
    Describe the extension here or using the `description` kwarg to the
    decorator. This text is for admins and is displayed in tooltips on the
    Extensions Mgmt admin page.
    """
    resource_handlers = ResourceHandler.objects.all()
    recurring_job = RecurringJob.objects.filter(name__icontains="CSMP Dashboard Widget Data Caching")
    job_id = recurring_job.first().id if recurring_job else None

    return render(request, 'kumo_integration_kit/templates/widget_compliance_summary.html', {
        "resource_handlers": resource_handlers,
        "job_id": job_id
    })
