import json
import traceback

from resourcehandlers.awsjit.models import AWSJITHandler
from resourcehandlers.azure_arm.models import AzureARMHandler
from resourcehandlers.gcp.models import GCPHandler
from resourcehandlers.models import ResourceHandler
from xui.kumo_integration_kit.utils import ApiResponse, is_aws_based_handler
from utilities.decorators import json_view
from django.http import HttpResponse


@json_view
def cost_efficiency_for_rh(request):
    """
    To get the service adviser data from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having data
    """
    charts_data = {}
    payload = json.loads(request.body)
    rh = ResourceHandler.objects.get(id=payload["rh_id"]).cast()
    charts_data["service_type_summary"] = []

    if is_aws_based_handler(rh):

        if (
            payload["service_type"] == "ec2_right_sizings"
            or payload["service_type"] == ""
        ):
            response = ApiResponse(payload, "ec2_rightsize").fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                charts_data["service_type_summary"].append(
                    {
                        "type": "ec2_right_sizings",
                        "count": response["meta_data"]["instance_count"],
                        "cost_sum": response["meta_data"]["total_saving"],
                    }
                )

        if (
            payload["service_type"] == "ignore_services"
            or payload["service_type"] == ""
        ):
            response = ApiResponse(payload, "ignored_services").fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                charts_data["service_type_summary"].append(
                    {
                        "type": "ignore_services",
                        "count": response.get("count", 0),
                        "cost_sum": response.get("service_cost_sum", 0),
                    }
                )

        response = ApiResponse(payload, "service_type_count").fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            charts_data["service_type_summary"] += response["service_type_count"]
        else:
            if not charts_data["service_type_summary"]:
                charts_data["message"] = response

    elif isinstance(rh, AzureARMHandler):
        response = ApiResponse(payload, "service_type_count").fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            charts_data["service_type_summary"] += response["service_type_count"]
        else:
            if not charts_data["service_type_summary"]:
                charts_data["message"] = response

    elif isinstance(rh, GCPHandler):
        response = ApiResponse(payload, "service_type_count").fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            charts_data["service_type_summary"] += response["service_type_count"]
        else:
            if not charts_data["service_type_summary"]:
                charts_data["message"] = response

    return charts_data


def csv_download_for_rh_json(request):
    """
    To download the services list from CSMP in csv format

    Args:
        request (http request): request having various params

    Returns:
        text/csv: csv data to be downloaded on the front-end
    """
    # payload = json.dumps(request.GET)
    # payload = json.loads(payload)
    payload = json.loads(request.body)
    if payload["ec2_status"] == True:
        response = ApiResponse(payload, "ec2_rightsizing_csv").fetch_response()
    else:
        response = ApiResponse(payload, "get_csv_download").fetch_response()

    _status, response = ApiResponse.check_response(response)
    if _status:
        csv_data = HttpResponse(response, content_type="text/csv")
        csv_data["Content-Disposition"] = "attachment; filename=recommendation.csv"
        return csv_data


@json_view
def region_list_for_rh_json(request):
    """
    To get the region and tag list from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having region and tag list
    """
    charts_data = {}
    payload = json.loads(request.body)
    rh = ResourceHandler.objects.get(id=payload["rh_id"]).cast()

    response = ApiResponse(payload, "get_regions_list").fetch_response()
    _status, response = ApiResponse.check_response(response)
    if _status:
        response = response.get("_embedded", None).get("account_region", None)
        if response:
            try:
                charts_data["regions_list"] = [
                    {
                        "enabled": regi["enabled"],
                        "region_id": regi["region_id"],
                        "region_name": regi["region_name"],
                        "adapter_type": regi["adapter_type"],
                        "code": regi["code"],
                    }
                    for regi in response
                    if regi["adapter_type"] == payload["handler_type"]
                ]
            except:
                charts_data["regions_list"] = []
        else:
            charts_data["regions_list"] = []
        
        if isinstance(rh, AWSJITHandler):
            wrapper = rh.cast().get_api_wrapper()
            rh_regions = wrapper.get_all_regions()
            region_code = [region.get("name") for region in rh_regions]
            charts_data["regions_list"] = [
                    {
                        "enabled": regi["enabled"],
                        "region_id": regi["region_id"],
                        "region_name": regi["region_name"],
                        "adapter_type": regi["adapter_type"],
                        "code": regi["code"],
                    }
                    for regi in response
                    if regi["code"] in region_code
                ]        
    else:
        charts_data["regions_list"] = []

    if isinstance(rh, GCPHandler):
        response = ApiResponse(payload, "gcp_get_label_keys").fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            charts_data["tags_list"] = response
        else:
            charts_data["tags_list"] = {}
    else:
        response = ApiResponse(payload, "get_tags_list").fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            charts_data["tags_list"] = response
        else:
            charts_data["tags_list"] = {}

    return charts_data


@json_view
def service_details_for_rh_json(request):
    """
    To get the detail of selected service type from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having service details of service type
    """
    payload = json.loads(request.body)

    response = ApiResponse(payload, "get_mapped_adapters").fetch_response()
    _status, response = ApiResponse.check_response(response)
    if _status:
        adapters_dict = {
            adapter["id"]: adapter["name"]
            for adapter in response["_embedded"]["adapter"]
        }

    response = ApiResponse(payload, "get_regions_list").fetch_response()
    _status, response = ApiResponse.check_response(response)
    if _status:
        response = response
        regions_dict = {
            region["region_id"]: region["region_name"]
            for region in response["_embedded"]["account_region"]
        }

    if payload["service_type"] == "ec2_right_sizings":
        response = ApiResponse(payload, "ec2_rightsize").fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            response = {"services": response["ec2_right_sizings"]}
        else:
            response = {"services": []}
    else:
        response = ApiResponse(payload, "get_service_type_details").fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            if payload["service_type"] == "amis":
                response_amis = {"services": []}
                for items in response["amis"]:
                    response_amis["services"].extend(items["results"])
                response = {"services": response_amis["services"]}

            for services in response["services"]:
                services["adapter_name"] = (
                    adapters_dict.get(services["adapter_id"], "N/A")
                    if "adapter_id" in services
                    else "N/A"
                )
                services["region_name"] = regions_dict[services["region_id"]]

    return response


@json_view
def ignored_services_list_for_rh_json(request):
    """
    To get the ignored services list from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having services list
    """
    payload = json.loads(request.body)

    # To fetch ignored service List with Details
    response = ApiResponse(payload, "ignored_services").fetch_response()
    _status, response = ApiResponse.check_response(response)

    return response


@json_view
def get_graph_data(request):
    """
    To get the graph data for selected service from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having graph data
    """
    payload = json.loads(request.body)

    response = ApiResponse(
        payload, "get_graph_data", request_type="POST"
    ).fetch_response()
    _status, response = ApiResponse.check_response(response)

    return response
