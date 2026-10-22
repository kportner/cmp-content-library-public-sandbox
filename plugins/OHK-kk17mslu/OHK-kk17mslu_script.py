import json
from common.methods import set_progress
from infrastructure.models import CustomField
from containerorchestrators.openshifthandler.models import Openshift, OpenshiftProject

from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def get_or_create_custom_fields():
    CustomField.objects.get_or_create(
        name="openshift_project_name",
        label="Openshift Project Name",
        defaults={"type": "STR", "show_as_attribute": True},
    )
    CustomField.objects.get_or_create(
        name="openshift_project_id",
        label="Openshift Project ID",
        defaults={"type": "INT", "show_as_attribute": True},
    )


def generate_options_for_container_orchestrator_id(
    control_value=None, server=None, **kwargs
):
    options = [("", "---Select Container---")]
    for openshift in Openshift.objects.all():
        options.append((openshift.id, openshift.name))
    return options


def run(resource, **kwargs):
    # get or create custom fields if needed
    get_or_create_custom_fields()

    projectname = "{{ project_name }}"
    display_name = "{{ display_name }}"
    description = "{{ description }}"
    oc_handler = Openshift.objects.get(id="{{container_orchestrator_id}}")

    set_progress("Starting Provisioning Project...")

    payload = {
        "kind": "ProjectRequest",
        "apiVersion": "project.openshift.io/v1",
        "metadata": {
            "name": projectname,
        },
        "displayName": display_name,
        "description": description,
    }

    wrapper = oc_handler.get_api_wrapper()
    url = (
        wrapper.get_base_url(version=None) + f"/project.openshift.io/v1/projectrequests"
    )

    try:
        wrapper.requests_post(url, data=json.dumps(payload))
    except Exception as err:
        return "FAILURE", f"{err}", f"Failed to create project {projectname}"

    total_created, _, _, _ = oc_handler.sync_resource_metadata(
        sync_resource_type="sync_namespaces", selected_resources=[projectname]
    )

    if total_created:
        project_obj = total_created[0]
    else:
        project_obj = OpenshiftProject.objects.filter(
            container_orchestrator=oc_handler, name=projectname
        ).first()

    resource.name = projectname
    resource.openshift_project_name = projectname
    resource.openshift_project_id = project_obj.id if project_obj else 0
    resource.save()

    return "SUCCESS", f"Project '{projectname}' created successfully", ""