from common.methods import set_progress
from containerorchestrators.openshifthandler.models import OpenshiftProject


def run(resource, **kwargs):
    set_progress(f"Openshift Project Delete plugin running for resource: {resource}")

    cf_value = resource.get_cf_values_as_dict()
    openshift_project_id = cf_value.get("openshift_project_id", None)

    if openshift_project_id is None or openshift_project_id == "":
        return (
            "SUCCESS",
            "Openshift Project {0} deleted successfully".format(resource.name),
            "",
        )

    try:
        project_obj = OpenshiftProject.objects.get(id=openshift_project_id)
    except Exception:
        return (
            "SUCCESS",
            "Openshift Project {0} deleted successfully".format(resource.name),
            "",
        )

    wrapper = project_obj.container_orchestrator.cast().get_api_wrapper()

    url = (
        wrapper.get_base_url(version=None)
        + f"/project.openshift.io/v1/projects/{resource.openshift_project_name}"
    )

    try:
        wrapper.requests_delete(url)
    except Exception as err:
        return "FAILURE", "", f"{err}"

    project_obj.delete()

    return "SUCCESS", f"{resource.openshift_project_name} deleted successfully", ""