import json
import traceback
import os
import threading

from resourcehandlers.models import ResourceHandler
from xui.kumo_integration_kit import utils
from xui.kumo_integration_kit.utils import (
    ApiResponse,
    update_custom_setting,
    get_default_rh_currency,
    get_api_validation,
    toggle_api_validation_status
)
from utilities.decorators import json_view
from utilities.permissions import cbadmin_required
from utilities.models import ConnectionInfo
from resourcehandlers.models import ResourceHandler
from infrastructure.models import CustomField
from infrastructure.models import Environment
from jobs.models import RecurringJob
from tags.models import CloudBoltTag
from django.http import HttpResponse, JsonResponse
from django.forms.models import model_to_dict
from utilities.logger import ThreadLogger


logger = ThreadLogger(__name__)

class KumoKit(object):
    """
    Database object for CSMP credentials
    """
    def __init__(self):
        ci = ConnectionInfo.objects.filter(
            name__iexact='Kumolus Kit Creds').first()

        if ci:
            self.connection_info = ci
            self.name = ci.name
            self.protocol = ci.protocol
            self.ip = ci.ip
            self.port = ci.port
            self.username = ci.username
            self.password = ci.password
            self.headers = ci.headers
            self.description = ci.description
        else:
            self.name = ""
            self.connection_info = ConnectionInfo()

    def save_description(self, ci_des):
        ci_obj = self.connection_info
        ci_obj.description = ci_des
        ci_obj.save()

    def save_credentials(self, *args, **kwargs):
        user_entry_object = ConnectionInfo(*args, **kwargs)
        kituser = user_entry_object.save()
        return kituser

    def update_credentials(self, *args, **kwargs):
        ip, password = kwargs["ip"], kwargs["password"]

        ci = ConnectionInfo.objects.filter(
            name__iexact='Kumolus Kit Creds').update(ip=ip, password=password)
        return ci

    def get_credentials(self):
        return self.connection_info


@json_view
@cbadmin_required
def validate_creds(request):
    return JsonResponse({'result': get_api_validation(request)})


def create_custom_fields():
    CustomField.objects.get_or_create(
        name='add_recurring_job',
        defaults={'type': 'BOOL',
                  'label': 'Add Recurring Job',
                  'description': 'Adding recurring job to store data for dashboard widgets'
                  })


@json_view
@cbadmin_required
def save_creds(request):
    """ To save the credentials

    Args:
        request (http request): This function will save the credentials
        entered by the customer after successful validation in Cloudbolt database.
    """
    payload = json.loads(request.POST.get('body'))
    web_host = payload['web_host']
    api_key = payload['api_key']

    try:
        kumokit = KumoKit()
        if hasattr(kumokit, "name") and hasattr(kumokit, "ip") and hasattr(kumokit, "password"):
            if kumokit.ip == web_host.split("://")[1] and kumokit.password == api_key:
                status = True
                exists = True

                return JsonResponse({'result': status, 'exists': exists})
            else:
                kituser = kumokit.update_credentials(
                    ip=web_host.split("://")[1],
                    password=api_key)

                status = True
                changed = True

                return JsonResponse({'result': status, 'changed': changed})
        else:
            # create_custom_fields()
            kituser = kumokit.save_credentials(
                name="Kumolus Kit Creds",
                protocol=web_host.split("://")[0],
                ip=web_host.split("://")[1],
                password=api_key)

            # CloudBoltTag.objects.get_or_create(name="remove_rj", model_name="connectioninfo")
            # kituser.labels.add(CloudBoltTag.objects.get(name="remove_rj"))

        status = True

    except:
        traceback.print_exc()
        status = False

    return JsonResponse({'result': status})


@json_view
@cbadmin_required
def get_creds(request):
    """ To fetch the credentials

    Args:
        request (http request): This function will fetch the credentials
        stored by the customer in Cloudbolt database.
    """
    creds = {}
    rj_obj = RecurringJob.objects.filter(name="CSMP Dashboard Widget Data Caching").first()
    rj_currency_rj_obj = RecurringJob.objects.filter(name="CSMP Resource Handler Data Caching").first()

    try:
        kumokit = KumoKit()
        if hasattr(kumokit, "name"):
            creds = {
                'web_host': kumokit.ip,
                'api_key': kumokit.password,
                'rj_status': rj_obj.enabled,
                'rj_currency_rj_status': rj_currency_rj_obj.enabled
            }

            status = True
        else:
            status = False

    except:
        traceback.print_exc()
        status = False

    return JsonResponse({'result': status, 'creds': creds})


@json_view
@cbadmin_required
def get_rh_list(request):
    """ To fetch the list of Resource Handlers

    Args:
        request (http request): This function will fetch the resource handlers
        that already added by the customer in Cloudbolt account.
    """
    rh_list = ResourceHandler.objects.all()
    payload = json.loads(request.POST.get('body'))
    matched_rh_list = []
    response_cc = {}
    response = {}
    set_curr = ""

    try:
        kumokit = KumoKit()

        if hasattr(kumokit, "description"):
            if kumokit.description:
                kumo_des = json.loads(kumokit.description)
                if "default_currency" in kumo_des.keys():
                    set_curr = kumo_des["default_currency"]

        if hasattr(kumokit, "name"):
            if not get_api_validation(request):
                return JsonResponse({
                    'result': [],
                    'error_message': 'Invalid credentials for API access' })

            aws_adapter, azure_adapters, gcp_adapters = utils.get_adapter_id()
            matched_rh_list = []
            available_cc = []
            # common_accounts = []
            # threads = []
            # accounts_with_currency = {}
            response_cc = ApiResponse(payload,
                                      'currency_conversion').fetch_response()
            _status, response = ApiResponse.check_response(response_cc)
            if _status:
                if response != "no_data_found":
                    available_cc = response["currency_configurations"]
            else:
                raise Exception(response)

            for rh in rh_list:
                rh_dict = {}
                rh_dict["id"] = rh.cast().__dict__["id"]
                rh_dict["name"] = rh.cast().__dict__["name"]
                rh_dict["description"] = rh.cast().__dict__["description"]
                handler_which_type = rh.cast().resource_technology.type_slug
                if (
                    handler_which_type == "aws"
                    or handler_which_type == "awsjit"
                ):
                    rh_dict["th_type"] = "AWS"
                elif handler_which_type == "azure_arm":
                    rh_dict["th_type"] = "Azure"    
                else:
                    rh_dict["th_type"] = handler_which_type.upper()
                
                rh_dict["available_cc"] = None
                rh_dict["set_currency"] = set_curr

                if rh_dict["th_type"] == "AWS":
                    if rh.cast().__dict__["account_id"] in aws_adapter:
                        rh_dict["provider_id"] = rh.cast().__dict__["account_id"]
                        rh_dict["default_currency"] = get_default_rh_currency(rh)
                        for curr_convs in available_cc:
                            if curr_convs["cloud_provider_currency"] == rh_dict["default_currency"] \
                                and curr_convs["default_currency"] == set_curr \
                                    and curr_convs["provider"] == "AWS":
                                rh_dict["available_cc"] = curr_convs
                        matched_rh_list.append(rh_dict)

                elif rh_dict["th_type"] == "GCP":
                    imported_projects_list = list(rh.cast().gcp_projects.filter(
                                                    imported=True).values_list(
                                                    "gcp_id", flat=True))
                    common_projects_list = list(set(imported_projects_list) & set(gcp_adapters.keys()))
                    if common_projects_list:
                        rh_dict["provider_id"] = common_projects_list
                        rh_dict["default_currency"] = get_default_rh_currency(rh)
                        for curr_convs in available_cc:
                            if curr_convs["cloud_provider_currency"] == rh_dict["default_currency"] \
                                and curr_convs["default_currency"] == set_curr \
                                    and curr_convs["provider"] == "GCP":
                                rh_dict["available_cc"] = curr_convs
                        matched_rh_list.append(rh_dict)

                elif rh_dict["th_type"] == "Azure":
                    if rh.cast().__dict__["serviceaccount"] in azure_adapters:
                        rh_dict["provider_id"] = rh.cast().__dict__["serviceaccount"]
                        rh_dict["default_currency"] = get_default_rh_currency(rh)
                        for curr_convs in available_cc:
                            if curr_convs["cloud_provider_currency"] == rh_dict["default_currency"] \
                                and curr_convs["default_currency"] == set_curr \
                                    and curr_convs["provider"] == "Azure":
                                rh_dict["available_cc"] = curr_convs
                        matched_rh_list.append(rh_dict)

    except:
        logger.warning(traceback.print_exc())
        toggle_api_validation_status(False)
        return JsonResponse({
            'result': [],
            'error_message': response if response else {}
        })

    return JsonResponse({'result': matched_rh_list})


@json_view
@cbadmin_required
def save_kumo_data(request):
    """ To save Billing and Normal account Ids

    Args:
        request (http request): This function will store the billing and
        normal ids entered by user in Cludbolt Database.
    """
    payload = json.loads(request.POST.get('body'))
    existing_data = {}

    try:
        kumokit = KumoKit()
        if hasattr(kumokit, "name"):
            if kumokit.headers:
                existing_data = json.loads(kumokit.headers)
                existing_data[payload['rhid']] = {
                    "billing_account": payload['billing_account'],
                    "normal_account": payload['normal_account'],
                }
            else:
                existing_data[payload['rhid']] = {
                    "billing_account": payload['billing_account'],
                    "normal_account": payload['normal_account'],
                }

            ConnectionInfo.objects.filter(name__iexact='Kumolus Kit Creds').update(
                headers=json.dumps(existing_data))
            status = True
        else:
            status = False

    except:
        traceback.print_exc()
        status = False

    return JsonResponse({'result': status})


@json_view
def validate_api_token(request):
    """
    To validate the CSMP account's API key entered by the customer

    Args:
        request (http request): reuest having api key as params

    Returns:
        dict: having message for status of the validation
    """
    payload = json.loads(request.body)

    kumokit = KumoKit()
    if hasattr(kumokit, "name"):
        payload['api_key'] = f"{kumokit.password}"

    response = ApiResponse(payload, 'validate_api_token').fetch_response()
    _status, response = ApiResponse.check_response(response)
    if _status:
        return JsonResponse({'result': response})
    
    return JsonResponse({'result': {}})


@json_view
def get_config(request):
    """
    To fetch the CSMP account's config for service adviser
    set by the customer

    Args:
        request (http request): None

    Returns:
        dict: having response with configuration data
    """
    payload = {}
    response = {}

    response = ApiResponse(payload, 'get_config').fetch_response()
    _status, response = ApiResponse.check_response(response)
    if not _status:
        return JsonResponse({'result': response})

    kumokit = KumoKit()

    if hasattr(kumokit, "description") and response:
        if kumokit.description:
            kumo_des = json.loads(kumokit.description)
            if "default_currency" in kumo_des.keys():
                if kumo_des["default_currency"]:
                    response.update({
                        "default_currency": kumo_des["default_currency"]
                    })

    return JsonResponse({'result': response})


@json_view
def set_config(request):
    """
    To set the CSMP account's config for service adviser
    set by the customer

    Args:
        request (http request): request with config data

    Returns:
        dict: having response with configuration data
    """
    payload = json.loads(request.POST.get('body'))

    response = ApiResponse(payload, 'get_config',
                           request_type="POST").fetch_response()
    _status, response = ApiResponse.check_response(response)
    if _status:
        return JsonResponse({'result': response})
    else:
        return JsonResponse({'result': {}})


def change_recurring_job_status(request):
    """
    To set the set recurring job for dashboard widgets
    by the customer

    Args:
        request (http request): request with config data

    Returns:
        dict: having response with configuration data
    """
    rj_obj = RecurringJob.objects.filter(
                name="CSMP Dashboard Widget Data Caching").first()
    rj_obj.enabled = not rj_obj.enabled
    rj_obj.save()

    return JsonResponse({'result': bool(rj_obj)})


def change_rh_currency_rj_status(request):
    """
    To set the set recurring job for caching currecny
    for dashboard widgets by the customer

    Args:
        request (http request): request with config data

    Returns:
        dict: having response with configuration data
    """
    rj_obj = RecurringJob.objects.filter(
                name="CSMP Resource Handler Data Caching").first()
    rj_obj.enabled = not rj_obj.enabled
    rj_obj.save()

    return JsonResponse({'result': bool(rj_obj)})


@json_view
def all_currency_conversion(request):
    """
    To interact with CSMP account's currency conversion
    config set by the customer

    Args:
        request (http request): request

    Returns:
        dict: having response with currency conversion
        configuration data
    """
    payload = json.loads(request.POST.get('body'))
    if payload["call_type"] == "PATCH":
        response = ApiResponse(payload, 'currency_conversion',
                               request_type="PATCH").fetch_response()
    elif payload["call_type"] == "DELETE":
        response = ApiResponse(payload, 'currency_conversion',
                               request_type="DELETE").fetch_response()
    elif payload["call_type"] == "POST":
        response = ApiResponse(payload, 'currency_conversion',
                               request_type="POST").fetch_response()
    _status, response = ApiResponse.check_response(response)
    if _status:
        return JsonResponse({'result': response})
    else:
        return JsonResponse({'result': {}})
        


@json_view
def save_preferred_currency(request):
    """
    To interact with CSMP account's currency conversion
    config set by the customer

    Args:
        request (http request): request

    Returns:
        dict: having response with currency conversion
        configuration data
    """
    payload = json.loads(request.GET.get('body'))
    response = {}
    # response = ApiResponse(payload, 'update_currency_conversion').fetch_response()
    kumokit = KumoKit()

    if hasattr(kumokit, "description"):
        if kumokit.description:
            kumo_des = json.loads(kumokit.description)
            kumo_des["default_currency"] = payload["default_currency"]
            kumokit.save_description(json.dumps(kumo_des))
        else:
            kumokit.save_description(json.dumps(payload))

    response.update({
        "default_currency": payload["default_currency"]
    })
    return JsonResponse({'result': response})


@json_view
def set_currency_unified_status(request):
    """
    To interact with Connection Info for Kumo
    Integration Kit's description to store currency
    unified for dashboard widgets or not

    Args:
        request (http request): request

    Returns:
        dict: having response with currency conversion
        configuration data
    """
    payload = json.loads(request.POST.get('body'))
    response = {}

    kumokit = KumoKit()

    if hasattr(kumokit, "description"):
        if kumokit.description:
            kumo_des = json.loads(kumokit.description)
            kumo_des["currency_unified"] = payload["currency_unified"]
            kumokit.save_description(json.dumps(kumo_des))
        else:
            kumokit.save_description(json.dumps(payload))

    response.update({
        "currency_unified": payload["currency_unified"]
    })
    return JsonResponse({'result': response})


def get_widget_currency():
    kumokit = KumoKit()

    if hasattr(kumokit, "description"):
        if kumokit.description:
            kumo_des = json.loads(kumokit.description)
            if "default_currency" in kumo_des.keys():
                if "currency_unified" in kumo_des.keys():
                    if kumo_des["currency_unified"]:
                        return kumo_des["default_currency"]
    return ""

def save_documentation_link(request):
    """
    By default, the Cost tab documentation link is set to CloudBolt's documentation,
    but Admins can change it to point to their own documentation.
    If they do, this function will save the new link in this ui's settings file.

    Args:
        request (http request)

    """
    if request.method == 'POST':
        data = request.POST
        documentation_link = data['documentation_link']

        if documentation_link and documentation_link[0:4] != 'http':
            documentation_link = 'https://' + documentation_link
        update_custom_setting('documentation_link', documentation_link)
        return JsonResponse({'result': 'success'})
