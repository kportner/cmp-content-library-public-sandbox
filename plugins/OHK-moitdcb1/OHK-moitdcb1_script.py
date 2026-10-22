"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
from infrastructure.models import CustomField
from containerorchestrators.openshifthandler.models import Openshift
from common.methods import set_progress


def get_or_create_custom_fields():
    """
    Helper functions for main function to create custom field as needed
    """

    CustomField.objects.get_or_create(
        name="replicas",
        defaults={
            "label": "Replicas",
            "type": "INT",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )


def generate_options_for_replicas(control_value=None, server=None, **kwargs):
    resource = kwargs.get("resource", None)

    if resource is None:
        return {"initial_value": "", "options": []}

    initial_value = resource.get_cf_values_as_dict().get("replicas", "")

    return {"initial_value": initial_value, "options": []}


def run(job, resource, *args, **kwargs):
    set_progress("Starting provision of deployment replicas count update...")

    # get or create custom fields as needed
    get_or_create_custom_fields()

    replicas = "{{replicas}}"

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

    payload = [{"op": "replace", "path": "/spec/replicas", "value": int(replicas)}]

    try:
        oc_handler.scale_application_deployment(name, namespace, payload)
    except Exception as err:
        return (
            "FAILURE",
            "",
            f"Unexpected error occurred, errors: {err}",
        )
    resource.replicas = replicas
    resource.save()

    # get all created pods name
    created_pods = [
        pod
        for pod in oc_handler.get_pod_names(namespace=namespace, force_sync=True)
        if pod.startswith(f"{name}-")
    ]

    if created_pods:
        # sync pods
        oc_handler.sync_resource_metadata(sync_resource_type="sync_pods", selected_resources=created_pods)

    return "SUCCESS", "Deployments replicas updated successfully", ""