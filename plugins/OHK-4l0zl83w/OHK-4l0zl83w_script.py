"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
from infrastructure.models import CustomField
from containerorchestrators.openshifthandler.models import Openshift, OpenshiftProject
from common.methods import set_progress


def get_or_create_custom_fields():
    """
    Helper functions for main function to create custom field as needed
    """
    CustomField.objects.get_or_create(
        name="container_orchestrator_id",
        defaults={
            "label": "Container Orchestrator",
            "type": "INT",
        },
    )
    CustomField.objects.get_or_create(
        name="project_id",
        defaults={
            "label": "Project",
            "type": "INT",
        },
    )
    CustomField.objects.get_or_create(
        name="project_image_stream_id",
        defaults={
            "label": "Project Image Stream",
            "type": "INT",
        },
    )
    CustomField.objects.get_or_create(
        name="image_name",
        defaults={
            "label": "Image Name",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )
    CustomField.objects.get_or_create(
        name="application_name",
        defaults={
            "label": "Application Name",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )
    CustomField.objects.get_or_create(
        name="container_app_name",
        defaults={
            "label": "Name",
            "type": "STR",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )
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
        name="project_name",
        defaults={
            "label": "Namespace",
            "type": "STR",
        },
    )
    CustomField.objects.get_or_create(
        name="replicas",
        defaults={
            "label": "Replicas",
            "type": "INT",
            "show_as_attribute": True,
            "show_on_servers": True,
        },
    )

    CustomField.objects.get_or_create(
        name="image_stream",
        defaults={
            "label": "Image Stream",
            "type": "STR",
        },
    )

    CustomField.objects.get_or_create(
        name="image_tag",
        defaults={
            "label": "Image Tag",
            "type": "STR",
        },
    )

    CustomField.objects.get_or_create(
        name="image_registry",
        defaults={
            "label": "Image Registry",
            "type": "STR",
        },
    )

    CustomField.objects.get_or_create(
        name="insecure_img",
        defaults={
            "label": "Insecure Image",
            "type": "BOOL",
        },
    )


def get_redhat_internal_registry_images(project_id, image_name=None):
    project = OpenshiftProject.objects.get(id=project_id)

    container_orchestrator = project.container_orchestrator.cast()

    wrapper = container_orchestrator.get_api_wrapper()

    base_url = wrapper.get_clusterrole_url(None, skip_base_url_version=True)

    uri = f"{base_url}/image.openshift.io/v1/namespaces/{project.name}/imagestreams"

    if image_name:
        uri = f"{uri}/{image_name}"

    response = wrapper.requests_get(uri)

    return response.json()


def generate_options_for_container_orchestrator_id(
    control_value=None, server=None, **kwargs
):
    options = [("", "---Select Container---")]
    for openshift in Openshift.objects.all():
        options.append((openshift.id, openshift.name))
    return options


def generate_options_for_image_registry(control_value=None, server=None, **kwargs):
    return [
        ("", "---Select Image Registry---"),
        ("internal", "Image stream tag from internal registry"),
        ("external", "Image name from external registry"),
    ]


def generate_options_for_image_stream(control_value=None, server=None, **kwargs):
    options = [("", "---Select Image Stream---")]
    if control_value is None or control_value == "":
        return options

    registry_images = get_redhat_internal_registry_images(control_value)["items"]

    for img in registry_images:
        name = img["metadata"]["name"]
        options.append((f"img_name={name}, project_id={control_value}", name))

    return options


def generate_options_for_image_tag(control_value=None, server=None, **kwargs):
    options = [("", "---Select Image Tag---")]
    if control_value is None or control_value == "":
        return options

    control_value_dict = {
        img_stream_obj.split("=")[0].strip(): img_stream_obj.split("=")[1]
        for img_stream_obj in control_value.split(",")
    }

    if (
        len(control_value_dict) != 2
        or "img_name" not in control_value_dict
        or "project_id" not in control_value_dict
    ):
        return options

    registry_image_tags = get_redhat_internal_registry_images(
        control_value_dict["project_id"], control_value_dict["img_name"]
    )

    tags_status = {tag["tag"]: tag for tag in registry_image_tags["status"]["tags"]}

    for tag in registry_image_tags["spec"]["tags"]:
        image_ref_items = tags_status.get(tag["name"], {}).get("items", [])
        image_ref = "latest"

        if image_ref_items:
            image_ref = image_ref_items[0]["image"]

        options.append(
            (
                f"name={tag['from']['name']}, tag={tag['name']}, image_ref={image_ref}",
                tag["name"],
            )
        )

    return options


def generate_options_for_image_name(control_value=None, server=None, **kwargs):
    return [
        ("", "---Select Image---"),
        ("bitnami/nginx", "nginx"),
        ("bitnami/apache", "apache"),
    ]


def generate_options_for_project_id(control_value=None, server=None, **kwargs):
    options = [("", "---Select Project---")]
    if control_value is None or control_value == "":
        return options

    for openshift in OpenshiftProject.objects.filter(
        container_orchestrator__id=control_value
    ):
        options.append((openshift.id, openshift.name))

    return options


def generate_options_for_project_image_stream_id(
    control_value=None, server=None, **kwargs
):
    options = [("", "---Select Project For Image streams---")]
    if control_value is None or control_value == "":
        return options

    for openshift in OpenshiftProject.objects.filter(
        container_orchestrator__id=control_value
    ):
        options.append((openshift.id, openshift.name))

    return options


def run(job, resource, *args, **kwargs):
    set_progress("Validating container image form data...")

    # get or create custom fields as needed
    get_or_create_custom_fields()

    oc_handler = Openshift.objects.get(id="{{container_orchestrator_id}}")
    oc_project = OpenshiftProject.objects.get(id="{{project_id}}")
    image_name = "{{image_name}}"
    application_name = "{{application_name}}"
    name = "{{container_app_name}}"
    replicas = int("{{replicas}}")
    image_registry = "{{image_registry}}"
    project_image_stream_id = "{{project_image_stream_id}}"
    image_stream = "{{image_stream}}"
    image_tags = "{{image_tag}}"
    insecure_img = "{{insecure_img}}"

    container_image = kwargs.get("blueprint_context", {}).get("container_image", {})

    for field in ["__untrusted_expressions", "service_item_id"]:
        if field in container_image:
            del container_image[field]

    if not container_image:
        return (
            "FAILURE",
            "",
            f"Invalid blueprint order container image form data, please check and try again",
        )

    return "", "", ""