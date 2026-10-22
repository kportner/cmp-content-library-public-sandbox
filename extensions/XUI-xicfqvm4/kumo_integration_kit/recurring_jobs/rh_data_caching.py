"""
This is a proof of concept for caching the data in order to implement dashboard widgets
"""
from datetime import datetime, timedelta
import os
import json
from django.db import connection

from settings import PROSERV_DIR, DEBUG
from resourcehandlers.models import ResourceHandler
from utilities.models import ConnectionInfo
from infrastructure.models import CustomField
from infrastructure.models import Environment
# from resourcehandlers.aws.models import AWSHandler
# from resourcehandlers.awsjit.models import AWSJITHandler
from resourcehandlers.azure_arm.models import AzureARMHandler
from resourcehandlers.gcp.models import GCPHandler
from common.methods import set_progress
from xui.kumo_integration_kit.constants import (
    API_ENDPOINTS_DICT,
    DATA_BACKUP_HOURS
)
from xui.kumo_integration_kit.utils import (
    get_currency,
    validate_api,
    ApiResponse,
    get_adapter_id,
    toggle_api_validation_status
)   
from xui.kumo_integration_kit.recurring_jobs.constants import *
from xui.kumo_integration_kit.apis.admin import KumoKit
from django.templatetags.static import static

yesterday = (datetime.now()-timedelta(days=1)).strftime("%d-%m-%Y")
day_before_30_day = (datetime.now()-timedelta(days=30)).strftime("%d-%m-%Y")
total_months = 2 if yesterday.split("-")[1] != day_before_30_day.split("-")[1] else 1


def get_creds_from_connection_info():
    ci = ConnectionInfo.objects.filter(name__iexact='Kumolus Kit Creds').first()
    if ci:
        return f'https://{ci.ip}', ci.password, ci.description, ci

    return "", "", "", ""


def get_or_create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='rh_currency',
        defaults={
            'label': 'RH Default Currency - CSMP',
            'type': 'STR',
            'show_as_attribute': True,
            'description': 'This is the default currecny of a RH imported from CSMP'
        }
    )


def get_and_store_rh_currency(src, host, api_key):
    set_progress("Fetching the default currencies for all Resource Handlers from CSMP...")
    for rh in ResourceHandler.objects.all():
        if (rh.cast().resource_technology.type_slug == "aws"
            or rh.cast().resource_technology.type_slug == "awsjit"
        ):
            provider_account_id = str(rh.cast().account_id)
        elif rh.cast().resource_technology.type_slug == "gcp":
            provider_account_id = list(rh.cast().gcp_projects.filter(
                                       imported=True).values_list(
                                       "gcp_id", flat=True))
        elif rh.cast().resource_technology.type_slug == "azure_arm":
            provider_account_id = str(rh.cast().serviceaccount)

        for env in list(Environment.objects.filter(resource_handler=rh)):
            env.rh_currency = get_currency(provider_account_id, rh)

    return


def get_and_store_csmp_adapters(src, host, api_key, file_name):
    set_progress("Fetching the CSMP adapter list...")
    file_location = os.path.join(src, file_name)
    payload = {
        'show_all': 'true',
        'not_configured': 'true',
    }

    response = ApiResponse(payload,
                           'get_mapped_adapters').fetch_response()
    _status, response = ApiResponse.check_response(response)
    if _status:
        json_object = json.dumps(response)
        with open(file_location, "w") as outfile:
            outfile.write(json_object)
    return


def get_and_store_cloud_spend_tab(src, host, api_key, cloud_provider):
    file_name = f"{cloud_provider}_spend.json"
    file_location = os.path.join(src, file_name)
    aws_rh, azure_arm_rh, gcp_rh = get_adapter_id()
    complete_response = {}
    if "aws" in file_name:
        set_progress("AWS data being fetched and cached...")
        # rh_list = list(AWSHandler.objects.all())
        # all_db_tables = connection.introspection.table_names()
        # awsjit_table_name = AWSJITHandler.objects.model._meta.db_table
        # if awsjit_table_name in all_db_tables:
        #     rh_list += list(AWSJITHandler.objects.all())
        rh_queryset = list(ResourceHandler.objects.filter(
            resource_technology__slug__startswith="aws"))
        rh_list = [rh.cast() for rh in rh_queryset]
            
        for rh in rh_list:
            if rh.account_id in aws_rh:
                for tabs in ["custom", "compute", "database", "storage", "transfer"]:
                    payload = get_aws_payload(rh.account_id, tabs)
                    response = ApiResponse(payload, 'get_chart_data',
                                           request_type="POST").fetch_response()
                    _status, response = ApiResponse.check_response(response)
                    if _status:
                        complete_response[f"{rh.id}-{tabs}"] = response

    elif "azure" in file_name:
        set_progress("Azure data being fetched and cached...")
        rh_list = list(AzureARMHandler.objects.all())
        for rh in rh_list:
            if rh.serviceaccount in azure_arm_rh:
                for tabs in ["custom", "compute", "database", "storage"]:
                    payload = get_azure_arm_payload(rh.serviceaccount, tabs)
                    response = ApiResponse(payload, 'azure_get_chart_data',
                                           request_type="POST").fetch_response()
                    _status, response = ApiResponse.check_response(response)
                    if _status:
                        complete_response[f"{rh.id}-{tabs}"] = response

    elif "gcp" in file_name:
        set_progress("GCP data being fetched and cached...")
        rh_list = GCPHandler.objects.all()
        for rh in rh_list:
            project_list = list(rh.gcp_projects.filter(
                                imported=True).values_list("gcp_id",
                                                           flat=True))
            common_projects_list = list(set(project_list) & set(gcp_rh.keys()))
            if common_projects_list:
                for tabs in ["custom", "compute", "database"]:
                    payload = get_gcp_payload(common_projects_list, tabs)
                    response = ApiResponse(payload, 'gcp_get_chart_data',
                                           request_type="POST").fetch_response()
                    _status, response = ApiResponse.check_response(response)
                    if _status:
                        complete_response[f"{rh.id}-{tabs}"] = response

    if complete_response:
        json_object = json.dumps(complete_response)
        with open(file_location, "w") as outfile:
            outfile.write(json_object)
    return


def save_default_payload(src):
    set_progress("Saving the default payloads for cloud providers")
    payload_file = os.path.join(src, "default_payload.json")
    pop_list = ["provider_account_id"]
    default_payload = {}
    for cloud_provider in ['aws', 'azure_arm', 'gcp']:
        default_payload[cloud_provider] = {}
        if cloud_provider == "aws":
            for tabs in ["custom", "compute", "database", "storage", "transfer"]:
                payload = get_aws_payload(None, tabs)
                
                report = {key: payload['report'][key] for key in payload['report'] if key not in pop_list}
                final_payload = {
                    "report": report,
                    "total_days": payload['total_days'],
                    "total_months": payload['total_months']
                }
                default_payload[cloud_provider][tabs] = final_payload
        elif cloud_provider == "azure_arm":
            for tabs in ["custom", "compute", "database", "storage"]:
                payload = get_azure_arm_payload(None, tabs)
                report = {key: payload['report'][key] for key in payload['report'] if key not in pop_list}
                final_payload = {
                    "report": report,
                    "total_days": payload['total_days'],
                    "total_months": payload['total_months']
                }
                final_payload["report"]["tab"] = tabs
                default_payload[cloud_provider][tabs] = final_payload
        elif cloud_provider == "gcp":
            for tabs in ["custom", "compute", "database"]:
                payload = get_gcp_payload(None, tabs)
                report = {key: payload['report'][key] for key in payload['report'] if key not in pop_list}
                final_payload = {
                    "report": report,
                    "total_days": payload['total_days'],
                    "total_months": payload['total_months']
                }
                final_payload["report"]["tab"] = tabs
                default_payload[cloud_provider][tabs] = final_payload
    json_object = json.dumps(default_payload)
    with open(payload_file, "w") as outfile:
        outfile.write(json_object)
    return True


def get_aws_payload(provider_account_id, tab):
    if tab == "compute":
        service = ["Amazon Elastic Compute Cloud"]
        product_family = []
    elif tab == "database":
        service = ["Amazon Relational Database Service"]
        product_family = []
    elif tab == "storage":
        service = ["Amazon Simple Storage Service"]
        product_family = []
    elif tab == "transfer":
        service = ["AWS Data Transfer"]
        product_family = ["Data Transfer"]
    else:
        service = []
        product_family = []

    return {
        "report": {
            "daily": True,
            "date_range": {
                "start_date": day_before_30_day,
                "end_date": yesterday
            },
            "tags": {},
            "type": "cost_report",
            "account": [],
            "service": service,
            "region": [],
            "usage_type": [],
            "operation": [],
            "monthly": False,
            "multi_series": False,
            "select_metric": "unblended",
            "product_family": product_family,
            "is_upfront_reservation_charges": True,
            "is_support_charges": True,
            "is_other_subscription_charges": True,
            "is_credit": True,
            "is_margin": True,
            "is_discount": True,
            "is_edp": True,
            "is_refund": True,
            "is_tax_charge": True,
            "is_tax_refund": True,
            "dimensions": [
                "date"
            ],
            "metrics": [
                "unblended"
            ],
            "provider_account_id": provider_account_id
        },
        "total_days": 30,
        "total_months": total_months
    }


def get_azure_arm_payload(provider_account_id, tab):
    if tab == "compute":
        serviceName = ["Virtual Machines", "Virtual Machines Licenses",
                       "Storage", "Bandwidth", "Virtual Network"]
        consumedService = ["Microsoft.Compute"]
    elif tab == "database":
        serviceName = ["SQL Database", "Azure Database for MySQL",
                       "Azure Database for PostgreSQL",
                       "Azure Database for MariaDB",
                       "Advanced Data Security",
                       "SQL Managed Instance"]
        consumedService = []
    elif tab == "storage":
        serviceName = ["Storage", "Bandwidth"]
        consumedService = ["Microsoft.Storage"]
    else:
        serviceName = []
        consumedService = []

    return {
        "report":
            {
                "daily": True,
                "monthly": False,
                "group_by": "date_range",
                "resource_group": [],
                "date_range": {
                    "start_date": day_before_30_day,
                    "end_date": yesterday
                },
                "consumed_service": consumedService,
                "service_name": serviceName,
                "service_tier": [],
                "resource_name": [],
                "tags": {},
                "location": [],
                "type": "azure_cost_report",
                "provider": "Azure",
                "multi_series": False,
                "tab": "database",
                "subscription": [],
                "dimensions": ["date"],
                "metrics": ["cost"],
                "select_metric": "cost",
                "provider_account_id": provider_account_id,
            },
        "total_days": 30,
        "total_months": total_months
    }


def get_gcp_payload(provider_account_id, tab):
    if tab == "compute":
        service = ["Compute Engine"]
    elif tab == "database":
        service = ["Cloud SQL"]
    else:
        service = []

    return {
        "report": {
            "daily": True,
            "monthly": False,
            "group_by": "date_range",
            "date_range": {
                "start_date": day_before_30_day,
                "end_date": yesterday
            },
            "sku": [],
            "service": service,
            "location": [],
            "project": [],
            "tags": {},
            "type": "gcp_cost_report",
            "provider": "GCP",
            "multi_series": False,
            "tab": "custom",
            "is_invoice": True,
            "is_partner_discount": True,
            "is_reseller_margin": True,
            "dimensions": [
                "date"
            ],
            "metrics": [
                "cost"
            ],
            "select_metric": "cost",
            "provider_account_id": provider_account_id
        },
        "total_days": 30,
        "total_months": total_months
    }


def run(job, *args, **kwargs):
    set_progress("This will show up in the job details page in the \
                 CB UI, and in the job log")
    get_or_create_custom_fields_as_needed()
    host, api_key, description, ci = get_creds_from_connection_info()
    if host and api_key:
        api_validation_status = validate_api(api_key)     
        toggle_api_validation_status(api_validation_status)

    if host and api_key and api_validation_status:
        src = os.path.join(PROSERV_DIR, "cached_xui_data", "kumo_integration_kit",
                           "csmp_data")
        isExist = os.path.exists(src)
        if not isExist:
            os.makedirs(src)

        get_and_store_rh_currency(src, host, api_key)
        get_and_store_csmp_adapters(src, host, api_key, "csmp_adapters.json")
        save_default_payload(src)
        set_progress("Fetching the Spend tab data from CSMP...")
        for cloud_provider in ['aws', 'azure_arm', 'gcp']:
            get_and_store_cloud_spend_tab(src, host, api_key, cloud_provider)

        return "SUCCESS", "Currencies are cached successfully", ""

    if not api_validation_status:
        return "FAILED", "Your API key is expired, Please update the CSMP API key and try again!", ""
    
    return "FAILED", "No CSMP credentials found", ""
