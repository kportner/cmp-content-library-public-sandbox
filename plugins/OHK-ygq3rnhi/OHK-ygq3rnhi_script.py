"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
from common.methods import set_progress
from containerorchestrators.openshifthandler.models import Openshift
from containerorchestrators.models import ContainerDeployment, ContainerPod


def run(job, resource, *args, **kwargs):
    set_progress(
        f"Openshift container application Delete plugin running for resource: {resource}"
    )

    cf_value = resource.get_cf_values_as_dict()
    container_orchestrator_id = cf_value.get("container_orchestrator_id", None)

    if container_orchestrator_id is None or container_orchestrator_id == "":
        return (
            "SUCCESS",
            "Openshift container application {0} deleted successfully".format(
                resource.name
            ),
            "",
        )

    try:
        oc_handler = Openshift.objects.get(id=container_orchestrator_id)
    except Exception:
        return (
            "SUCCESS",
            "Openshift container application {0} deleted successfully".format(
                resource.name
            ),
            "",
        )

    try:
        oc_handler.delete_application_deployment(resource.name, resource.project_name)
    except Exception as err:
        return "FAILURE", "", f"{err}"
    
    try:
        oc_handler.delete_application_service(resource.name, resource.project_name)
    except Exception as err:
        pass
    
    if cf_value.get("image_registry", "") == "external":
        try:
            oc_handler.delete_application_imagestream(
                resource.name, resource.project_name
            )
        except Exception as err:
            pass

    resource_create_route = cf_value.get("create_route", "False")

    if isinstance(resource_create_route, str):
        resource_create_route = False if resource_create_route == "False" else True

    if resource_create_route:
        try:
            oc_handler.delete_application_route(resource.name, resource.project_name)
        except Exception as err:
            pass

    if resource.lifecycle != "PROVFAILED":
        # delete deployment and pods from CMP
        try:
            ContainerDeployment.objects.get(
                name=resource.name, namespace__name=resource.project_name
            ).delete()
        except Exception as err:
            pass
        else:
            pods = ContainerPod.objects.filter(
                namespace__name=resource.project_name,
                name__startswith=f"{resource.name}-",
            )
            for pod in pods:
                pod.delete()

    return (
        "SUCCESS",
        "Openshift container application {0} deleted successfully".format(
            resource.name
        ),
        "",
    )