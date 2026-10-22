import os
import json
from initialize.create_objects import create_recurring_job
from c2_wrapper import create_hook, create_custom_field, create_custom_field_value
from orders.models import CustomFieldValue
from infrastructure.models import CustomField
from jobs.models import RecurringJob
from settings import PROSERV_DIR


def _update_or_create_servicenow_change_order_status_action():

    recurring_job = {
        'name': 'ServiceNow Change Order Status',
        "description": (
            "This will fetch status of CMP orders from servicenow portal to approve them in CMP"
        ),
        'schedule': '*/30 * * * *',
        'type': 'recurring_action',
        'enabled': True,
        "hook_name": "Hook for ServiceNow Change Order Status",
    }
    recurring_job_hook = {
        'name': "Hook for ServiceNow Change Order Status",
        'description': "Generate hook for ServiceNow Change Order Status in ServiceNow recurring job.",
        'hook_point': None,
        'module': os.path.join(PROSERV_DIR, "xui", "service_now_approval",
                               "recurring_jobs", 
                               "servicenow_change_order_status.py"),
    }

    create_hook(**recurring_job_hook)
    create_recurring_job(recurring_job)
    rj_obj = RecurringJob.objects.filter(
                name="ServiceNow Change Order Status").first()

    return bool(rj_obj), rj_obj.id


def _update_or_create_servicenow_create_request_action():

    orchestration_action_hook = {
        'name': "ServiceNow Create Service Request",
        'enabled': True,
        'description': "Hook to create a Service Catalog Request for Order once it is submitted.",
        'hook_point': "order_approval",
        'module': os.path.join(PROSERV_DIR, "xui", "service_now_approval",
                               "recurring_jobs", 
                               "servicenow_create_request.py"),
    }

    create_hook(**orchestration_action_hook)
    return


def _update_or_create_servicenow_close_request_action():

    orchestration_action_hook = {
        'name': "ServiceNow Close Service Request",
        'enabled': True,
        'description': "Hook to close a Service Catalog Request Record for Order an order when complete.",
        'hook_point': "post_order_execution",
        'module': os.path.join(PROSERV_DIR, "xui", "service_now_approval",
                               "recurring_jobs", 
                               "servicenow_close_request.py"),
    }

    create_hook(**orchestration_action_hook)
    return


def get_or_create_default_json():
    if not CustomField.objects.filter(name="servicenow_approvals_default_json").exists():
        static_src = os.path.join(PROSERV_DIR, "xui", "service_now_approval", "static", "files")
        default_data_file_location = os.path.join(static_src, "default_data.json")
        data = {}
        if os.path.isfile(default_data_file_location):
            with open(default_data_file_location, "r+") as jsonFile:
                data = json.loads(jsonFile.read())
        custom_field = create_custom_field(
            name="servicenow_approvals_default_json",
            namespace="servicenow_approvals_default_json",
            type="TXT",
            label="Service Now Approval Configs",
            description="Custom Field used for storing Service Now Approval Configs",
        )
        approval_config = json.dumps(data)
        custom_field_value = create_custom_field_value("servicenow_approvals_default_json", approval_config)
        return json.loads(custom_field_value.txt_value)
    else:
        custom_field = CustomField.objects.filter(namespace__name="servicenow_approvals_default_json").first()
        custom_field_values = CustomFieldValue.objects.filter(field=custom_field).first()
        return json.loads(custom_field_values.txt_value)
