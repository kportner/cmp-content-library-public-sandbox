import json
import collections
import functools
import operator
import traceback
from datetime import (
    date,
    datetime,
    timedelta
)
from django.http import HttpResponse
from django.http import HttpResponse, JsonResponse

from utilities.decorators import json_view
from resourcehandlers.azure_arm.models import AzureARMHandler
from resourcehandlers.models import ResourceHandler
from xui.kumo_integration_kit.utils import (
    ApiResponse,
    check_for_cache,
    get_cache_data,
    set_cache_data,
    is_aws_based_handler
)
from utilities.logger import ThreadLogger


logger = ThreadLogger(__name__)


def generate_chart_data(api_data, name, dictionary, rh_type=None):
    """
    To struture the api response data in desired format
    """
    dictionary[name] = {"labels": [], "values": []}
    if rh_type == "AZURE":
        for row in api_data["chart_data"]["categories"][0]["category"]:
            dictionary[name]["labels"].append(row["label"])
            dictionary[name]["values"].append(row["value"])
    else:
        for row in api_data["chart_data"]:
            dictionary[name]["labels"].append(row["label"])
            dictionary[name]["values"].append(row["value"])


@json_view
def get_security_trends(request):
    """To get the security trends data

    Args:
        request (get request): get request to get data.

    Returns:
        dict: Security trend's data.
    """

    payload = json.loads(request.POST.get('body'))
    rh = ResourceHandler.objects.get(id=payload['rh_id']).cast()
    if is_aws_based_handler(rh):
        response = ApiResponse(
                        payload,
                        'aws_security_trends',
                        request_type="POST").fetch_response()
    elif isinstance(rh, AzureARMHandler):
        response = ApiResponse(
                        payload,
                        'azure_security_trends',
                        request_type="POST").fetch_response()
    _status, response = ApiResponse.check_response(response)
    if _status:
        return JsonResponse({'result': response})
    
    return JsonResponse({'result': {"message": "No normal adapter found."}})


@json_view
def get_compliance_report(request):
    """To get the compliance report data

    Args:
        request (get request): get request to get data.

    Returns:
        dict: Compliance report's data.
    """

    payload = json.loads(request.GET.get('body'))
    rh = ResourceHandler.objects.get(id=payload['rh_id']).cast()
    if is_aws_based_handler(rh):
        response = ApiResponse(
                    payload,
                    'aws_compliance_report').fetch_response()
    elif isinstance(rh, AzureARMHandler):
        response = ApiResponse(
                    payload,
                    'azure_compliance_report').fetch_response()
        
    _status, response = ApiResponse.check_response(response)
    if _status:
        return JsonResponse({'result': response})
    
    return JsonResponse({'result': {"message": "No normal adapter found."}})


@json_view
def get_compliance_overview(request):
    """To get the compliance overview data

    Args:
        request (get request): get request to get data.

    Returns:
        dict: Compliance overview's data.
    """

    payload = json.loads(request.GET.get('body'))
    rh = ResourceHandler.objects.get(id=payload['rh_id']).cast()
    if is_aws_based_handler(rh):
        response = ApiResponse(
                        payload,
                        'aws_compliance_overview').fetch_response()
    elif isinstance(rh, AzureARMHandler):
        response = ApiResponse(
                        payload,
                        'azure_compliance_overview').fetch_response()
        
    _status, response = ApiResponse.check_response(response)
    if _status:
        return JsonResponse({'result': response})
    
    return JsonResponse({'result': {"message": "No normal adapter found."}})