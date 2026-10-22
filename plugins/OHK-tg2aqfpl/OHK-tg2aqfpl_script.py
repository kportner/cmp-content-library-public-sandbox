"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
from common.methods import set_progress
from infrastructure.models import CustomField
from containerorchestrators.openshifthandler.models import Openshift
import ast


def get_or_create_custom_fields():
    """
    Helper functions for main function to create custom field as needed
    """
    CustomField.objects.get_or_create(
        name="application_env_value",
        defaults={
            "label": "Single values (env)",
            "type": "TXT",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="application_envform_value",
        defaults={
            "label": "ConfigMaps or Secrets (envFrom)",
            "type": "TXT",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )


def generate_options_for_application_env_value(
    control_value=None, server=None, **kwargs
):
    resource = kwargs.get("resource", None)

    if resource is None:
        return {"initial_value": "", "options": []}

    initial_value = resource.get_cf_values_as_dict().get("application_env_value", "")

    return {"initial_value": initial_value, "options": []}


def generate_options_for_application_envform_value(
    control_value=None, server=None, **kwargs
):
    resource = kwargs.get("resource", None)

    if resource is None:
        return {"initial_value": "", "options": []}

    initial_value = resource.get_cf_values_as_dict().get(
        "application_envform_value", ""
    )

    return {"initial_value": initial_value, "options": []}


def run(job, resource, *args, **kwargs):
    set_progress("Starting provision of deployments environments variables update...")

    # get or create custom fields as needed
    get_or_create_custom_fields()

    application_env_value = "{{application_env_value}}"
    application_envform_value = "{{application_envform_value}}"

    if application_env_value != "":
        try:
            application_env_value = ast.literal_eval(application_env_value)
            if not isinstance(application_env_value, dict):
                raise
        except Exception as err:
            return (
                "FAILURE",
                "",
                f"Invalid 'Single values (env)' field value, the system will accept only JSON or empty string, please check and try again.",
            )

    if application_envform_value != "":
        try:
            application_envform_value = ast.literal_eval(application_envform_value)
            if not isinstance(application_envform_value, dict):
                raise
        except Exception as err:
            return (
                "FAILURE",
                "",
                f"Invalid 'ConfigMaps or Secrets (envFrom)' field value, the system will accept only JSON or empty string, please check and try again.",
            )

    if application_envform_value == "" and application_env_value == "":
        return "WRANNING", "Please enter data and try again.", ""

    cf_values = resource.get_cf_values_as_dict()

    container_orchestrator_id = cf_values.get("container_orchestrator_id", None)

    if container_orchestrator_id is None:
        return (
            "FAILURE",
            "",
            f"Does not found container orchestrator id: {container_orchestrator_id}",
        )

    application_env_value_payload = []

    if application_env_value != "":
        application_env_value_payload = [
            {"name": key, "value": value}
            for key, value in application_env_value.items()
        ]

    application_envform_value_payload = []

    if application_envform_value != "":
        application_envform_value_payload = [
            {"prefix": value, "configMapRef": {"name": key}}
            for key, value in application_envform_value.items()
        ]

    oc_handler = Openshift.objects.get(id=container_orchestrator_id)

    payload = oc_handler.build_deployment_env_and_env_form_payload(
        application_env_value_payload, application_envform_value_payload
    )

    name = resource.name
    namespace = cf_values.get("project_name", "")
    
    try:
        # update deployments environment variables
        oc_handler.patch_application_deployment(name, namespace, payload)
    except Exception as err:
        return (
            "FAILURE",
            "",
            f"Unexpected error occurred, errors: {err}",
        )

    resource.application_env_value = application_env_value
    resource.application_envform_value = application_envform_value
    resource.save()

    return "SUCCESS", "Deployments environments updated successfully", ""