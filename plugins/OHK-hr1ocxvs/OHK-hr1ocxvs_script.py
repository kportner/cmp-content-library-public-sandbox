"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
import time
from infrastructure.models import CustomField
from containerorchestrators.openshifthandler.models import Openshift
from common.methods import set_progress


def get_or_create_custom_fields():
    """
    Helper functions for main function to create custom field as needed
    """
    CustomField.objects.get_or_create(
        name="create_route",
        defaults={
            "label": "Create a Route to the Application",
            "type": "BOOL",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="application_route",
        defaults={
            "label": "Application Routes",
            "type": "URL",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="application_hostname",
        defaults={
            "label": "Hostname",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )
    CustomField.objects.get_or_create(
        name="application_path",
        defaults={
            "label": "Path",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="application_target_port",
        defaults={
            "label": "Target Port",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )


def generate_options_for_create_route(control_value=None, server=None, **kwargs):
    resource = kwargs.get("resource", None)

    if resource is None:
        return {"initial_value": "", "options": []}

    initial_value = resource.get_cf_values_as_dict().get("create_route", "")

    return {"initial_value": initial_value, "options": []}


def generate_options_for_application_target_port(
    control_value=None, server=None, **kwargs
):
    resource = kwargs.get("resource", None)

    if resource is None:
        return {"initial_value": "", "options": []}

    initial_value = resource.get_cf_values_as_dict().get("application_target_port", "")

    return {"initial_value": initial_value, "options": []}


def generate_options_for_application_path(control_value=None, server=None, **kwargs):
    resource = kwargs.get("resource", None)

    if resource is None:
        return {"initial_value": "", "options": []}

    initial_value = resource.get_cf_values_as_dict().get("application_path", "")

    return {"initial_value": initial_value, "options": []}


def generate_options_for_application_hostname(
    control_value=None, server=None, **kwargs
):
    resource = kwargs.get("resource", None)

    if resource is None:
        return {"initial_value": "", "options": []}

    initial_value = resource.get_cf_values_as_dict().get("application_route", "")

    return {"initial_value": initial_value, "options": []}


def build_payload(
    resource,
    cf_values,
    application_hostname,
    application_path,
    application_target_port,
    oc_handler,
):
    service_payload_kwargs = {}

    if application_target_port != "":
        application_target_port = int(application_target_port)

        service_payload_kwargs = {
            "ports": [
                {
                    "port": application_target_port,
                    "targetPort": application_target_port,
                    "protocol": "TCP",
                    "name": f"{application_target_port}-tcp",
                }
            ]
        }

    # get service port payload
    port_payload = oc_handler.build_resource_ports(
        resource_type="service", **service_payload_kwargs
    )

    name = resource.name
    namespace = cf_values.get("project_name", "")

    try:
        # get service raw details
        service_json = oc_handler.get_service_detail_raw(name, namespace)
    except Exception as err:
        raise ValueError(f"Unexpected error occurred, errors: {err}")

    service_json["spec"]["ports"] = port_payload
    
    resource_create_route = cf_values.get("create_route", False)
    
    if isinstance(resource_create_route, str):
        resource_create_route = False if resource_create_route == "False" else True

    delete_existing_route = False

    if (not resource_create_route) or (
        application_hostname == ""
        and application_path == ""
        and application_target_port == ""
    ):
        if resource_create_route:
            delete_existing_route = True

        resource_create_route = True

        application_name = cf_values.get("application_name", "")
        route_payload_kwargs = {}

        if application_target_port != "":
            route_payload_kwargs = {
                "host": application_hostname,
                "path": application_path,
                "targetPort": application_target_port,
            }

        # get route payload
        route_json = oc_handler.build_route_payload(
            name, application_name, namespace, **route_payload_kwargs
        )
    else:
        resource_create_route = False
        try:
            # get route raw details
            route_json = oc_handler.get_route_detail_raw(name, namespace)
        except Exception as err:
            raise ValueError(f"Unexpected error occurred, errors: {err}")

        # create route payload
        route_payload = {
            "to": route_json["spec"]["to"],
            "host": application_hostname,
            "path": application_path,
            "port": {
                "targetPort": f"{application_target_port}-tcp"
                if application_target_port != ""
                else "8080-tcp"
            },
            "wildcardPolicy": route_json["spec"]["wildcardPolicy"],
        }

        auto_host_generated = (
            route_json["metadata"]
            .get("annotations", {})
            .get("openshift.io/host.generated", "false")
        )

        if auto_host_generated == "true":
            if (
                application_hostname != ""
                and application_hostname != route_json["spec"]["host"]
            ):
                del route_json["metadata"]["annotations"]["openshift.io/host.generated"]
                if not route_json["metadata"]["annotations"]:
                    del route_json["metadata"]["annotations"]
        else:
            if application_hostname == "":
                if "annotations" in route_json["metadata"]:
                    route_json["metadata"]["annotations"][
                        "openshift.io/host.generated"
                    ] = "true"
                else:
                    route_json["metadata"]["annotations"] = {
                        "openshift.io/host.generated": "true"
                    }

        route_json["spec"] = route_payload

        if "ingress" in route_json["status"]:
            # set host name
            route_json["status"]["ingress"][0]["host"] = application_hostname

    return (
        route_json,
        service_json,
        name,
        namespace,
        delete_existing_route,
        resource_create_route,
    )


def run(job, resource, *args, **kwargs):
    set_progress("Starting provision of container route settings update...")

    # get or create custom fields as needed
    get_or_create_custom_fields()

    create_route = "{{create_route}}"
    application_hostname = "{{application_hostname}}"
    application_path = "{{application_path}}"
    application_target_port = "{{application_target_port}}"

    cf_values = resource.get_cf_values_as_dict()

    if isinstance(create_route, str):
        create_route = False if create_route == "False" else True

    if (
        application_hostname == ""
        and application_path == ""
        and application_target_port == ""
        and cf_values.get("application_route", "") == ""
        and cf_values.get("application_path", "") == ""
        and cf_values.get("application_target_port", "") == ""
        and not create_route
    ):
        return "WRANNING", "Please enter data and try again.", ""

    container_orchestrator_id = cf_values.get("container_orchestrator_id", None)

    if container_orchestrator_id is None:
        return (
            "FAILURE",
            "",
            f"Does not found container orchestrator id: {container_orchestrator_id}",
        )

    oc_handler = Openshift.objects.get(id=container_orchestrator_id)

    (
        route_json,
        service_json,
        name,
        namespace,
        delete_existing_route,
        create_new_route,
    ) = build_payload(
        resource,
        cf_values,
        application_hostname,
        application_path,
        application_target_port,
        oc_handler,
    )

    try:
        # update service details
        oc_handler.update_application_service(name, namespace, service_json)
    except Exception as err:
        return (
            "FAILURE",
            "",
            f"Unexpected error occurred, errors: {err}",
        )
    
    if delete_existing_route or not create_route:
        try:
            # delete old route
            oc_handler.delete_application_route(name, namespace)
        except Exception as err:
            return (
                "FAILURE",
                "",
                f"Unexpected error occurred, errors: {err}",
            )
        else:
            time.sleep(10)

        if not create_route:
            resource.create_route = create_route
            resource.application_hostname = ""
            resource.application_path = ""
            resource.application_target_port = ""
            resource.application_route = ""
            resource.save()
            return "SUCCESS", "Container route updated successfully", ""

    if create_new_route:
        try:
            # create route
            route_rsp = oc_handler.create_application_route(namespace, route_json)
        except Exception as err:
            return (
                "FAILURE",
                "",
                f"Unexpected error occurred, errors: {err}",
            )

        resource.application_route = "{0}{1}".format(route_rsp["spec"]["host"], application_path)

    else:
        try:
            # update route details
            route_rsp = oc_handler.update_application_route(name, namespace, route_json)
        except Exception as err:
            return (
                "FAILURE",
                "",
                f"Unexpected error occurred, errors: {err}",
            )
        resource.application_route = "{0}{1}".format(route_rsp["spec"]["host"], application_path)

    resource.create_route = create_route
    resource.application_hostname = application_hostname
    resource.application_path = application_path
    resource.application_target_port = application_target_port
    resource.save()

    return "SUCCESS", "Container route updated successfully", ""