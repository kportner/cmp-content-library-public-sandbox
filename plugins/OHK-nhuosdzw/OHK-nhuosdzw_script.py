"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
from common.methods import set_progress
from decimal import Decimal
from containerorchestrators.openshifthandler.models import Openshift
from infrastructure.models import CustomField


def get_or_create_custom_fields():
    """
    Helper functions for main function to create custom field as needed
    """
    CustomField.objects.get_or_create(
        name="cpu_unit",
        defaults={
            "label": "CPU Unit",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="memory_unit",
        defaults={
            "label": "Memory Unit",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="cpu_request",
        defaults={
            "label": "CPU Request",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="cpu_limit",
        defaults={
            "label": "CPU Limit",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="memory_request",
        defaults={
            "label": "Memory Request",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="memory_limit",
        defaults={
            "label": "Memory Limit",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )


def generate_options_for_cpu_request(control_value=None, server=None, **kwargs):
    resource = kwargs.get("resource", None)

    if resource is None:
        return {"initial_value": "", "options": []}

    initial_value = resource.get_cf_values_as_dict().get("cpu_request", "")

    return {"initial_value": initial_value, "options": []}


def generate_options_for_cpu_limit(control_value=None, server=None, **kwargs):
    resource = kwargs.get("resource", None)

    if resource is None:
        return {"initial_value": "", "options": []}

    initial_value = resource.get_cf_values_as_dict().get("cpu_limit", "")

    return {"initial_value": initial_value, "options": []}


def generate_options_for_memory_request(control_value=None, server=None, **kwargs):
    resource = kwargs.get("resource", None)

    if resource is None:
        return {"initial_value": "", "options": []}

    initial_value = resource.get_cf_values_as_dict().get("memory_request", "")

    return {"initial_value": initial_value, "options": []}


def generate_options_for_memory_limit(control_value=None, server=None, **kwargs):
    resource = kwargs.get("resource", None)

    if resource is None:
        return {"initial_value": "", "options": []}

    initial_value = resource.get_cf_values_as_dict().get("memory_limit", "")

    return {"initial_value": initial_value, "options": []}


def generate_options_for_cpu_unit(control_value=None, server=None, **kwargs):
    resource = kwargs.get("resource", None)

    options = [
        ("", "---Select CPU Unit---"),
        ("core", "cores"),
        ("m", "millicores"),
    ]

    if resource is None:
        return options

    initial_value = resource.get_cf_values_as_dict().get("cpu_unit", "")

    if initial_value != "":
        return {"initial_value": initial_value, "options": options}

    return options


def generate_options_for_memory_unit(control_value=None, server=None, **kwargs):
    resource = kwargs.get("resource", None)

    options = [("", "---Select Memory Unit---"), ("Mi", "Mi"), ("Gi", "Gi")]

    if resource is None:
        return options

    initial_value = resource.get_cf_values_as_dict().get("memory_unit", "")

    if initial_value != "":
        return {"initial_value": initial_value, "options": options}

    return options


def run(job, resource, *args, **kwargs):
    set_progress("Starting provision of container resource limits update...")

    # get or create custom fields as needed
    get_or_create_custom_fields()

    cpu_unit = "{{cpu_unit}}"
    cpu_request = "{{cpu_request}}"
    cpu_limit = "{{cpu_limit}}"

    memory_unit = "{{memory_unit}}"
    memory_request = "{{memory_request}}"
    memory_limit = "{{memory_limit}}"

    cpu_request = (
        cpu_request.rstrip("0").rstrip(".") if "." in cpu_request else cpu_request
    )
    cpu_limit = cpu_limit.rstrip("0").rstrip(".") if "." in cpu_limit else cpu_limit
    memory_request = (
        memory_request.rstrip("0").rstrip(".")
        if "." in memory_request
        else memory_request
    )
    memory_limit = (
        memory_limit.rstrip("0").rstrip(".") if "." in memory_limit else memory_limit
    )

    if Decimal(cpu_request) > Decimal(cpu_limit):
        return (
            "FAILURE",
            "",
            f"Invalid resource cpu request, it should be less than the limit",
        )

    if Decimal(memory_request) > Decimal(memory_limit):
        return (
            "FAILURE",
            "",
            f"Invalid resource memory request, it should be less than the limit",
        )

    if cpu_unit == "core":
        cpu_unit = ""

    resources = {
        "limits": {
            "cpu": f"{cpu_limit}{cpu_unit}",
            "memory": f"{memory_limit}{memory_unit}",
        },
        "requests": {
            "cpu": f"{cpu_request}{cpu_unit}",
            "memory": f"{memory_request}{memory_unit}",
        },
    }

    set_progress(f"Requested resource limits are: {resources}")

    cf_values = resource.get_cf_values_as_dict()

    container_orchestrator_id = cf_values.get("container_orchestrator_id", None)

    if container_orchestrator_id is None:
        return (
            "FAILURE",
            "",
            f"Does not found container orchestrator id: {container_orchestrator_id}",
        )

    oc_handler = Openshift.objects.get(id=container_orchestrator_id)

    name = resource.name
    namespace = cf_values.get("project_name", "")

    try:
        # get deployments json
        deployment_json = oc_handler.get_deployment_detail_raw(name, namespace)
    except Exception as err:
        return (
            "FAILURE",
            "",
            f"Unexpected error occurred, errors: {err}",
        )

    for container in deployment_json["spec"]["template"]["spec"]["containers"]:
        container["resources"] = resources

    try:
        # update container resource limits
        oc_handler.update_application_deployment(name, namespace, deployment_json)
    except Exception as err:
        return (
            "FAILURE",
            "",
            f"Unexpected error occurred, errors: {err}",
        )

    resource.cpu_unit = "core" if cpu_unit == "" else cpu_unit
    resource.cpu_request = cpu_request
    resource.cpu_limit = cpu_limit
    resource.memory_unit = memory_unit
    resource.memory_request = memory_request
    resource.memory_limit = memory_limit
    resource.save()

    return "SUCCESS", "Container resource limits updated successfully", ""