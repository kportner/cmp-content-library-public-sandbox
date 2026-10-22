import json
import os
import ast
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
import copy
from utilities.decorators import json_view
from resourcehandlers.awsjit.models import AWSJITHandler
from resourcehandlers.azure_arm.models import AzureARMHandler
from resourcehandlers.gcp.models import GCPHandler
from resourcehandlers.models import ResourceHandler
from settings import PROSERV_DIR
from xui.kumo_integration_kit.constants import (
    UNUSED_SERVICES,
    UNOPTIMIZED_SERVICES,
)
from xui.kumo_integration_kit.utils import (
    ApiResponse,
    check_for_cache,
    get_cache_data,
    set_cache_data,
    write_to_file,
    check_if_key_exists,
    is_aws_based_handler
)
from utilities.logger import ThreadLogger


logger = ThreadLogger(__name__)


def payload_check(func):
    def wrapper(request):
        payload = json.loads(request.body)
        rh = ResourceHandler.objects.get(id=payload['rh_id']).cast()
        # if isinstance(rh, GCPHandler):
        #     request._body.decode('utf-8')["provider_account_id"] \
        #         =
        data = getattr(request, '_body', request.body)
        # request._body["provider_account_id"] \
        #     = ast.literal_eval(data["provider_account_id"])
        func(request)
    return wrapper



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
def charts_data_rh_json(request):
    """
    To get the cost reporting data from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having data
    """
    payload = json.loads(request.body)
    rh = ResourceHandler.objects.get(id=payload['rh_id']).cast()
    charts_data = {}
    output_data_dict = {}
    rh_file_name = f'chart_data_{payload["rh_id"]}'

    should_fetch = check_for_cache(rh_file_name)
    logger.info(f"Get cached data for {rh_file_name} ======> {should_fetch}")

    if should_fetch:
        if is_aws_based_handler(rh):
            response = ApiResponse(
                payload,
                'report_dashboard').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status and response.get('response', None):
                api_data = response["response"]["report_dashboard"]

                for x in api_data:
                    if 'overview_data' in list(x.keys()):
                        charts_data['thirty_days_ri_overview'] = {
                            "used_reservations": x['overview_data']['utilization']['grid_data']['used_reservations'],
                            "unused_reservations": x['overview_data']['utilization']['grid_data']['unused_reservations'],
                        }
                    else:
                        charts_data['thirty_days_ri_overview'] = {
                            "used_reservations": 0,
                            "unused_reservations": 0
                        }
            else:
                charts_data['thirty_days_ri_overview'] = {
                    "used_reservations": 0,
                    "unused_reservations": 0
                }

            response = ApiResponse(
                payload,
                'misc_details').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                charts_data['month_to_date'] = response['month_to_date_details']['month_to_date_cost']
                charts_data['year_to_date'] = response['year_to_date_details']['year_to_date_cost']
                charts_data['year_forecast'] = response['year_to_date_details']['current_year_forecast']
            else:
                charts_data['month_to_date'] = 0
                charts_data['year_to_date'] = 0
                charts_data['year_forecast'] = 0

            # payload['type'] = 'last_30_days'
            # response = ApiResponse(
            #     payload,
            #     'cost_by_days').fetch_response()
            exact_date = datetime.now() - timedelta(30)
            sd = datetime.strftime(exact_date, '%d-%m-%Y')
            exact_date = datetime.now() - timedelta(1)
            ed = datetime.strftime(exact_date, '%d-%m-%Y')

            extra_payload = {
                "report": {
                    "daily": True,
                    "date_range": {
                        "start_date": sd,
                        "end_date": ed
                    },
                    "tags": {},
                    "type": "cost_report",
                    "account": [],
                    "service": [],
                    "region": [],
                    "usage_type": [],
                    "operation": [],
                    "monthly": False,
                    "multi_series": False,
                    "select_metric": "unblended",
                    "product_family": [],
                    "is_upfront_reservation_charges": True,
                    "is_support_charges": True,
                    "is_other_subscription_charges": True,
                    "is_credit": False,
                    "rh_id": 4,
                    "dimensions": ["date"],
                    "metrics": ["unblended"],
                    "provider_account_id": payload["provider_account_id"]
                }
            }
            response = ApiResponse(
                extra_payload,
                'get_chart_data',
                request_type="POST").fetch_response()

            _status, response = ApiResponse.check_response(response)
            if _status:
                if isinstance(response, str):
                    charts_data['message'] = "no billing adapter"
                else:
                    response = response['response']
                    charts_data["cost_by_day_chart_data"] = {
                        "labels": [],
                        "values": [],
                    }

                    for row in response["chart_data"]["categories"][0]["category"]:
                        charts_data["cost_by_day_chart_data"]["labels"].append(row["label"])
                        charts_data["cost_by_day_chart_data"]["values"].append(row["value"])

                    charts_data['average_daily_cost'] = (sum(
                            charts_data["cost_by_day_chart_data"]["values"])/30)

                    charts_data['previous_spend'] = charts_data["cost_by_day_chart_data"]["values"][-1] \
                                                    if charts_data["cost_by_day_chart_data"]["values"] else 0

            # if response:
            #     if 'message' in response.json():
            #         charts_data['message'] = "no billing adapter"
            #     else:
            #         generate_chart_data(
            #             response.json(), 'cost_by_day_chart_data', charts_data)
            #         charts_data['average_daily_cost'] = response.json()[
            #             'grid_data']['avarage_cost']
            #         charts_data['previous_spend'] = response.json()[
            #             'grid_data']['previous_spend']
            else:
                charts_data['average_daily_cost'] = 0
                charts_data['previous_spend'] = 0
                charts_data['cost_by_day_chart_data'] = {}

            payload['type'] = 'last_12_months'
            response = ApiResponse(
                payload,
                'cost_by_months').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                generate_chart_data(
                    response, 'cost_by_year_chart_data', charts_data)
                charts_data['average_monthly_cost'] = response[
                    'grid_data']['avarage_cost']
            else:
                charts_data['average_monthly_cost'] = 0
                charts_data['cost_by_year_chart_data'] = {}

            payload['type'] = 'last_30_days'
            response = ApiResponse(
                payload,
                'cost_by_services').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                generate_chart_data(
                    response, 'cost_by_service_chart_data', charts_data)
                charts_data['total_spend'] = response['grid_data']
            else:
                charts_data['total_spend'] = 0
                charts_data['cost_by_service_chart_data'] = {}

            charts_data['day_cost_diff'] = 0
            charts_data['month_cost_diff'] = 0
            # To calculate the diff in yesterdays cost day on day
            if charts_data['cost_by_day_chart_data'] and 'values' in charts_data['cost_by_day_chart_data'].keys():
                if charts_data['cost_by_day_chart_data']['values']:
                    try:
                        day_before_yesterday_cost = charts_data['cost_by_day_chart_data']['values'][-2]
                        charts_data['day_cost_diff'] \
                            = ((charts_data['previous_spend']/day_before_yesterday_cost)-1) * 100
                    except ZeroDivisionError:
                        charts_data['day_cost_diff'] = 0

            if charts_data['cost_by_year_chart_data'] and 'values' in charts_data['cost_by_year_chart_data'].keys():
                if charts_data['cost_by_year_chart_data']['values']:
                    if len(charts_data['cost_by_year_chart_data']['values']) > 1:
                        try:
                            # To calculate the diff in month wise cost
                            last_month_cost = charts_data['cost_by_year_chart_data']['values'][-2]
                            charts_data['month_cost_diff'] \
                                = ((charts_data['month_to_date']/last_month_cost)-1) * 100
                        except ZeroDivisionError:
                            charts_data['month_cost_diff'] = 0
                    else:
                        charts_data['month_cost_diff'] = 100

            if all(map((lambda value: True if value else False), (
                charts_data["month_to_date"], charts_data["year_to_date"],
                charts_data["year_forecast"], charts_data["average_daily_cost"],
                charts_data["previous_spend"], charts_data["cost_by_day_chart_data"],
                charts_data["average_monthly_cost"],
                charts_data["cost_by_year_chart_data"], charts_data["total_spend"],
                charts_data["cost_by_service_chart_data"]))):
                set_cache_data(rh_file_name, charts_data)

        elif isinstance(rh, AzureARMHandler):
            response = ApiResponse(
                payload,
                'azure_misc_details').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                charts_data['month_to_date'] = response['month_to_date_details']['month_to_date_cost']
                charts_data['year_to_date'] = response['year_to_date_details']['year_to_date_cost']
                charts_data['year_forecast'] = response['year_to_date_details']['current_year_forecast']
            else:
                charts_data['month_to_date'] = 0
                charts_data['year_to_date'] = 0
                charts_data['year_forecast'] = 0

            payload['type'] = 'last_30_days'
            response = ApiResponse(
                payload,
                'azure_cost_by_days').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                if isinstance(response, str):
                    charts_data['message'] = "no billing adapter"
                else:
                    generate_chart_data(
                        response, 'cost_by_day_chart_data', charts_data)
                    charts_data['average_daily_cost'] = response[
                        'grid_data']['avarage_cost']
                    charts_data['previous_spend'] = response[
                        'grid_data']['previous_spend']
            else:
                charts_data['average_daily_cost'] = 0
                charts_data['previous_spend'] = 0
                charts_data['cost_by_day_chart_data'] = {}

            payload['type'] = 'last_12_months'
            response = ApiResponse(
                payload,
                'azure_cost_by_months').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                generate_chart_data(
                    response, 'cost_by_year_chart_data', charts_data)
                charts_data['average_monthly_cost'] = response[
                    'grid_data']['avarage_cost']
            else:
                charts_data['average_monthly_cost'] = 0
                charts_data['cost_by_year_chart_data'] = {}

            payload['type'] = 'last_30_days'
            response = ApiResponse(
                payload,
                'azure_cost_by_services').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                generate_chart_data(
                    response, 'cost_by_service_chart_data', charts_data)
                charts_data['total_spend'] = response['grid_data']
            else:
                charts_data['total_spend'] = 0
                charts_data['cost_by_service_chart_data'] = {}

            charts_data['day_cost_diff'] = 0
            charts_data['month_cost_diff'] = 0

            if charts_data['cost_by_day_chart_data'] and 'values' in charts_data['cost_by_day_chart_data'].keys():
                if charts_data['cost_by_day_chart_data']['values']:
                    try:
                        # To calculate the diff in yesterdays cost day on day
                        day_before_yesterday_cost = charts_data['cost_by_day_chart_data']['values'][-2]
                        charts_data['day_cost_diff'] \
                            = ((charts_data['previous_spend']/day_before_yesterday_cost)-1) * 100
                    except ZeroDivisionError:
                        charts_data['day_cost_diff'] = 0

            if charts_data['cost_by_year_chart_data'] and 'values' in charts_data['cost_by_year_chart_data'].keys():
                if charts_data['cost_by_year_chart_data']['values']:
                    if len(charts_data['cost_by_year_chart_data']['values']) > 1:
                        try:
                            # To calculate the diff in month wise cost
                            last_month_cost = charts_data['cost_by_year_chart_data']['values'][-2]
                            charts_data['month_cost_diff'] \
                                = ((charts_data['month_to_date']/last_month_cost)-1) * 100
                        except ZeroDivisionError:
                            charts_data['month_cost_diff'] = 0
                    else:
                        charts_data['month_cost_diff'] = 100

            if all(map((lambda value: True if value else False), (
                charts_data["month_to_date"], charts_data["year_to_date"],
                charts_data["year_forecast"], charts_data["average_daily_cost"],
                charts_data["previous_spend"], charts_data["cost_by_day_chart_data"],
                charts_data["average_monthly_cost"], charts_data["cost_by_year_chart_data"],
                charts_data["total_spend"], charts_data["cost_by_service_chart_data"]))):
                set_cache_data(rh_file_name, charts_data)

        elif isinstance(rh, GCPHandler):
            response = ApiResponse(
                payload,
                'gcp_misc_details').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                charts_data['month_to_date'] = response['month_to_date_details']['month_to_date_cost']
                charts_data['year_to_date'] = response['year_to_date_details']['year_to_date_cost']
                charts_data['year_forecast'] = response['year_to_date_details']['current_year_forecast']
            else:
                charts_data['month_to_date'] = 0
                charts_data['year_to_date'] = 0
                charts_data['year_forecast'] = 0

            charts_data['average_daily_cost'] = 0
            charts_data['previous_spend'] = 0
            charts_data['cost_by_day_chart_data'] = {}

            payload['type'] = 'last_30_days'
            response = ApiResponse(
                payload,
                'gcp_cost_by_days').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                if isinstance(response, str):
                    charts_data['message'] = "no billing adapter"
                else:
                    generate_chart_data(
                        response, 'cost_by_day_chart_data', charts_data)
                    charts_data['average_daily_cost'] = response[
                        'grid_data']['avarage_cost']
                    charts_data['previous_spend'] = response[
                        'grid_data']['previous_spend']

            charts_data['average_monthly_cost'] = 0
            charts_data['cost_by_year_chart_data'] = {}

            payload['type'] = 'last_12_months'
            response = ApiResponse(
                payload,
                'gcp_cost_by_months').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                generate_chart_data(
                    response, 'cost_by_year_chart_data', charts_data)
                charts_data['average_monthly_cost'] = response[
                    'grid_data']['avarage_cost']

            charts_data['total_spend'] = 0
            charts_data['cost_by_service_chart_data'] = {}

            payload['type'] = 'last_30_days'
            response = ApiResponse(
                payload,
                'gcp_cost_by_services').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                generate_chart_data(
                    response, 'cost_by_service_chart_data', charts_data)
                charts_data['total_spend'] = response['grid_data']

            charts_data['day_cost_diff'] = 0
            charts_data['month_cost_diff'] = 0

            if charts_data['cost_by_day_chart_data'] and 'values' in charts_data['cost_by_day_chart_data'].keys():
                if charts_data['cost_by_day_chart_data']['values']:
                    try:
                        # To calculate the diff in yesterdays cost day on day
                        day_before_yesterday_cost = charts_data['cost_by_day_chart_data']['values'][-2]
                        charts_data['day_cost_diff'] \
                            = ((charts_data['previous_spend']/day_before_yesterday_cost)-1) * 100
                    except ZeroDivisionError:
                        charts_data['day_cost_diff'] = 0

            if charts_data['cost_by_year_chart_data'] and 'values' in charts_data['cost_by_year_chart_data'].keys():
                if charts_data['cost_by_year_chart_data']['values']:
                    if len(charts_data['cost_by_year_chart_data']['values']) > 1:
                        try:
                            # To calculate the diff in month wise cost
                            last_month_cost = charts_data['cost_by_year_chart_data']['values'][-2]
                            charts_data['month_cost_diff'] \
                                = ((charts_data['month_to_date']/last_month_cost)-1) * 100
                        except ZeroDivisionError:
                            charts_data['month_cost_diff'] = 0
                    else:
                        charts_data['month_cost_diff'] = 100

            if all(map((lambda value: True if value else False), (
                charts_data["month_to_date"], charts_data["year_to_date"],
                charts_data["year_forecast"], charts_data["average_daily_cost"],
                charts_data["previous_spend"], charts_data["cost_by_day_chart_data"],
                charts_data["average_monthly_cost"], charts_data["cost_by_year_chart_data"],
                charts_data["total_spend"], charts_data["cost_by_service_chart_data"]))):
                set_cache_data(rh_file_name, charts_data)
    else:
        charts_data = get_cache_data(rh_file_name)

    if is_aws_based_handler(rh):
        output_data_dict.update({
            "used_reservations": round(charts_data['thirty_days_ri_overview']['used_reservations'] or 0, 2),
            "unused_reservations": round(charts_data['thirty_days_ri_overview']['unused_reservations'] or 0, 2),
        })

    if 'message' in charts_data:
        output_data_dict.update({'message': 'no billing adapter'})

    output_data_dict.update({
        "cost_by_service_chart_data": charts_data['cost_by_service_chart_data'],
        "cost_by_day_chart_data": charts_data['cost_by_day_chart_data'],
        "cost_by_year_chart_data": charts_data['cost_by_year_chart_data'],
        "yesterday_spend": round(charts_data['previous_spend'] or 0, 2),
        "total_spend": round(charts_data['total_spend'] or 0, 2),
        "month_to_date": round(charts_data['month_to_date'] or 0, 2),
        "year_to_date": round(charts_data['year_to_date'] or 0, 2),
        "year_forecast": round(charts_data['year_forecast'] or 0, 2),
        "day_cost_diff": round(charts_data['day_cost_diff'] or 0, 2),
        "month_cost_diff": round(charts_data['month_cost_diff'] or 0, 2),
    })

    return output_data_dict


@json_view
def cost_adviser_overview_for_rh(request):
    """
    To get the service adviser data from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having data
    """
    charts_data = {}
    payload = json.loads(request.body)
    rh = ResourceHandler.objects.get(id=payload['rh_id']).cast()

    response = ApiResponse(
                payload,
                'service_type_count').fetch_response()
    _status, response = ApiResponse.check_response(response)
    if _status:
        if isinstance(response, str):
            charts_data['service_type_summary'] = []
        else:
            charts_data['service_type_summary'] = response['service_type_count']
    else:
        charts_data['service_type_summary'] = []

    if is_aws_based_handler(rh):

        response = ApiResponse(
                payload,
                'ec2_rightsize').fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            charts_data['service_type_summary'].append({
                'type': 'ec2_right_sizings',
                'count': response['meta_data']['instance_count'],
                'cost_sum': response['meta_data']['total_saving'],
            })
        else:
            pass

        response = ApiResponse(
                payload,
                'ignored_services').fetch_response()
        _status, response = ApiResponse.check_response(response)
        if _status:
            charts_data['service_type_summary'].append({
                "type": "ignore_services",
                "count": response.get("count", 0),
                "cost_sum": response.get("service_cost_sum", 0),
            })
        else:
            pass

    cost_efficiency = {}
    format_cost_efficiency_data(charts_data, cost_efficiency)

    return cost_efficiency


def format_cost_efficiency_data(charts_data, cost_efficiency):
    """
    To consolidate the unused, unoptimized and ignored services
    """
    unused_cost_sum = 0
    unused_count = 0
    unoptimized_cost_sum = 0
    unoptimized_count = 0
    ignored_cost_sum = 0
    ignored_count = 0
    for data in charts_data['service_type_summary']:
        if data['type'] in UNUSED_SERVICES:
            unused_count = unused_count + data['count']
            unused_cost_sum = unused_cost_sum + float(data['cost_sum'])

        elif data['type'] in UNOPTIMIZED_SERVICES:
            unoptimized_count = unoptimized_count + data['count']
            unoptimized_cost_sum = unoptimized_cost_sum + \
                float(data['cost_sum'])

        elif data['type'] == 'ignore_services':
            ignored_cost_sum = float(data['cost_sum'])
            ignored_count = data['count']

    cost_efficiency['data'] = ({
        'unused_count': unused_count,
        'unused_cost_sum': unused_cost_sum,
        'unoptimized_count': unoptimized_count,
        'unoptimized_cost_sum': unoptimized_cost_sum,
        'ignored_count': ignored_count,
        'ignored_cost_sum': ignored_cost_sum,
        'potential_benefit': (unused_cost_sum
                              + unoptimized_cost_sum
                              + ignored_cost_sum)
    })


@json_view
def aws_ri_recommendations_for_rh_json(request):
    """
    To fetch the AWS RI recommendation data from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having data
    """
    payload = json.loads(request.body)

    response = ApiResponse(
        payload,
        'aws_ri_purchase_recommendations',
        request_type="POST").fetch_response()
    _status, response = ApiResponse.check_response(response)
    if _status:
        response = response['summary']

    return response


@json_view
def azure_ri_recommendations_for_rh_json(request):
    """
    To fetch the Azure RI recommendation data from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having data
    """
    payload = json.loads(request.body)

    response = ApiResponse(
        payload,
        'azure_ri_purchase_recommendations'
        ).fetch_response()
    _status, response = ApiResponse.check_response(response)

    return response


# To fetch all regions/services/tags/accounts
@json_view
def filtration_menu_rh_json(request):
    """
    To fetch the filteration menu for filters from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having data
    """
    payload = json.loads(request.body)
    rh = ResourceHandler.objects.get(id=payload['rh_id']).cast()
    rh_file_name = f'filteration_data_{payload["rh_id"]}'

    should_fetch = check_for_cache(rh_file_name)
    logger.info(f"Get cached data for {rh_file_name} ======> {should_fetch}")
    if should_fetch:
        if is_aws_based_handler(rh):
            response = ApiResponse(
                payload, 'filtration_menu'
                ).fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                response = response['filteration_menu']["cost_report"]["AWS"]
                if not 'Services' in response:
                    response = {'Services': ''}
            else:
                response = {'Services': ''}

            if response["Services"]:
                set_cache_data(rh_file_name, response)

        elif isinstance(rh, GCPHandler):
            response = ApiResponse(
                payload, 'gcp_filtration_menu',
                request_type="POST").fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                response = response['gcp_filteration_menu']["gcp_cost_report"]["GCP"]
                if not 'Projects' in response:
                    response = {'Projects': ''}
                if not 'Services' in response:
                    response = {'Services': ''}
                if not 'Locations' in response:
                    response = {'Locations': ''}
                if not 'Skus' in response:
                    response = {'Skus': ''}
            else:
                response = {'Projects': ''}
                response = {'Services': ''}
                response = {'Locations': ''}
                response = {'Skus': ''}

            response_label_keys = ApiResponse(
                payload, 'gcp_get_label_keys'
                ).fetch_response()
            _status, response_label_keys = ApiResponse.check_response(response_label_keys)
            if _status:
                response['Labels'] = response_label_keys
            else:
                response = {'Labels': ''}

            if response["Projects"] and response["Services"] \
                and response["Locations"] and response["Skus"]:
                set_cache_data(rh_file_name, response)

        elif isinstance(rh, AzureARMHandler):
            response = ApiResponse(
                payload,
                'azure_filtration_menu').fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                response = response['azure_filteration_menu']["azure_cost_report"]["Azure"]
                if not 'Services' in response:
                    response = {'Services': ''}
            else:
                response = {'Services': ''}

            response_resource_group = ApiResponse(
                payload, 'azure_resource_groups',
                request_type="POST").fetch_response()
            _status, response_resource_group = ApiResponse.check_response(response_resource_group)
            if _status:
                response['ResourceGs'] = response_resource_group
            else:
                response = {'ResourceGs': ''}

            response_tag_keys = ApiResponse(
                payload, 'azure_tag_keys'
                ).fetch_response()
            _status, response_tag_keys = ApiResponse.check_response(response_tag_keys)
            if _status:
                response['Tags'] = response_tag_keys
            else:
                response = {'Tags': ''}

            if response["Services"] and response["ResourceGs"] and response["Tags"]:
                set_cache_data(rh_file_name, response)
    else:
        response = get_cache_data(rh_file_name)

    if isinstance(rh, AWSJITHandler):
        wrapper = rh.cast().get_api_wrapper()
        rh_regions = wrapper.get_all_regions()
        response["Regions"] = {region.get("display") : region.get("name") 
                               for region in rh_regions}
    return response


@json_view
def spend_details_for_rh_json(request):
    """
    To fetch last 30 days cost/spend data from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having data
    """
    chart_data = {}
    complete_response = {}
    payload = json.loads(request.body)
    copy_payload = copy.deepcopy(payload)
    
    pop_from_payload = ["tab_name"]
    pop_from_report_dict = ["provider_account_id", "rh_id"]
    
    actual_payload = {key: copy_payload[key] for key in copy_payload if key not in pop_from_payload}
    report = {key: copy_payload["report"][key] for key in copy_payload["report"] if key not in pop_from_report_dict}
    actual_payload['report'] = report
    
    rh = ResourceHandler.objects.get(id=payload['report']['rh_id']).cast()
    rh_type_slug = rh.resource_technology.type_slug \
        if rh.resource_technology.type_slug != 'awsjit' else 'aws'
    src = os.path.join(PROSERV_DIR, "cached_xui_data", "kumo_integration_kit", "csmp_data")
    if not os.path.exists(src):
        os.makedirs(src)
            
    file_location \
        = os.path.join(src, f"{rh_type_slug}_spend.json")
    default_payload_file = os.path.join(src, f"default_payload.json")
    refresh_data = False
    if os.path.exists(default_payload_file):
        with open(default_payload_file, "r") as payload_outfile:
            payload_object = payload_outfile.read()
        default_payload_response = json.loads(payload_object)
        default_payload_response = default_payload_response[rh_type_slug][payload['tab_name']]
        saved_default_payload, actual_payload = json.dumps(default_payload_response, sort_keys=True), json.dumps(actual_payload, sort_keys=True)
        if not saved_default_payload == actual_payload:
            refresh_data = True
    response = {}
    if os.path.exists(file_location) and not refresh_data:
        with open(file_location, "r") as outfile:
            json_object = outfile.read()
        response = json.loads(json_object)

        if response:
            response = response.get(f"{rh.id}-{payload['tab_name']}", "")
            if response:
                response = response.get("report", "") \
                    if rh_type_slug == "azure_arm" \
                    else response.get("response", "")

    if not os.path.exists(file_location) or refresh_data or not response:
        if is_aws_based_handler(rh):
            response = ApiResponse(
                    payload,
                    'get_chart_data',
                    request_type="POST").fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                if not os.path.exists(file_location) or not check_if_key_exists(f"{rh.id}-{payload['tab_name']}", file_location):
                    write_to_file(f"{rh.id}-{payload['tab_name']}",
                                file_location, response)
                response = response['response']

        elif isinstance(rh, AzureARMHandler):
            response = ApiResponse(
                    payload,
                    'azure_get_chart_data',
                    request_type="POST").fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                if not os.path.exists(file_location) or not check_if_key_exists(f"{rh.id}-{payload['tab_name']}", file_location):
                    write_to_file(f"{rh.id}-{payload['tab_name']}",
                                file_location, response)
                response = response['report']

        elif isinstance(rh, GCPHandler):
            response = ApiResponse(
                    payload,
                    'gcp_get_chart_data',
                    request_type="POST").fetch_response()
            _status, response = ApiResponse.check_response(response)
            if _status:
                if not os.path.exists(file_location) or not check_if_key_exists(f"{rh.id}-{payload['tab_name']}", file_location):
                    write_to_file(f"{rh.id}-{payload['tab_name']}",
                                file_location, response)
                response = response['response']
    else:
        _status = True
    
    if _status and response:
        if (payload['report']['multi_series']):
            multi_series_chart = []
            for x in response["chart_data"]["dataset"]:
                data = []
                for y in (x['data']):
                    data.append(y['value'])
                serie_name = x['seriesname'] if 'seriesname' in x else 'Others'
                multi_series_chart.append(
                    {'name': serie_name, 'data': data})

            chart_data = {}
            chart_data = {"labels": [], "values": multi_series_chart,
                        "total_cost": response['grid_data']['total']}
            for row in response["chart_data"]["categories"][0]["category"]:
                chart_data["labels"].append(row["label"])

            today_yesterday = [
                datetime.today().strftime('%d %b %Y'),
                (date.today() - timedelta(days=1)).strftime('%d %b %Y')
            ]
            multiseries_data_list = [
                data_list['data'][-1] if chart_data['labels'][-1] in today_yesterday else 0 for data_list in chart_data['values']]
            
            multiseries_data_list = [data if data is not None else 0 for data in multiseries_data_list]

            chart_data['previous_spend'] = sum(
                multiseries_data_list) if multiseries_data_list else 0

            if payload['report']['monthly'] == True:
                chart_data['average_daily_cost'] = (chart_data['total_cost'] / \
                    payload["total_months"])/30 if chart_data['labels'] else 0

                chart_data['average_monthly_cost'] = chart_data['total_cost'] / \
                    payload["total_months"] if chart_data['labels'] else 0

            else:
                chart_data['average_daily_cost'] = chart_data['total_cost'] / \
                    payload["total_days"]

                chart_data['average_monthly_cost'] = 30 * chart_data['total_cost'] / \
                    payload["total_days"]

        else:
            chart_data = {
                "labels": [],
                "values": [],
                "total_cost": response['grid_data']['total']
            }
            for row in response["chart_data"]["categories"][0]["category"]:
                chart_data["labels"].append(row["label"])
                chart_data["values"].append(row["value"])

            chart_data['previous_spend'] = chart_data["values"][-1] if chart_data["values"] else 0

            if payload['report']['monthly'] == True:
                chart_data['average_daily_cost'] = (sum(
                    chart_data["values"])/payload["total_months"])/30 if chart_data["values"] else 0

                chart_data['average_monthly_cost'] = sum(
                    chart_data["values"])/payload["total_months"] if chart_data["values"] else 0

            else:
                chart_data['average_daily_cost'] = (sum(
                    chart_data["values"])/payload["total_days"])

                chart_data['average_monthly_cost'] = 30 * (sum(
                    chart_data["values"])/payload["total_days"])

    return chart_data


@json_view
def forecast_for_rh_json(request):
    """
    To fetch the forecasting values in case of future dates
    are selected

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having data
    """
    charts_data = {"labels": [], "values": []}
    payload = json.loads(request.body)
    rh = ResourceHandler.objects.get(id=payload['report']['rh_id']).cast()

    if is_aws_based_handler(rh):
        response = ApiResponse(payload, 'get_aws_forecast',
                               request_type="POST").fetch_response()
        _status, response = ApiResponse.check_response(response)

    elif isinstance(rh, AzureARMHandler):
        response = ApiResponse(payload, 'get_azure_forecast',
                               request_type="POST").fetch_response()
        _status, response = ApiResponse.check_response(response)

    elif isinstance(rh, GCPHandler):
        response = ApiResponse(payload, 'gcp_get_forecast',
                               request_type="POST").fetch_response()
        _status, response = ApiResponse.check_response(response)

    if _status:
        # To get the remaining days and hours forecast
        start_date = date.today()
        end_date_string = payload['report']['date_range']['end_date']
        end_date = datetime.strptime(end_date_string, "%d-%m-%Y").date()
        starting_date_string = payload['report']['date_range']['start_date']
        starting_date = datetime.strptime(starting_date_string, "%d-%m-%Y").date()

        while start_date <= end_date:
            if start_date >= starting_date:
                charts_data["labels"].append(start_date.strftime("%d %b %Y"))
                if start_date == date.today():
                    today = datetime.now()
                    remaining_hours_of_day = round(
                        24 - (today.hour + (today.minute/60)), 2)
                    value = 24 * response['hour_forecast_value']
                    charts_data["values"].append(value)
                else:
                    charts_data["values"].append(response['day_forecast_value'])
            start_date += timedelta(days=1)

        if payload['report']['monthly']:
            forecast_data = {'labels': [], 'values': []}

            for forecast_month in payload['report']['month_labels']:
                total_cost = 0

                values_indexes = [index for index, forecast_date in enumerate(
                    charts_data['labels']) if forecast_month[0:3] in forecast_date]
                total_cost = sum([charts_data['values'][indexes]
                                for indexes in values_indexes])
                forecast_data['labels'].append(forecast_month)
                forecast_data['values'].append(total_cost)

            return forecast_data

    return charts_data


@json_view
def get_resource_name(request):
    """
    To fetch the Azure tags from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having data
    """
    payload = json.loads(request.body)

    response = ApiResponse(payload, 'azure_resource_names',
                           request_type="POST").fetch_response()
    _status, response = ApiResponse.check_response(response)

    return response


@json_view
def get_tag_values(request):
    """
    To fetch the Azure tag values for selected tag from CSMP

    Args:
        request (http request): request having various params

    Returns:
        dict: Python dictionary having data
    """
    payload = json.loads(request.body)
    rh = ResourceHandler.objects.get(id=payload['rh_id']).cast()

    if isinstance(rh, AzureARMHandler):
        response = ApiResponse(
            payload,
            'azure_tag_values').fetch_response()
        _status, response = ApiResponse.check_response(response)

    elif isinstance(rh, GCPHandler):
        response = ApiResponse(
            payload,
            'gcp_get_label_values').fetch_response()
        _status, response = ApiResponse.check_response(response)

    return response
