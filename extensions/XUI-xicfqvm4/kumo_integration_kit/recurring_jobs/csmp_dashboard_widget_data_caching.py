"""
This is a proof of concept for caching the data in order to implement dashboard widgets
"""
from datetime import datetime, timedelta
import os
import time
import json
import copy

from settings import PROSERV_DIR, DEBUG
from resourcehandlers.models import ResourceHandler
from utilities.models import ConnectionInfo
from common.methods import set_progress
from utilities.helpers import cb_request

from xui.kumo_integration_kit.constants import (
    API_ENDPOINTS_DICT,
    DATA_BACKUP_HOURS
)
from xui.kumo_integration_kit.utils import (
    get_default_rh_currency,
    get_adapter_id,
    validate_api,
    toggle_api_validation_status,
    ApiResponse
)
from xui.kumo_integration_kit.recurring_jobs.constants import *
from xui.kumo_integration_kit.apis.admin import KumoKit

from django.templatetags.static import static


def get_creds_from_connection_info():
    ci = ConnectionInfo.objects.filter(name__iexact='Kumolus Kit Creds').first()
    if ci:
        return f'https://{ci.ip}', ci.password

    return "", ""


def api_call_for_aws(rh, provider_account_id, host, api_key, which_widget, json_data):
    set_progress("This will show up api call and response for AWS RH")

    headers = { 'Authorization': api_key }
    params = {
        'provider_account_id': provider_account_id,
        'type': 'last_30_days'
    }

    kumokit = KumoKit()
    if hasattr(kumokit, "description"):
        if kumokit.description:
            kumo_des = json.loads(kumokit.description)
            if "default_currency" in kumo_des.keys():
                if "currency_unified" in kumo_des.keys():
                    if kumo_des["currency_unified"]:
                        if get_default_rh_currency(rh) != kumo_des["default_currency"]:
                            params.update({
                                "currency": kumo_des["default_currency"]
                            })

    call_get_method = True
    if which_widget == "days":
        url = host + API_ENDPOINTS_DICT["cost_by_days"]
    elif which_widget == 'services':
        url = host + API_ENDPOINTS_DICT["cost_by_services"]
    elif which_widget == 'compliance':
        url = host + API_ENDPOINTS_DICT["aws_compliance_report"]
    elif which_widget == 'efficiency':
        url = host + API_ENDPOINTS_DICT["service_type_count"]
    elif which_widget == 'spend_services' or which_widget == 'spend_locations' or which_widget == 'spend_resources':
        url = host + API_ENDPOINTS_DICT["get_chart_data"]
        call_get_method = False
    if call_get_method:
        response = cb_request("GET", url, headers=headers, params=params, json=json_data)
    else:
        if "currency" in params:
            response = cb_request("POST", url, headers=headers, params=params, json=json_data)
        else:
            response = cb_request("POST", url, headers=headers, json=json_data)
    
    response = ApiResponse.handle_response(response=response)
    _status, response = ApiResponse.check_response(response)
    if _status:
        return response
        
    return {}


def api_call_for_azure(rh, azure_provider_account_id, host, api_key, which_widget, json_data):
    set_progress("This will show up api call and response for Azure RH")
    headers = { 'Authorization': api_key }
    params = {
        'provider_account_id': azure_provider_account_id,
        'type': 'last_30_days'
    }

    kumokit = KumoKit()
    if hasattr(kumokit, "description"):
        if kumokit.description:
            kumo_des = json.loads(kumokit.description)
            if "default_currency" in kumo_des.keys():
                if "currency_unified" in kumo_des.keys():
                    if kumo_des["currency_unified"]:
                        if get_default_rh_currency(rh) != kumo_des["default_currency"]:
                            params.update({
                                "currency": kumo_des["default_currency"]
                            })

    call_get_method = True
    if which_widget == "days":
        url = host + API_ENDPOINTS_DICT["azure_cost_by_days"]
    elif which_widget == 'services':
        url = host + API_ENDPOINTS_DICT["azure_cost_by_services"]
    elif which_widget == 'efficiency':
        url = host + API_ENDPOINTS_DICT["service_type_count"]
    elif which_widget == 'spend_services' or which_widget == 'spend_locations' or which_widget == 'spend_resources':
        url = host + API_ENDPOINTS_DICT["azure_get_chart_data"]
        call_get_method = False
    if call_get_method:
        response = cb_request("GET", url, headers=headers, params=params, json=json_data)
    else:
        if "currency" in params:
            response = cb_request("POST", url, headers=headers, params=params, json=json_data)
        else:
            response = cb_request("POST", url, headers=headers, json=json_data)
    
    response = ApiResponse.handle_response(response=response)
    _status, response = ApiResponse.check_response(response)
    if _status:
        return response

    return {}


def api_call_for_gcp(rh, provider_account_id, host, api_key, which_widget, json_data):
    set_progress("This will show up api call and response for GCP RH")
    headers = { 'Authorization': api_key }
    params = {
        'type': 'last_30_days'
    }

    kumokit = KumoKit()
    if hasattr(kumokit, "description"):
        if kumokit.description:
            kumo_des = json.loads(kumokit.description)
            if "default_currency" in kumo_des.keys():
                if "currency_unified" in kumo_des.keys():
                    if kumo_des["currency_unified"]:
                        if get_default_rh_currency(rh) != kumo_des["default_currency"]:
                            params.update({
                                "currency": kumo_des["default_currency"]
                            })

    json_data["provider_account_id"] = provider_account_id
    call_get_method = True
    if which_widget == "days":
        url = host + API_ENDPOINTS_DICT["gcp_cost_by_days"]
    elif which_widget == 'services':
        url = host + API_ENDPOINTS_DICT["gcp_cost_by_services"]
    elif which_widget == 'efficiency':
        url = host + API_ENDPOINTS_DICT["service_type_count"]
    elif which_widget == 'spend_services' or which_widget == 'spend_locations' or which_widget == 'spend_resources':
        url = host + API_ENDPOINTS_DICT["gcp_get_chart_data"]
        call_get_method = False
    if call_get_method:
        response = cb_request("GET", url, headers=headers, params=params, json=json_data)
    else:
        if "currency" in params:
            response = cb_request("POST", url, headers=headers, params=params, json=json_data)
        else:
            response = cb_request("POST", url, headers=headers, json=json_data)
    
    response = ApiResponse.handle_response(response=response)
    _status, response = ApiResponse.check_response(response)
    if _status:
        return response

    return {}


def get_cloud_providers_data(src, host, api_key, file_name, which_widget):
    set_progress(which_widget.capitalize()+" Data Function")
    file_location = os.path.join(src, file_name)
    response_dict = {
        "AWS": [],
        "Azure": [],
        "GCP": [],
    }
    aws_adapter, azure_adapters, gcp_adapters = get_adapter_id()
    for rh in ResourceHandler.objects.all():
        json_data = {}
        cast = rh.cast()
        if (rh.resource_technology.type_slug == "aws"
            or rh.resource_technology.type_slug == "awsjit"
        ):
            if cast.__dict__["account_id"] in aws_adapter:
                provider_account_id = cast.account_id
                if which_widget == 'spend_resources':
                    json_data = copy.deepcopy(SPEND_PAYLOAD_AWS)
                    json_data["report"]["provider_account_id"] = str(provider_account_id)
                    json_data["report"]["rh_id"] = rh.id
                    json_data["report"]["multi_series"] = False
                    json_data["report"]["date_range"]["start_date"] = (datetime.now() - timedelta(days=30)).strftime("%d-%m-%Y")
                    json_data["report"]["date_range"]["end_date"] = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%Y")
                elif which_widget == 'spend_services':
                    json_data = copy.deepcopy(SPEND_PAYLOAD_AWS)
                    json_data["report"]["provider_account_id"] = str(provider_account_id)
                    json_data["report"]["rh_id"] = rh.id
                    json_data["report"]["multi_series"] = "service"
                    json_data["report"]["date_range"]["start_date"] = (datetime.now() - timedelta(days=30)).strftime("%d-%m-%Y")
                    json_data["report"]["date_range"]["end_date"] = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%Y")
                elif which_widget == 'spend_locations':
                    json_data = copy.deepcopy(SPEND_PAYLOAD_AWS)
                    json_data["report"]["provider_account_id"] = str(provider_account_id)
                    json_data["report"]["rh_id"] = rh.id
                    json_data["report"]["multi_series"] = "region"
                    json_data["report"]["date_range"]["start_date"] = (datetime.now() - timedelta(days=30)).strftime("%d-%m-%Y")
                    json_data["report"]["date_range"]["end_date"] = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%Y")
                response = api_call_for_aws(rh, provider_account_id, host, api_key, which_widget, json_data)

                if response: # and "message" not in response:
                    if which_widget == 'services':
                        services = [x['label'] for x in response['chart_data']]
                        json_data = copy.deepcopy(SPEND_PAYLOAD_AWS)
                        json_data["report"]["provider_account_id"] = str(provider_account_id)
                        json_data["report"]["rh_id"] = rh.id
                        json_data["report"]["multi_series"] = "service"
                        json_data["report"]["service"] = services
                        json_data["report"]["date_range"]["start_date"] = (datetime.now() - timedelta(days=30)).strftime("%d-%m-%Y")
                        json_data["report"]["date_range"]["end_date"] = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%Y")
                        response = api_call_for_aws(rh, provider_account_id, host, api_key, "spend_services", json_data)
                    
                    if response:
                        response['account_id'] = provider_account_id
                        response['rh_type'] = "aws"
                        response['rh_name'] = rh.name
                        response_dict["AWS"].append(response)

        elif rh.resource_technology.type_slug == "azure_arm":
            if cast.__dict__["serviceaccount"] in azure_adapters:
                azure_provider_account_id = cast.serviceaccount
                if which_widget == 'spend_resources':
                    json_data = copy.deepcopy(SPEND_PAYLOAD_AZURE)
                    json_data["report"]["provider_account_id"] = azure_provider_account_id
                    json_data["report"]["rh_id"] = rh.id
                    json_data["report"]["multi_series"] = False
                    json_data["report"]["date_range"]["start_date"] = (datetime.now() - timedelta(days=30)).strftime("%d-%m-%Y")
                    json_data["report"]["date_range"]["end_date"] = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%Y")
                elif which_widget == 'spend_services':
                    json_data = copy.deepcopy(SPEND_PAYLOAD_AZURE)
                    json_data["report"]["provider_account_id"] = azure_provider_account_id
                    json_data["report"]["rh_id"] = rh.id
                    json_data["report"]["multi_series"] = "service_name"
                    json_data["report"]["date_range"]["start_date"] = (datetime.now() - timedelta(days=30)).strftime("%d-%m-%Y")
                    json_data["report"]["date_range"]["end_date"] = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%Y")
                elif which_widget == 'spend_locations':
                    json_data = copy.deepcopy(SPEND_PAYLOAD_AZURE)
                    json_data["report"]["provider_account_id"] = azure_provider_account_id
                    json_data["report"]["rh_id"] = rh.id
                    json_data["report"]["multi_series"] = "location"
                    json_data["report"]["date_range"]["start_date"] = (datetime.now() - timedelta(days=30)).strftime("%d-%m-%Y")
                    json_data["report"]["date_range"]["end_date"] = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%Y")
                response = api_call_for_azure(rh, azure_provider_account_id, host, api_key, which_widget, json_data)

                if response: # and "message" not in response:
                    if which_widget == 'services':
                        services = [x['label'] for x in response['chart_data']]
                        json_data = copy.deepcopy(SPEND_PAYLOAD_AZURE)
                        json_data["report"]["provider_account_id"] = azure_provider_account_id
                        json_data["report"]["rh_id"] = rh.id
                        json_data["report"]["multi_series"] = "service_name"
                        json_data["report"]["service_name"] = services
                        json_data["report"]["date_range"]["start_date"] = (datetime.now() - timedelta(days=30)).strftime("%d-%m-%Y")
                        json_data["report"]["date_range"]["end_date"] = (datetime.now() - timedelta(days=1)).strftime("%d-%m-%Y")
                        response = api_call_for_azure(rh, azure_provider_account_id, host, api_key, "spend_services", json_data)
                        
                    if response:
                        response['account_id'] = azure_provider_account_id
                        response['rh_type'] = "azure_arm"
                        response['rh_name'] = rh.name
                        response_dict["Azure"].append(response)

        elif rh.resource_technology.type_slug == "gcp":
            provider_account_id = list(cast.gcp_projects.filter(imported=True).values_list("gcp_id", flat=True))
            provider_account_id = list(set(provider_account_id) & set(gcp_adapters.keys()))
            if provider_account_id:
                if which_widget == 'spend_resources':
                    json_data = copy.deepcopy(SPEND_PAYLOAD_GCP)
                    json_data["report"]["provider_account_id"] = provider_account_id
                    json_data["report"]["multi_series"] = False
                    json_data["report"]["date_range"]["start_date"] = (datetime.now() - timedelta(days=30)).strftime("%B %d, %Y")
                    json_data["report"]["date_range"]["end_date"] = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")
                elif which_widget == 'spend_services':
                    json_data = copy.deepcopy(SPEND_PAYLOAD_GCP)
                    json_data["report"]["provider_account_id"] = provider_account_id
                    json_data["report"]["multi_series"] = "service"
                    json_data["report"]["date_range"]["start_date"] = (datetime.now() - timedelta(days=30)).strftime("%B %d, %Y")
                    json_data["report"]["date_range"]["end_date"] = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")
                elif which_widget == 'spend_locations':
                    json_data = copy.deepcopy(SPEND_PAYLOAD_GCP)
                    json_data["report"]["provider_account_id"] = provider_account_id
                    json_data["report"]["multi_series"] = "region"
                    json_data["report"]["date_range"]["start_date"] = (datetime.now() - timedelta(days=30)).strftime("%B %d, %Y")
                    json_data["report"]["date_range"]["end_date"] = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")
                response = api_call_for_gcp(rh, provider_account_id, host, api_key, which_widget, json_data)

                if response: # and "message" not in response:
                    if which_widget == 'services':
                        services = [x['label'] for x in response['chart_data']]
                        json_data = copy.deepcopy(SPEND_PAYLOAD_GCP)
                        json_data["report"]["provider_account_id"] = provider_account_id
                        json_data["report"]["multi_series"] = "service"
                        json_data["report"]["service"] = services
                        json_data["report"]["date_range"]["start_date"] = (datetime.now() - timedelta(days=30)).strftime("%B %d, %Y")
                        json_data["report"]["date_range"]["end_date"] = (datetime.now() - timedelta(days=1)).strftime("%B %d, %Y")
                        response = api_call_for_gcp(rh, provider_account_id, host, api_key, "spend_services", json_data)
                    
                    if response:
                        response['account_id'] = provider_account_id
                        response['rh_type'] = "gcp"
                        response['rh_name'] = rh.name
                        response_dict["GCP"].append(response)

    if response_dict["AWS"] or response_dict["Azure"] or response_dict["GCP"]:
        json_object = json.dumps(response_dict)
        with open(file_location, "w") as outfile:
            outfile.write(json_object)

    return


def get_compliance_data(src, host, api_key, file_name, which_widget):
    set_progress("Compliance Data Function")
    file_location = os.path.join(src, file_name)

    final_response = {}
    for rh in ResourceHandler.objects.all():
        cast = rh.cast()
        json_data = {}
        if (rh.resource_technology.type_slug == "aws"
            or rh.resource_technology.type_slug == "awsjit"
        ):
            provider_account_id = cast.account_id
            response = api_call_for_aws(rh, provider_account_id, host, api_key, which_widget, json_data)
            overview_response = get_compliance_overview(api_key, host, provider_account_id)
            response_dict = {d.pop('standard_type'): d for d in overview_response}
            if response: # and "message" not in response:
                for d in response:
                    if response and type(response) == list:
                        response_dict[d.pop('standard_type')].update(d)
                final_response[rh.id] = response_dict
    json_object = json.dumps(final_response)
    with open(file_location, "w") as outfile:
        outfile.write(json_object)
    return


def get_compliance_overview(api_key, host, provider_account_id):
    standard_types = [
        {
            "standard_type": "CIS",
            "standard_version": "1.2.0",
            "image_path": static('kumo_integration_kit/images/cis.png')
        },
        {
            "standard_type": "PCI",
            "standard_version": "3.2.1",
            "image_path": static('kumo_integration_kit/images/pci.png')
        },
        {
            "standard_type": "NIST",
            "standard_version": "1.1.0",
            "image_path": static('kumo_integration_kit/images/nist.png')
        },
        {
            "standard_type": "HIPAA",
            "standard_version": "5010",
            "image_path": static('kumo_integration_kit/images/hipaa.png')
        },
        {
            "standard_type": "AWSWA",
            "standard_version": "1.0.0",
            "image_path": static('kumo_integration_kit/images/awswa.png')
        }
    ]
    response_list = []
    for data in standard_types:
        json_data = {}
        data['provider_account_id'] = provider_account_id
        url = host + API_ENDPOINTS_DICT['aws_compliance_overview']
        headers = { 'Authorization': api_key }
        response = cb_request("GET", url, headers=headers, json=data)
        response = ApiResponse.handle_response(response=response)
        _status, response = ApiResponse.check_response(response)
        if _status:
            json_data["standard_type"] = data['standard_type']
            json_data["fail_count_by_resource"] = response['fail_count_by_resource']
            json_data["image_path"] = data["image_path"]
            response_list.append(json_data)
            
    return response_list


def get_efficiency_data(src, host, api_key, file_name, which_widget):
    set_progress("Efficiency Data Function")
    file_location = os.path.join(src, file_name)
    response_list = []
    aws_adapter, azure_adapters, gcp_adapters = get_adapter_id()
    
    for rh in ResourceHandler.objects.all():
        cast = rh.cast()
        json_data = {}
        if (rh.resource_technology.type_slug == "aws"
            or rh.resource_technology.type_slug == "awsjit"
        ):
            if cast.__dict__["account_id"] in aws_adapter:
                provider_account_id = cast.account_id
                json_data = EFFICIENCY_PAYLOAD_AWS
                json_data['adapter_id'] = provider_account_id
                json_data['adapter_ids'] = provider_account_id
                json_data['provider_account_id'] = provider_account_id
                json_data['rh_id'] = rh.id
                response = api_call_for_aws(rh, provider_account_id, host, api_key, which_widget, json_data)
                if response: # and "message" not in response:
                    response['rh_name'] = rh.name
                    right_sized_response = get_right_sized_data(rh, provider_account_id, host, api_key, rh.id)
                    ignored_services_response = get_ignored_services_data(rh, provider_account_id, host, api_key, rh.id)
                    if right_sized_response:
                        response['service_type_count'].append(right_sized_response)
                    if ignored_services_response:
                        response['service_type_count'].append(ignored_services_response)
                        response_list.append(response)

        elif rh.resource_technology.type_slug == "azure_arm":
            if cast.__dict__["serviceaccount"] in azure_adapters:
                azure_provider_account_id = cast.serviceaccount
                json_data = EFFICIENCY_PAYLOAD_AZURE
                json_data['adapter_id'] = azure_provider_account_id
                json_data['adapter_ids'] = azure_provider_account_id
                json_data['provider_account_id'] = azure_provider_account_id
                json_data['rh_id'] =rh.id
                response = api_call_for_azure(rh, azure_provider_account_id, host, api_key, which_widget, json_data)
                if response: # and "message" not in response:
                    response['rh_name'] = rh.name
                    response_list.append(response)

        elif rh.resource_technology.type_slug == "gcp":
            provider_account_id = list(cast.gcp_projects.filter(imported=True).values_list("gcp_id", flat=True))
            provider_account_id = list(set(provider_account_id) & set(gcp_adapters.keys()))
            if provider_account_id:
                json_data = EFFICIENCY_PAYLOAD_GCP
                json_data['adapter_id'] = provider_account_id
                json_data['adapter_ids'] = provider_account_id
                json_data['provider_account_id'] = provider_account_id
                response = api_call_for_gcp(rh, provider_account_id, host, api_key, which_widget, json_data)
                if response: # and "message" not in response:
                    response['rh_name'] = rh.name
                    response_list.append(response)

    if response_list:
        json_object = json.dumps(response_list)
        with open(file_location, "w") as outfile:
            outfile.write(json_object)

    return


def get_right_sized_data(rh, provider_account_id, host, api_key, rh_id):
    response_list = {}
    json_data = RIGHT_SIZED_PAYLOAD
    json_data["adapter_id"] = provider_account_id
    json_data["provider_account_id"] = provider_account_id
    json_data["rh_id"] = rh_id
    headers = { 'Authorization': api_key }
    params = {
        'provider_account_id': provider_account_id,
        'type': 'last_30_days'
    }

    kumokit = KumoKit()
    if hasattr(kumokit, "description"):
        if kumokit.description:
            kumo_des = json.loads(kumokit.description)
            if "default_currency" in kumo_des.keys():
                if "currency_unified" in kumo_des.keys():
                    if kumo_des["currency_unified"]:
                        if get_default_rh_currency(rh) != kumo_des["default_currency"]:
                            params.update({
                                "currency": kumo_des["default_currency"]
                            })

    url = host + API_ENDPOINTS_DICT["ec2_rightsize"]
    response = cb_request("GET", url, headers=headers, params=params, json=json_data)
    response = ApiResponse.handle_response(response=response)
    _status, response = ApiResponse.check_response(response)
    if _status:
        response_list = {
            "type": "ec2_right_sizings",
            "count": response['meta_data'].get('instance_count'),
            "cost_sum": response['meta_data'].get('total_saving')
        }
    return response_list


def get_ignored_services_data(rh, provider_account_id, host, api_key, rh_id):
    response_list = {}
    json_data = IGNORED_SERVICES_PAYLOAD
    json_data["adapter_id"] = provider_account_id
    json_data["provider_account_id"] = provider_account_id
    json_data["rh_id"] = rh_id
    headers = { 'Authorization': api_key }
    params = {
        'provider_account_id': provider_account_id,
        'type': 'last_30_days'
    }

    kumokit = KumoKit()
    if hasattr(kumokit, "description"):
        if kumokit.description:
            kumo_des = json.loads(kumokit.description)
            if "default_currency" in kumo_des.keys():
                if "currency_unified" in kumo_des.keys():
                    if kumo_des["currency_unified"]:
                        if get_default_rh_currency(rh) != kumo_des["default_currency"]:
                            params.update({
                                "currency": kumo_des["default_currency"]
                            })

    url = host + API_ENDPOINTS_DICT["ignored_services"]
    response = cb_request("GET", url, headers=headers, params=params, json=json_data)
    response = ApiResponse.handle_response(response=response)
    _status, response = ApiResponse.check_response(response)
    if _status:
        response_list = {
            "type": "ignore_services",
            "count": response['count'],
            "cost_sum": response['service_cost_sum']
        }
    return response_list


def run(job, *args, **kwargs):
    set_progress("This will show up in the job details page in the CB UI, and in the job log")
    host, api_key = get_creds_from_connection_info()
    if host and api_key:
        api_validation_status = validate_api(api_key)     
        toggle_api_validation_status(api_validation_status)
        
    if host and api_key and api_validation_status:
        src = os.path.join(PROSERV_DIR, "cached_xui_data", "kumo_integration_kit",
                           "widget_data")
        isExist = os.path.exists(src)
        if not isExist:
            os.makedirs(src)
        get_cloud_providers_data(src, host, api_key, "cost_by_days_data.txt", "days")
        get_cloud_providers_data(src, host, api_key, "cost_by_services_data.txt", "services")
        get_cloud_providers_data(src, host, api_key, "spend_resources_details.txt", "spend_resources")
        get_cloud_providers_data(src, host, api_key, "spend_services_details.txt", "spend_services")
        get_cloud_providers_data(src, host, api_key, "spend_locations_details.txt", "spend_locations")
        get_compliance_data(src, host, api_key, "compliance_data.txt", "compliance")
        get_efficiency_data(src, host, api_key, "efficiency_tab.txt", "efficiency")

        return "SUCCESS", "Data is cached successfully", ""

    if not api_validation_status:
        return "FAILED", "Your API key is expired, Please update the CSMP API key and try again!", ""    
    
    return "FAILED", "No CSMP credentials found", ""
