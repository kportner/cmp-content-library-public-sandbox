import os
import json
import datetime
import resource
import traceback
import requests
import pwd
import grp

from django.core.cache import cache
from django.http import HttpResponse, JsonResponse
from utilities.models import ConnectionInfo
from resourcehandlers.models import ResourceHandler
# from resourcehandlers.aws.models import AWSHandler
# from resourcehandlers.awsjit.models import AWSJITHandler
from resourcehandlers.azure_arm.models import AzureARMHandler
from resourcehandlers.gcp.models import GCPHandler
from infrastructure.models import Environment
from django.contrib.contenttypes.models import ContentType

from initialize.create_objects import create_recurring_job
from c2_wrapper import create_hook
from jobs.models import RecurringJob
from settings import PROSERV_DIR
from xui.kumo_integration_kit.kumo_wrapper import KumoConnector
from xui.kumo_integration_kit.constants import (
    API_ENDPOINTS_DICT,
    DATA_BACKUP_HOURS,
    CUSTOMIZATIONS_FILE_PATH
)
from utilities.logger import ThreadLogger

uid = pwd.getpwnam("cloudbolt").pw_uid
gid = grp.getgrnam("cloudbolt").gr_gid
logger = ThreadLogger(__name__)

class ApiResponse:
    """
    To fetch and handle the response from the CSMP API endpoints
    """
    def __init__(self, payload, api_endpoint, web_host=None, request_type=None):
        self.response = {}
        self.api_endpoint = API_ENDPOINTS_DICT[api_endpoint]
        self.payload = payload
        self.request_type = request_type
        self.web_host = web_host
        self.api_endpoint_key = api_endpoint

    def fetch_response(self):
        try:
            with KumoConnector() as conn:
                if self.web_host:
                    conn.base_url = self.web_host

                if self.request_type == "POST":
                    self.response = conn.post(self.api_endpoint, json=self.payload)
                elif self.request_type == "DELETE":
                    self.response = conn.delete(f"{self.api_endpoint}/{self.payload['cc_id']}",
                                                json={})
                elif self.request_type == "PATCH":
                    self.response = conn.patch(f"{self.api_endpoint}/{self.payload['cc_id']}",
                                                json=self.payload)
                else:
                    self.response = conn.get(self.api_endpoint, json=self.payload)

                # if self.api_endpoint_key != 'validate_api_token' and \
                #     self.api_endpoint_key != 'service_type_count':
                #     self.response.raise_for_status()

                # if self.api_endpoint_key not in \
                #     ['get_csv_download', 'get_potential_savings',
                #      'ec2_rightsizing_csv', 'azure_server_potential_savings',
                #      'validate_api_token', 'service_type_count', 'azure_currency']:
                #     try:
                #         if 'message' in self.response.json().keys():
                #             self.response = {}
                #     except:
                #         pass

        except:
            logger.warning(traceback.print_exc())
            # if self.response.status_code == 422:
            #     pass
            # if self.response.status_code == 401:
            #     self.response = { 'error_message': 'Invalid Credentials' }
            # else:
            self.response = {}
        
        if isinstance(self.response, requests.models.Response):
            return self.handle_response(response=self.response)

        return {
            "message": self.response if self.response is dict else {}
        }

    @classmethod
    def handle_response(cls, response):
        status_code = response.status_code

        if status_code == 200:
            logger.info("Request successful!")
            return response
        
        elif status_code == 401:
            logger.info("Not Authorised!")
            return {
                "message": "Invalid Credentials"
            }
        elif status_code == 404:
            logger.info("Not Authorised!")
            return {
                "message": "Invalid Permissions"
            }
        elif status_code == 422:
            logger.info("Error occurred!")
            return {
                "message": "Adapter `type` not found"
            }
        elif status_code == 500:
            logger.info("Internal server error or invalid credentials!")
            if response.json().get("message", None):
                return {
                    "message": "Invalid Credentials"
                }
            else:
                return {
                    "message": "Internal Server Error"
                }
        else:
            logger.info(f"Unexpected status code: {status_code}")
            return {
                "message": {}
            }

    @staticmethod
    def check_response(response):
        if isinstance(response, requests.models.Response):
            try:
                return True, response.json()
            except Exception as e:
                return True, response.text
        elif response.get("text", None):
            return True, response.text
        else:
            return False, response.get("message", None)


def get_credentials_from_db():
    """
    To fetch CSMP credentials of customer from ConnectionInfo table

    Returns:
        str: customer's CSMP domain and API Key
    """
    ci = ConnectionInfo.objects.filter(
        name__iexact='Kumolus Kit Creds').first()
    if ci:
        if ci.ip and ci.password:
            return f'https://{ci.ip}', ci.password
    return "", ""


def fetch_and_store_csmp_adapter(payload, file_location):
    response = ApiResponse(payload,
                               'get_mapped_adapters').fetch_response()
    _status, response = ApiResponse.check_response(response)
    if _status:
        json_object = json.dumps(response)
        with open(file_location, "w+") as outfile:
            outfile.write(json_object)
    
    return response


def get_adapter_id(account_id=None):
    """
    To fetch and return the adapters from CSMP
    """
    aws_adapter, azure_adapters, gcp_adapters = {}, {}, {}
    normal_adapter_id = ""
    response = {}
    file_name = "csmp_adapters.json"
    payload = {
        'show_all': 'true',
        'not_configured': 'true',
    }

    src = os.path.join(PROSERV_DIR, "cached_xui_data",
                       "kumo_integration_kit", "csmp_data")
    file_location = os.path.join(src, file_name)

    if not os.path.exists(file_location):
        if not os.path.exists(src):
            os.makedirs(src)
            
        response = fetch_and_store_csmp_adapter(payload, file_location)
        # os.chown(file_location, uid, gid)
    else:
        with open(file_location, "r") as outfile:
            json_object = outfile.read()
        response = json.loads(json_object)
        
        if not response.get("_embedded", None).get("adapters", None):
            if not response.get("_embedded", None).get("adapter", None):
                response = fetch_and_store_csmp_adapter(payload, file_location)
    
    if not response.get("_embedded", None).get("adapters", None):
        if not response.get("_embedded", None).get("adapter", None):        
            response = {}

    if response:
        response = response['_embedded']['adapter']

        aws_adapter = {adapter['aws_account_id']: adapter['id']
                    for adapter in response if 'aws_account_id' in adapter and adapter['aws_account_id']}

        azure_adapters = {adapter['azure_account_id']: adapter['id']
                        for adapter in response if 'azure_account_id' in adapter and adapter['azure_account_id']}

        gcp_adapters = {adapter['gcp_project_id']: adapter['id']
                        for adapter in response if 'gcp_project_id' in adapter and adapter['gcp_project_id']}

        if account_id:
            try:
                if type(account_id) == str:
                    if account_id in aws_adapter.keys():
                        normal_adapter_id = aws_adapter[account_id]
                    elif type(account_id) == str and account_id in azure_adapters.keys():
                        normal_adapter_id = azure_adapters[account_id]
                elif type(account_id) == list:
                    common_projects_list = list(set(account_id) & set(gcp_adapters.keys()))
                    normal_adapter_id = common_projects_list if common_projects_list else ""
            except KeyError:
                pass

    if account_id:
        return normal_adapter_id
    else:
        return aws_adapter, azure_adapters, gcp_adapters


def get_currency(provider_account_id, resource_handler, currency_dict=None):
    """
    To fetch azure resource handler currency from CSMP

    Args:
        provider_account_id (str): azure subscription id

    Returns:
        str: Currency in 3 char format e.g. USD, INR, etc.
    """
    payload = {"provider_account_id": provider_account_id}
    rh = resource_handler.cast()
    response_curr = ""

    if is_aws_based_handler(rh):
        response_curr = 'USD'
        response = ApiResponse(payload, 'fetch_currency_conversion').fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            if response.get("default_currency", None) and response.get("enable_currency_conversion", None):
                response_curr = str(response["default_currency"])

    if isinstance(rh, AzureARMHandler):
        response = ApiResponse(payload, 'azure_currency').fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            response_curr = response
        else:
            response_curr = 'USD'

    elif isinstance(rh, GCPHandler):
        response = ApiResponse(payload, 'gcp_get_currency').fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            response_curr = response["currency"]
        else:
            response_curr = 'USD'

    if type(currency_dict) == dict:
        currency_dict[resource_handler.id] = response_curr

    return response_curr


def get_default_rh_currency(handler):
    rh_currency = [
            env.rh_currency for env in Environment.objects.filter(
                resource_handler=handler) if hasattr(env, "rh_currency")
        ]
    rh_currency = list(filter(None, rh_currency))
    rh_currency = \
        rh_currency[0] if rh_currency else ""
    return rh_currency


def check_for_cache(rh_file_name):
    """
    To check if cache exists

    Args:
        rh_file_name (str): Key name of the cache

    Returns:
        bool: if no cache exists then returns True to fetch
    """
    logger.info(f"Checking for cached data ======> {rh_file_name}")
    cached_data = cache.get(rh_file_name, 'NO-VALUE')
    if cached_data == 'NO-VALUE':
        return True
    else:
        return False


def get_cache_data(rh_file_name):
    """
    To fetch the cache if exists

    Args:
        rh_file_name (str): Key name of the cache

    Returns:
        json: if cache exists returns the json object
    """
    logger.info(f"Fetching cached data for {rh_file_name}")
    cached_data = json.loads(cache.get(rh_file_name, 'NO-VALUE'))
    if cached_data != 'NO-VALUE':
        return cached_data
    else:
        return {}


def set_cache_data(rh_file_name, data_to_bo_stored):
    """
    To save the data in the cache

    Args:
        rh_file_name (str): Key name of the cache
        data_to_bo_stored (dict): python dictionary containing data to be cached
    """
    logger.info(f"Caching data for {rh_file_name} for next 6 hours")
    cache.set(rh_file_name, json.dumps(data_to_bo_stored), DATA_BACKUP_HOURS*60*60)
    return


def create_folder_with_permission(folder_name):
    widget_data_fol_path = os.path.join(os.path.dirname(__file__), folder_name)
    if not os.path.exists(widget_data_fol_path):
        os.makedirs(widget_data_fol_path)

    os.chmod(widget_data_fol_path, 0o777)
    return


def write_to_file(key_id, file_location, response):
    complete_response = {}
    if os.path.exists(file_location):
        with open(file_location, "r") as outfile:
            file_content = json.loads(outfile.read())
        file_content[key_id] = response
        complete_response = file_content
    else:
        complete_response[key_id] = response

    json_object = json.dumps(complete_response)
    with open(file_location, "w+") as outfile:
        outfile.write(json_object)
    # os.chown(file_location, uid, gid)
    return


def _update_or_create_recurring_job():
    recurring_job = {
        'name': 'CSMP Dashboard Widget Data Caching',
        "description": (
            "In order to see dashboard widget's data, you have to run this recurring job "
            "which will cache the data for better dashboard performance and less latency."
        ),
        'schedule': '10 0 * * *',
        'type': 'recurring_action',
        'enabled': True,
        "hook_name": "CSMP Dashboard Widget",
    }
    recurring_job_hook = {
        'name': "CSMP Dashboard Widget",
        'description': "Generate hook for CSMP Dashboard Widget data caching recurring job.",
        'hook_point': None,
        'module': os.path.join(PROSERV_DIR, "xui", "kumo_integration_kit",
                               "recurring_jobs", "csmp_dashboard_widget_data_caching.py"),
    }

    create_hook(**recurring_job_hook)
    create_recurring_job(recurring_job)
    create_folder_with_permission("widget_data")
    create_folder_with_permission("csmp_data")
    rj_obj = RecurringJob.objects.filter(name="CSMP Dashboard Widget Data Caching").first()
    return bool(rj_obj), rj_obj.id


def _update_or_create_rh_currency_job():
    recurring_job = {
        'name': 'CSMP Resource Handler Data Caching',
        "description": (
            "This will fetch default resource handler currencies from CSMP "
            "and store them in CustomField"
        ),
        'schedule': '10 0 * * *',
        'type': 'recurring_action',
        'enabled': True,
        "hook_name": "CSMP Resource Handler Data",
    }
    recurring_job_hook = {
        'name': "CSMP Resource Handler Data",
        'description': "Generate hook for CSMP Resource Handler Data caching recurring job.",
        'hook_point': None,
        'module': os.path.join(PROSERV_DIR, "xui", "kumo_integration_kit",
                               "recurring_jobs", "rh_data_caching.py"),
    }

    create_hook(**recurring_job_hook)
    create_recurring_job(recurring_job)
    rj_obj = RecurringJob.objects.filter(
                name="CSMP Resource Handler Data Caching").first()

    return bool(rj_obj), rj_obj.id


def get_all_compliance_data(data_obj):
    response_dict = {
    "CIS":{
         "fail_count_by_resource": 0,
         "image_path":"",
         "standard_version":"",
         "threat_count": 0,
         "total_count": 0,
         "compliance_progress": 0
        },
        "PCI":{
            "fail_count_by_resource": 0,
            "image_path":"",
            "standard_version":"",
            "threat_count": 0,
            "total_count": 0,
            "compliance_progress": 0
        },
        "NIST":{
            "fail_count_by_resource": 0,
            "image_path":"",
            "standard_version":"",
            "threat_count": 0,
            "total_count": 0,
            "compliance_progress": 0
        },
        "HIPAA":{
            "fail_count_by_resource": 0,
            "image_path":"",
            "standard_version":"",
            "threat_count": 0,
            "total_count": 0,
            "compliance_progress": 0
        },
        "AWSWA":{
            "fail_count_by_resource": 0,
            "image_path":"",
            "standard_version":"",
            "threat_count": 0,
            "total_count": 0,
            "compliance_progress": 0
        }
    }
    for data in data_obj.values():
        for rec in data.keys():
            for obj in data[rec].keys():
                if obj == "fail_count_by_resource" or obj == "threat_count" or obj == "total_count" or obj == "compliance_progress":
                    response_dict[rec][obj] += data[rec][obj]
                else:
                    response_dict[rec][obj] = data[rec][obj]
    return response_dict


def validate_api(secret_key):
    validation_payload = {'api_key': secret_key}
    response = ApiResponse(validation_payload,
                           'validate_api_token').fetch_response()
    _status, response = ApiResponse.check_response(response)
    if _status:
        if response['message'] != "success":
            return False
        return True
    else:
        return False
    


def get_api_validation(request):
    api_validation_status = False
    ci = ConnectionInfo.objects.filter(name__iexact='Kumolus Kit Creds').first()
    updating_hostname = False
    req_content = request.POST.get('body', None)
    req_payload = json.loads(req_content) if req_content else {}
    if req_payload.get("web_host", None) and req_payload.get("api_key", None):
        updating_hostname = True
    
    if ci and not updating_hostname:
        if hasattr(ci, "description"):
            if ci.description:
                kumo_des = json.loads(ci.description)
                if not kumo_des["api_validation"] or not kumo_des.get("api_validation", None):
                    api_validation_status = validate_api(ci.password)
                    kumo_des["api_validation"] = api_validation_status
                    ci.description = json.dumps(kumo_des)
                    ci.save()
                    
            else:
                api_validation_status = validate_api(ci.password)
                kumo_des = {
                    "api_validation": api_validation_status
                }
                ci.description = json.dumps(kumo_des)
                ci.save()
            return kumo_des["api_validation"]
    else:
        payload = json.loads(request.POST.get('body'))
        web_host = payload['web_host']

        response = ApiResponse(payload, 'validate_api_token',
                                web_host=web_host).fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            if response['message'] != "success":
                api_validation_status = False
            api_validation_status = True
        else:
            api_validation_status = False

    return api_validation_status


def check_if_key_exists(key_id, file_location):
    if os.path.exists(file_location):
        with open(file_location, "r") as outfile:
            file_content = json.loads(outfile.read())
        return True if key_id in file_content else False
    return False

def get_custom_setting_dict():
    """
        Get all customized settings from the file
    """
    try:
        with open(CUSTOMIZATIONS_FILE_PATH, 'r') as f:
            settings = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        settings={}

    return settings


def get_custom_setting(key):
    """
        Get a customized settings from the file
    """

    settings = get_custom_setting_dict()

    return settings.get(key, None)


def update_custom_setting(key, value):
    """
        Add or update a customized setting in the file
    """

    settings = get_custom_setting_dict()
    if value:
        settings[key]=value
    else:
        if key in settings:
            del settings[key]

    # if the file does not exist, it will be created
    with open(CUSTOMIZATIONS_FILE_PATH, 'w') as f:
        json.dump(settings, f)

    return HttpResponse({'status': "success"})


def toggle_api_validation_status(status):
    ci = ConnectionInfo.objects.filter(name__iexact='Kumolus Kit Creds').first()
    if ci:
        if hasattr(ci, "description"):
            if ci.description:
                kumo_des = json.loads(ci.description)
            else:
                kumo_des = {}
        
            if kumo_des.get("api_validation", ""):
                kumo_des["api_validation"] = status
                ci.description = json.dumps(kumo_des)
                ci.save()
            else:   
                kumo_des.update({"api_validation": status})
                ci.description = json.dumps(kumo_des)
                ci.save()
    return
                
def is_aws_based_handler(resource_handler: ResourceHandler):
    rh = resource_handler.cast()
    # return isinstance(rh, AWSHandler) or isinstance(rh, AWSJITHandler)
    return rh.resource_technology.slug.startswith("aws")
