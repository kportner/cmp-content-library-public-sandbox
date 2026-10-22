import os
import json
import datetime
from django.http import HttpResponse, JsonResponse

from settings import PROSERV_DIR, DEBUG
from utilities.logger import ThreadLogger
from xui.kumo_integration_kit.utils import (
    get_all_compliance_data
)
from xui.kumo_integration_kit.constants import (
    UNUSED_SERVICES,
    UNOPTIMIZED_SERVICES
)
from xui.kumo_integration_kit.apis.admin import KumoKit
from jobs.models import RecurringJob

logger = ThreadLogger(__name__)


def get_cost_summary_widget_data():
    try:
        message_status = False
        last_job_status = ""
        piechart_data = {}
        barchart_data = {}
        piechart_series_data = []
        barchart_series_data = []
        last_job_status = ""
        recurring_job = RecurringJob.objects.filter(name__icontains="CSMP Dashboard Widget Data Caching")
        job_id = recurring_job.first().id if recurring_job else None
        first_run = False if recurring_job.first().spawned_jobs.all() else True
        if not first_run:
            last_job_status = recurring_job.first().spawned_jobs.all().last().status
            if last_job_status != "SUCCESS":
                last_updated = datetime.datetime.strftime(
                    recurring_job.first().spawned_jobs.all().last().updated_date, '%d/%m/%Y')
                last_job_status = last_updated
            else:
                last_job_status = ""

        src = os.path.join(PROSERV_DIR, "cached_xui_data", "kumo_integration_kit", "widget_data")
        isExist = os.listdir(src)

        if isExist:
            file_name = "cost_by_days_data.txt"
            file_location = os.path.join(src, file_name)
            with open(file_location) as f:
                data = json.load(f)

            kumokit = KumoKit()

            if hasattr(kumokit, "description"):
                if kumokit.description:
                    kumo_des = json.loads(kumokit.description)
                    if "currency_unified" not in kumo_des.keys():
                        message_status = "not unified"
                    else:
                        if not kumo_des["currency_unified"]:
                            message_status = "not unified"
                else:
                    message_status = "not unified"

            for cloud_providers in data:
                piechart_series_data.append(cloud_providers)
                piechart_data[cloud_providers] = 0
                for handlers in data[cloud_providers]:
                    values_list = [item["value"] for item in handlers["chart_data"]]
                    piechart_data[cloud_providers] += round(sum(values_list), 2)
                    current_labels = [item["label"] for item in handlers["chart_data"] if item["label"] not in barchart_series_data]
                    barchart_series_data.append(current_labels)
                    if cloud_providers not in barchart_data.keys():
                        barchart_data[cloud_providers] = {item["label"]:round(item["value"], 2) for item in handlers["chart_data"]}
                    else:
                        for item in handlers["chart_data"]:
                            if item["label"] in barchart_data[cloud_providers].keys():
                                barchart_data[cloud_providers][item["label"]] += round(item["value"], 2)
                            else:
                                barchart_data[cloud_providers][item["label"]] = round(item["value"], 2)
        else:
            message_status = True
            last_job_status = ""
        if piechart_data:
            piechart_data = dict(sorted(piechart_data.items(), key=lambda item: item[1], reverse=True))
        if barchart_series_data:
            result = [x for l in barchart_series_data for x in l]
            unique_series_data = list(set(result))
            barchart_series_data = sorted(unique_series_data, key=lambda x: datetime.datetime.strptime(x, '%d %b %Y'))
    except Exception as e:
        logger.info(e.args[0])
        message_status = True
        last_job_status = ""

    return piechart_data, barchart_data, barchart_series_data, \
        piechart_series_data, message_status, job_id, first_run, \
        last_job_status


def get_expensive_services_widget_data():
    try:
        response_data = []
        barchart_series_data = []
        message_status = False
        recurring_job = RecurringJob.objects.filter(name__icontains="CSMP Dashboard Widget Data Caching")
        job_id = recurring_job.first().id if recurring_job else None
        first_run = False if recurring_job.first().spawned_jobs.all() else True
        last_job_status = ""
        if not first_run:
            last_job_status = recurring_job.first().spawned_jobs.all().last().status
            if last_job_status != "SUCCESS":
                last_updated = datetime.datetime.strftime(
                    recurring_job.first().spawned_jobs.all().last().updated_date, '%d/%m/%Y')
                last_job_status = last_updated
            else:
                last_job_status = ""

        src = os.path.join(PROSERV_DIR, "cached_xui_data", "kumo_integration_kit", "widget_data")
        isExist = os.listdir(src)

        if isExist:
            file_name = "cost_by_services_data.txt"
            file_location = os.path.join(src, file_name)
            with open(file_location) as f:
                data = json.load(f)

            kumokit = KumoKit()

            if hasattr(kumokit, "description"):
                if kumokit.description:
                    kumo_des = json.loads(kumokit.description)
                    if "currency_unified" not in kumo_des.keys():
                        message_status = "not unified"
                    else:
                        if not kumo_des["currency_unified"]:
                            message_status = "not unified"
                else:
                    message_status = "not unified"

            for cloud_providers in data:
                for handlers in data[cloud_providers]:
                    if cloud_providers == "Azure":
                        rh_data = handlers["report"]
                    else:
                        rh_data = handlers["response"]
                    if rh_data:
                        for row in rh_data["chart_data"]["dataset"]:
                            existing_list = [service.get("name") for service in response_data]
                            if row['seriesname'] in existing_list:
                                current_sum = round(sum(item['value'] for item in row['data'] if not item['value'] == None), 1)
                                for service in response_data:
                                    if service.get("name") == row['seriesname']:
                                        service["value"] = service.get("value") + current_sum
                                        service['data'] = [{"label": x['label'], "value": x['value'] + y['value']} for x in row['data'] for y in service['data'] if x['label'] == y['label']]
                            else:
                                json_data = {}
                                json_data['name'] = row['seriesname']
                                total_sum = round(sum(item['value'] for item in row['data'] if not item['value'] == None ), 1)
                                json_data['value'] = total_sum
                                json_data['data'] = [{"label": data['label'], "value": data['value']} for data in row['data']]
                                if total_sum > 0:
                                    response_data.append(json_data)
                        sorted_handlers_data = sorted(response_data, key=lambda d: d['value'], reverse=True)
                        response_data = sorted_handlers_data
            response_data = response_data[0:5]
            if response_data:
                unique_series_data = list(set([items['label'] for services in response_data for items in services['data']]))
                result = [items for items in unique_series_data]
                barchart_series_data = sorted(result, key=lambda x: datetime.datetime.strptime(x, '%d %b %Y'))
        else:
            message_status = True
            last_job_status = ""
    except Exception as e:
        logger.info(e)
        message_status = True
        last_job_status = ""

    return response_data, barchart_series_data, message_status, job_id, \
        first_run, last_job_status


def get_cost_efficiecy_widget_data():
    try:
        message_status = False
        total_potential_benefits = 0.0
        potential_data = []
        benefits_across_rh = []
        last_job_status = ""
        recurring_job = RecurringJob.objects.filter(name__icontains="CSMP Dashboard Widget Data Caching")
        job_id = recurring_job.first().id if recurring_job else None
        first_run = False if recurring_job.first().spawned_jobs.all() else True
        if not first_run:
            last_job_status = recurring_job.first().spawned_jobs.all().last().status
            if last_job_status != "SUCCESS":
                last_updated = datetime.datetime.strftime(
                    recurring_job.first().spawned_jobs.all().last().updated_date, '%d/%m/%Y')
                last_job_status = last_updated
            else:
                last_job_status = ""

        src = os.path.join(PROSERV_DIR, "cached_xui_data", "kumo_integration_kit", "widget_data")
        isExist = os.listdir(src)

        if isExist:
            file_name = "efficiency_tab.txt"
            file_location = os.path.join(src, file_name)
            with open(file_location) as f:
                data = json.load(f)

            kumokit = KumoKit()

            if hasattr(kumokit, "description"):
                if kumokit.description:
                    kumo_des = json.loads(kumokit.description)
                    if "currency_unified" not in kumo_des.keys():
                        message_status = "not unified"
                    else:
                        if not kumo_des["currency_unified"]:
                            message_status = "not unified"
                else:
                    message_status = "not unified"

            unused = 0.0
            unused_count = 0
            unoptimised = 0.0
            unoptimised_count = 0
            suppressed = 0.0
            suppressed_count = 0
            for rec in data:
                rh_sum = 0.0
                for obj in rec['service_type_count']:
                    rh_sum += float(obj.get('cost_sum'))
                    total_potential_benefits += float(obj.get('cost_sum'))
                    if obj.get('type') in UNUSED_SERVICES:
                        unused += float(obj.get('cost_sum'))
                        unused_count += obj.get('count')
                    elif obj.get('type') in UNOPTIMIZED_SERVICES:
                        unoptimised += float(obj.get('cost_sum'))
                        unoptimised_count += obj.get('count')
                    elif obj.get('type') == "ignore_services":
                        suppressed += float(obj.get('cost_sum'))
                        suppressed_count += obj.get('count')
                benefits_across_rh.append(list((rec.get("rh_name"), rh_sum)))
            potential_data.append(list(("Unused", unused*100.0/total_potential_benefits, unused_count, unused)))
            potential_data.append(list(("Unoptimised", unoptimised*100.0/total_potential_benefits, unoptimised_count, unoptimised)))
            potential_data.append(list(("Suppressed", suppressed*100.0/total_potential_benefits, suppressed_count, suppressed)))
        else:
            message_status = True
            last_job_status = ""
    except Exception as e:
        message_status = True
        last_job_status = ""
        logger.info(e.args[0])

    return total_potential_benefits, potential_data, benefits_across_rh, \
        message_status, job_id, first_run, last_job_status


def get_compliance_data(request):
    try:
        last_job_status = ""
        recurring_job = RecurringJob.objects.filter(name__icontains="CSMP Dashboard Widget Data Caching")
        job_id = recurring_job.first().id if recurring_job else None
        first_run = False if recurring_job.first().spawned_jobs.all() else True
        if not first_run:
            last_job_status = recurring_job.first().spawned_jobs.all().last().status
            if last_job_status != "SUCCESS":
                last_updated = datetime.datetime.strftime(
                    recurring_job.first().spawned_jobs.all().last().updated_date, '%d/%m/%Y')
                last_job_status = last_updated
            else:
                last_job_status = ""

        src = os.path.join(PROSERV_DIR, "cached_xui_data", "kumo_integration_kit", "widget_data")
        isExist = os.listdir(src)

        if isExist:
            file_name = "compliance_data.txt"
            file_location = os.path.join(src, file_name)
            with open(file_location) as f:
                data = json.load(f)
                rh_ids_with_compliance = list(data.keys())

            if request.method == "POST":
                rh_id = request.POST.get('id')
                if not rh_id == "all":
                    response_data = data[rh_id]
                else:
                    response_data = get_all_compliance_data(data)

                return JsonResponse({"result": response_data, 'message_status' : False, "job_id": job_id,
                                    "rh_ids_with_data": rh_ids_with_compliance, "first_run": first_run,
                                    "last_job_status": last_job_status})
        else:
            last_job_status = ""
            return JsonResponse({"result": [], 'message_status' : True,
                                "job_id": job_id, "rh_ids_with_data": [],
                                "first_run": first_run, "last_job_status": last_job_status})
    except Exception as e:
        logger.info(e.args[0])
        last_job_status = ""
        return JsonResponse({"result": [], 'message_status' : True, "job_id": job_id,
                            "rh_ids_with_data": [], "first_run": first_run,
                            "last_job_status": last_job_status})


def get_spend_data(request):
    try:
        barchart_series_data = []
        response_data = []
        data_type = request.POST.get('data_type')
        message_status = False
        last_job_status = ""
        recurring_job = RecurringJob.objects.filter(name__icontains="CSMP Dashboard Widget Data Caching")
        job_id = recurring_job.first().id if recurring_job else None
        first_run = False if recurring_job and recurring_job.first().spawned_jobs.all() else True
        if not first_run:
            last_job_status = recurring_job.first().spawned_jobs.all().last().status
            if last_job_status != "SUCCESS":
                last_updated = datetime.datetime.strftime(
                    recurring_job.first().spawned_jobs.all().last().updated_date, '%d/%m/%Y')
                last_job_status = last_updated
            else:
                last_job_status = ""

        src = os.path.join(PROSERV_DIR, "cached_xui_data", "kumo_integration_kit", "widget_data")
        isExist = os.listdir(src)

        if isExist:
            if request.method == "POST":
                kumokit = KumoKit()

                if hasattr(kumokit, "description"):
                    if kumokit.description:
                        kumo_des = json.loads(kumokit.description)
                        if "currency_unified" not in kumo_des.keys():
                            message_status = "not unified"
                        else:
                            if not kumo_des["currency_unified"]:
                                message_status = "not unified"
                    else:
                        message_status = "not unified"

                if data_type == "resource_handler":
                    file_name = "spend_resources_details.txt"
                    file_location = os.path.join(src, file_name)
                    with open(file_location) as f:
                        data = json.load(f)

                    for cloud_providers in data:
                        for handlers in data[cloud_providers]:
                            if cloud_providers == "Azure":
                                rh_data = handlers["report"]
                            else:
                                rh_data = handlers["response"]
                            if rh_data:
                                json_data = {}
                                json_data['name'] = handlers['rh_name']
                                total_sum = round(sum(item['value'] for item in rh_data["chart_data"]["categories"][0]['category'] if not item['value'] == None ), 1)
                                json_data['value'] = total_sum
                                json_data['data'] = [{"label": data['label'], "value": data['value']} for data in rh_data["chart_data"]["categories"][0]['category']]
                                if total_sum > 0:
                                    response_data.append(json_data)
                                sorted_handlers_data = sorted(response_data, key=lambda d: d['value'], reverse=True)
                                response_data =  sorted_handlers_data
                elif data_type == "services" or data_type == "locations_regions" or data_type == "labels_tags":
                    if data_type == "services":
                        file_name = "spend_services_details.txt"
                    elif data_type == "locations_regions":
                        file_name = "spend_locations_details.txt"
                    elif data_type == "labels_tags":
                        file_name = "spend_tags_details.txt"
                    file_location = os.path.join(src, file_name)
                    with open(file_location) as f:
                        data = json.load(f)
                    for cloud_providers in data:
                        for handlers in data[cloud_providers]:
                            if cloud_providers == "Azure":
                                rh_data = handlers["report"]
                            else:
                                rh_data = handlers["response"]
                            if rh_data:
                                for row in rh_data["chart_data"]["dataset"]:
                                    existing_list = [service.get("name") for service in response_data]
                                    if row['seriesname'] in existing_list:
                                        current_sum = round(sum(item['value'] for item in row['data'] if not item['value'] == None), 1)
                                        for service in response_data:
                                            if service.get("name") == row['seriesname']:
                                                service["value"] = service.get("value") + current_sum
                                                service['data'] = [{"label": x['label'], "value": float(x['value'] or 0) + float(y['value'] or 0)} for x in row['data'] for y in service['data'] if x['label'] == y['label']]
                                    else:
                                        json_data = {}
                                        json_data['name'] = row['seriesname']
                                        total_sum = round(sum(item['value'] for item in row['data'] if not item['value'] == None ), 1)
                                        json_data['value'] = total_sum
                                        json_data['data'] = [{"label": data['label'], "value": data['value']} for data in row['data']]
                                        if total_sum > 0:
                                            response_data.append(json_data)
                                sorted_handlers_data = sorted(response_data, key=lambda d: d['value'], reverse=True)
                                response_data =  sorted_handlers_data
                else:
                    return JsonResponse({"message": "Invalid Choice"})

                if response_data:
                    unique_series_data = list(set([items['label'] for services in response_data for items in services['data']]))
                    result = [items for items in unique_series_data]
                    barchart_series_data = sorted(result, key=lambda x: datetime.datetime.strptime(x, '%d %b %Y'))

                return JsonResponse({
                    "status": True,
                    "data_type": data_type,
                    "response_data": response_data,
                    "barchart_series_data": barchart_series_data,
                    "message_status": message_status,
                    "job_id": job_id,
                    "first_run": first_run,
                    "last_job_status": last_job_status
                })
        else:
            message_status = True
            last_job_status = ""
            return JsonResponse({"status": True, "data_type": data_type,
                                 "response_data": response_data,
                                 "barchart_series_data": barchart_series_data,
                                 "message_status": message_status, "job_id": job_id,
                                 "first_run": first_run, "last_job_status": last_job_status})
    except Exception as e:
        message_status = True
        last_job_status = ""
        logger.info(e)
        return JsonResponse({
            "status": True,
            "data_type": data_type,
            "response_data": response_data,
            "barchart_series_data": barchart_series_data,
            "message_status": message_status,
            "job_id": job_id,
            "first_run": first_run,
            "last_job_status": last_job_status
        })
