from extensions.views import admin_extension
from django.shortcuts import render
from itsm.servicenow.wrapper import TechnologyWrapper as ServiceNowAPI
from django.http import JsonResponse
import json
import os
from utilities.decorators import dialog_view
from utilities.permissions import cbadmin_required
from django.http import HttpResponseRedirect
from django.urls import reverse
from django.contrib import messages
from django.utils.html import format_html
from django.utils.translation import gettext as _
from settings import PROSERV_DIR
from cbhooks.models import ServiceNowHook
from itsm.servicenow.forms import ServiceNowITSMCredentialsForm
from xui.service_now_approval.utils import (
    _update_or_create_servicenow_create_request_action,
    _update_or_create_servicenow_close_request_action,
    _update_or_create_servicenow_change_order_status_action,
    get_or_create_default_json,
)
from utilities.logger import ThreadLogger
from itsm.servicenow.models import ServiceNowITSM
from itsm.models import ITSMTechnology
from servicecatalog.models import ServiceBlueprint
import uuid
from c2_wrapper import create_custom_field, create_custom_field_value
from orders.models import CustomFieldValue
from infrastructure.models import CustomField


logger = ThreadLogger(__name__)


@admin_extension(
    title="ServiceNow Approval", description="ServiceNow Approval into CloudBolt"
)
def admin_page(request):
    """
    Admin page of service now approval,
    This page will be having list of all servicenow connectors, sample workflows and list of all configurations.
    """
    _update_or_create_servicenow_create_request_action()
    _update_or_create_servicenow_close_request_action()
    _update_or_create_servicenow_change_order_status_action()
    get_or_create_default_json()

    service_now_approval = ServiceNowITSM.objects.all()
    blueprints = ServiceBlueprint.objects.filter(status="ACTIVE", is_orderable=True)
    workflows = []
    data = {}
    default_data = get_or_create_default_json()
    custom_fields = CustomField.objects.filter(namespace__name="servicenow_approvals_xui")
    for custom_field in custom_fields:
        custom_field_values = CustomFieldValue.objects.filter(field=custom_field).first()
        values = json.loads(custom_field_values.txt_value)
        data[custom_field.name] = values
        workflows.append(values)
    is_default_present = False
    for workflow in workflows:
        if 'default' in workflow and workflow.get('default') == True:
            is_default_present = True
            break

    context = {
        "service_now_approvals": service_now_approval,
        "service_nows_count": service_now_approval.count(),
        "workflows": workflows,
        "workflows_count": len(workflows),
        "blueprints": blueprints,
        "is_default_present": is_default_present,
        'json_data': data,
        "default_data": default_data
    }
    return render(request, "service_now_approval/templates/admin_page.html", context)


def get_workflow_choices(request):
    """
    This function will fetch all the workflows from servicenow using the connector id.
    """
    data = json.loads(request.POST.get("body"))
    snow_id = data.get("snow_id")
    if snow_id and ServiceNowITSM.objects.filter(id=int(snow_id)).exists():
        snow = ServiceNowITSM.objects.get(id=int(snow_id))
        servicenow_api = ServiceNowAPI(snow.ip, snow.port, snow.service_account, snow.password)
        base_url = f"{servicenow_api.service_now_instance_url}{servicenow_api.API_BASE_URL}"
        snow_workflows = servicenow_api._snow_get(
            f"{base_url}/wf_workflow"
        )
        wfs = snow_workflows.json()["result"]
        wf_choices = [(wf["sys_id"], wf["sys_name"]) for wf in wfs]
        return JsonResponse({"result": wf_choices, "message_status": True})
    else:
        return JsonResponse({"result": [], "message_status": False})


def get_field_choices(request):
    """
    This function will fetch all the field choices from servicenow using the connector id.
    """
    data = json.loads(request.POST.get("body"))
    snow_id = data.get("snow_id")
    if snow_id and ServiceNowITSM.objects.filter(id=int(snow_id)).exists():
        snow = ServiceNowITSM.objects.get(id=int(snow_id))
        servicenow_api = ServiceNowAPI(snow.ip, snow.port, snow.service_account, snow.password)
        base_url = f"{servicenow_api.service_now_instance_url}{servicenow_api.API_BASE_URL}"
        snow_field_choices = servicenow_api._snow_get(
            f"{base_url}/task?sysparm_limit=1"
        )
        fields_dict = snow_field_choices.json()["result"][0]
        keys_list = list(fields_dict.keys())
        field_choices = list(set([(key, key) for key in keys_list]))
        field_choices = [
            field
            for field in field_choices
            if (
                "sys_" not in field[0]
                and "_at" not in field[0]
                and "_by" not in field[0]
                and "_to" not in field[0]
                and "due" not in field[0]
            )
        ]
        return JsonResponse({"result": field_choices, "message_status": True})
    else:
        return JsonResponse({"result": [], "message_status": False})


def get_field_value_choices(request):
    """
    This function will fetch all the values for selected field choice from servicenow using connector id and field_name.
    """
    data = json.loads(request.POST.get("body"))
    snow_id = data.get("snow_id")
    if snow_id and ServiceNowITSM.objects.filter(id=int(snow_id)).exists():
        snow = ServiceNowITSM.objects.get(id=int(snow_id))
        servicenow_api = ServiceNowAPI(snow.ip, snow.port, snow.service_account, snow.password)
        base_url = f"{servicenow_api.service_now_instance_url}{servicenow_api.API_BASE_URL}"
        field_name = data.get("approval_field_name")
        query = f"element={field_name}"
        snow_value_choices = servicenow_api._snow_get(
            f"{base_url}/sys_choice?{query}"
        )
        vcs = snow_value_choices.json()["result"]
        vc_choices = list(set([(vc["value"], vc["label"]) for vc in vcs]))
        return JsonResponse({"result": vc_choices, "message_status": True})
    else:
        return JsonResponse({"result": [], "message_status": False})


def get_service_now_tables(request):
    """
    This function will fetch all the service now tables from servicenow using connector id.
    """
    table_base_url = "/api/now/doc/table"
    data = json.loads(request.POST.get("body"))
    snow_id = data.get("snow_id")
    if snow_id and ServiceNowITSM.objects.filter(id=int(snow_id)).exists():
        snow = ServiceNowITSM.objects.get(id=int(snow_id))
        servicenow_api = ServiceNowAPI(snow.ip, snow.port, snow.service_account, snow.password)
        base_url = f"{servicenow_api.service_now_instance_url}{table_base_url}"
        snow_value_choices = servicenow_api._snow_get(
            f"{base_url}/schema"
        )
        tables = snow_value_choices.json()["result"]
        return JsonResponse({"result": tables, "message_status": True})
    else:
        return JsonResponse({"result": [], "message_status": False})


@dialog_view
@cbadmin_required
def add_service_now_approval_connection(request):
    """
    Dialog for adding a new ServiceNowITSM object.
    """
    if request.method == "POST":
        form = ServiceNowITSMCredentialsForm(request.POST)
        if form.is_valid():
            service_now_approval = form.save()
            messages.success(
                request,
                format_html(
                    "The ServiceNow connection <b>{}</b> was created.",
                    service_now_approval.name,
                ),
            )
            return HttpResponseRedirect("/extensions/admin/service_now_approval/admin_page")
        else:
            logger.info(form.errors)
            msg = "The ServiceNow connection was not created. Unable to create new connection."
            messages.error(request, format_html(msg))
            logger.info(msg)

        return HttpResponseRedirect("/extensions/admin/service_now_approval/admin_page")
    elif request.method == "GET":
        itsm_technology = ITSMTechnology.objects.filter(name='ServiceNow').first()
        form = ServiceNowITSMCredentialsForm(initial={"itsm_technology": itsm_technology.id})

    return {
        "title": "Create New ServiceNow Connection",
        "form": form,
        "use_ajax": True,
        "action_url": reverse("add_service_now_approval_connection"),
        "submit": "Create",
    }


def save_snow_workflow(request):
    """
    This function will be used for saving the servicenow configurations in a json file at the specified path in the container.
    """
    payload_data = json.loads(request.POST.get("body"))
    snow_id = str(uuid.uuid4())
    default_data = get_or_create_default_json()
    payload_data.update({"snow_id": snow_id})
    payload_data.update({"data": default_data})
    custom_field = create_custom_field(
        name=snow_id,
        namespace="servicenow_approvals_xui",
        type="TXT",
        label="Service Now Approval Configs",
        description="Custom Field used for storing Service Now Approval Configs",
    )
    approval_config = json.dumps(payload_data)
    custom_field_value = create_custom_field_value(snow_id, approval_config)
    msg = format_html(_("ServiceNow workflow configuration has been created."))
    messages.success(request, msg)
    return JsonResponse({"success": True})


def delete_snow_workflow(request):
    """
    This function will be used for deleting a particular servicenow configuration.
    """
    payload_data = json.loads(request.POST.get("body"))
    file_key_id = payload_data["file_key_id"]
    CustomField.objects.filter(name=file_key_id).delete()
    msg = format_html(_("ServiceNow workflow configuration has been deleted."))
    messages.success(request, msg)
    return JsonResponse({"success": True})


def make_default_snow_workflow(request):
    """
    This function will be used for making default a particular servicenow configuration.
    """
    payload_data = json.loads(request.POST.get("body"))
    file_key_id = payload_data["file_key_id"]
    custom_field_values = CustomFieldValue.objects.filter(field__namespace__name="servicenow_approvals_xui")
    
    for record in custom_field_values:
        data = json.loads(record.txt_value)
        if 'default' in data:
            data.update({'default': False})
        data.update({'change_default': False})
        if record.field.name == file_key_id:
            data.update({'default': True})
        record.txt_value = json.dumps(data)
        record.save()
    msg = format_html(_("ServiceNow workflow configuration has been set to default."))
    messages.success(request, msg)
    return JsonResponse({"success": True})


def change_default_snow_workflow(request):
    """
    This function will be used for changing Change Default flag so that button will be appear on workflow configuration.
    """
    custom_field_values = CustomFieldValue.objects.filter(field__namespace__name="servicenow_approvals_xui")
    for record in custom_field_values:
        data = json.loads(record.txt_value)
        data.update({'change_default': True})
        data.update({'default': False})
        record.txt_value = json.dumps(data)
        record.save()
    return JsonResponse({"success": True})


def add_default_data(request):
    """
    This function will be used for adding default data into the workflow.
    """
    payload_data = json.loads(request.POST.get("body"))
    file_key_id = payload_data["file_key_id"]
    custom_field_values = CustomFieldValue.objects.filter(field__name=file_key_id).first()
    data = json.loads(custom_field_values.txt_value)
    data.update({'data': payload_data["data"]})
    custom_field_values.txt_value = json.dumps(data)
    custom_field_values.save()
    msg = format_html(_("Payload has been updated."))
    messages.success(request, msg)
    return JsonResponse({"success": True})
