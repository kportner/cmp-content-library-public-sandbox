"""
This is a working sample CloudBolt plug-in for you to start with. The run method is required,
but you can change all the code within it. See the "CloudBolt Plug-ins" section of the docs for
more info and the CloudBolt forge for more examples:
https://github.com/CloudBoltSoftware/cloudbolt-forge/tree/master/actions/cloudbolt_plugins
"""
import time
import json
from common.methods import set_progress
from containerorchestrators.openshifthandler.models import Openshift, OpenshiftProject
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def clean_payload_data(payload_dict):
    for field in ["__untrusted_expressions", "service_item_id"]:
        if field in payload_dict:
            del payload_dict[field]

    return payload_dict


def verify_deployment_pods_status(oc_handler, app_name, namespace, replicas):
    wrapper = oc_handler.get_api_wrapper()
    base_url = "{}/pods".format(wrapper.get_base_url("v1", namespace))
    uri = f"{base_url}?labelSelector=app%3D{app_name}"

    try:
        pod_list = wrapper.requests_get(uri).json()["items"]
    except Exception as err:
        raise ValueError(f"Unexpected error occurred, errors: {err}")

    status = ""
    error_messages = []

    for pod in pod_list:
        status_dict = pod.get("status", {})
        status = status_dict.get("phase", "")

        if status == "Running":
            return status, []

        containerStatuses = status_dict.get("containerStatuses", [])

        for con_status in containerStatuses:
            state = con_status.get("state", {})

            con_error_dict = state.get(list(state.keys())[0], {})

            if con_error_dict:
                error_mgs = ", ".join(
                    [f"{key}:{value}" for key, value in con_error_dict.items()]
                )
                error_messages.append(error_mgs)

    return status, error_messages


def run(job, resource, *args, **kwargs):
    set_progress("Starting Provision of Openshift container application...")

    blueprint_context = kwargs.get("blueprint_context", {})
    deploy_image = clean_payload_data(blueprint_context.get("container_image", {}))
    advanced_options = clean_payload_data(blueprint_context.get("advanced_options", {}))

    if not advanced_options or not deploy_image:
        return (
            "FAILURE",
            "",
            f"Invalid blueprint order form data, please check and try again",
        )

    image_name = deploy_image.get("image_name", "")
    insecure_img = deploy_image.get("insecure_img", False)
    name = deploy_image["container_app_name"]
    application_name = deploy_image["application_name"]
    image_registry = deploy_image.get("image_registry", "external")
    project_image_stream_id = deploy_image.get("project_image_stream_id", 0)
    image_stream = deploy_image.get("image_stream", "")
    image_tag = deploy_image.get("image_tag", "")

    replicas = deploy_image["replicas"]
    oc_handler = Openshift.objects.get(id=deploy_image["container_orchestrator_id"])
    oc_project = OpenshiftProject.objects.get(id=deploy_image["project_id"])
    create_route = advanced_options["create_route"]

    application_target_port = advanced_options.get("application_target_port", "")
    service_payload_kwargs = {}
    route_payload_kwargs = {}

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

        route_payload_kwargs = {
            "host": advanced_options.get("application_hostname", ""),
            "path": advanced_options.get("application_path", ""),
            "targetPort": application_target_port,
        }

        application_target_port = f"{application_target_port}-tcp"

    # get service payload
    service_payload = oc_handler.build_service_payload(
        name, application_name, oc_project.name, **service_payload_kwargs
    )

    # get route payload
    route_payload = oc_handler.build_route_payload(
        name, application_name, oc_project.name, **route_payload_kwargs
    )

    add_latest_tag = False

    if image_registry == "external":
        # get imagestream payload
        imagestream_payload = oc_handler.build_imagestream_payload(
            name, application_name, oc_project.name, image_name, **{"type": "Source", "local": True}
        )
        imagestream_payload["spec"]["tags"][0]["importPolicy"]["scheduled"] = True
        
        logger.info("imagestream post request payload : {}".format(imagestream_payload))
        set_progress("Starting Provision ImageStream...")

        try:
            # create imagestream
            imagestream_rsp = oc_handler.create_application_imagestream(
                oc_project.name, imagestream_payload
            )
        except Exception as err:
            return "FAILURE", "", f"{err}"

        logger.info("imagestream response : {}".format(imagestream_rsp))

        create_img_stream_name = imagestream_rsp.get("metadata", {}).get("name", "")

        if create_img_stream_name != "":
            image_name = create_img_stream_name
            add_latest_tag = True
        else:
            images = imagestream_rsp.get("status", {}).get("images", [])

            if images:
                image_name = images[0]["image"]["dockerImageReference"]
    else:
        image_tag_dict = {
            img_tag_obj.split("=")[0].strip(): img_tag_obj.split("=")[1]
            for img_tag_obj in image_tag.split(",")
        }

        image_name = f"{image_tag_dict['name']}@{image_tag_dict['image_ref']}"
        image_tag = image_tag_dict["tag"]

        image_stream_dict = {
            img_stream_obj.split("=")[0].strip(): img_stream_obj.split("=")[1]
            for img_stream_obj in image_stream.split(",")
        }

        image_stream = image_stream_dict["img_name"]

    # get deployment payload
    deployment_payload = oc_handler.build_deployment_payload(
        name,
        application_name,
        oc_project.name,
        image_name,
        **{"replicas": replicas, "insecure": insecure_img},
    )
    
    image_stream_tag_name = f"{image_name}:latest"
    trigger_field_path = f'spec.template.spec.containers[0].image'
    trigger_image = [{"from":{"kind":"ImageStreamTag","name":image_stream_tag_name,'namespace':oc_project.name},"fieldPath":trigger_field_path}]
    deployment_payload["metadata"]["annotations"]["image.openshift.io/triggers"] = json.dumps(trigger_image)
    
    if add_latest_tag:
        image_name = f"{image_name}:latest"

    deployment_payload["spec"]["template"]["spec"]["containers"][0][
        "image"
    ] = image_name
    deployment_payload["spec"]["template"]["spec"]["containers"][0][
        "imagePullPolicy"
    ] = "Always"

    logger.info("deployment post request payload : {}".format(deployment_payload))
    set_progress("Starting Provision deployment...")

    try:
        # create deployment
        deployment_rsp = oc_handler.create_application_deployment(
            oc_project.name, deployment_payload
        )
    except Exception as err:
        return "FAILURE", "", f"{err}"

    logger.info("deployment response : {}".format(deployment_rsp))
    logger.info("service post request payload : {}".format(service_payload))
    set_progress("Starting Provision service...")

    try:
        # create service
        service_rsp = oc_handler.create_application_service(
            oc_project.name, service_payload
        )
    except Exception as err:
        return "FAILURE", "", f"{err}"

    logger.info("service response : {}".format(service_rsp))

    if create_route:
        logger.info("route post request payload : {}".format(route_payload))
        set_progress("Starting Provision route...")

        try:
            # create route
            route_rsp = oc_handler.create_application_route(
                oc_project.name, route_payload
            )
        except Exception as err:
            return "FAILURE", "", f"{err}"

        logger.info("route response : {}".format(route_rsp))

        resource.application_route = "{0}{1}".format(
            route_rsp["spec"]["host"], advanced_options.get("application_path", "")
        )

    # update resource metadata
    resource.container_orchestrator_id = oc_handler.id
    resource.project_id = oc_project.id
    resource.project_name = oc_project.name
    resource.image_name = image_name
    resource.name = name
    resource.application_name = application_name
    resource.create_route = create_route
    resource.container_app_name = name
    resource.replicas = replicas
    resource.project_image_stream_id = project_image_stream_id
    resource.image_stream = image_stream
    resource.image_tag = image_tag
    resource.image_registry = image_registry
    resource.insecure_img = insecure_img

    if application_target_port:
        resource.application_target_port = application_target_port
        resource.application_path = advanced_options.get("application_path", "")

    resource.save()

    set_progress("Checking deployment status...")
    start_time = time.time()

    while True:
        try:
            deployment_status = oc_handler.get_deployment_detail_raw(
                name, oc_project.name
            )["status"]
        except Exception as err:
            return "FAILURE", "", f"{err}"

        availableReplicas = deployment_status.get("availableReplicas", 0)

        if availableReplicas != 0 and availableReplicas <= deployment_status.get(
            "replicas", 0
        ):
            break

        time_diff, _ = divmod(time.time() - start_time, 60)

        if time_diff > 2:
            set_progress("Checking deployment pod's status...")
            status, error_messages = verify_deployment_pods_status(
                oc_handler, name, oc_project.name, replicas
            )
            if status != "Running":
                set_progress(
                    f"Unexpected error occurred, errors are: {' ,'.join(error_messages)}"
                )
                return (
                    "FAILURE",
                    "",
                    f"Unexpected error occurred, errors are: {' ,'.join(error_messages)}",
                )

            break

        time.sleep(5)

    try:
        # sync deployments
        oc_handler.import_deployments(selected_deployments=[name])

        # get all created pods name
        created_pods = [
            pod
            for pod in oc_handler.get_pod_names(
                namespace=oc_project.name, force_sync=True
            )
            if pod.startswith(f"{name}-")
        ]

        if created_pods:
            # sync pods
            oc_handler.import_pods(selected_pods=created_pods)
    except Exception as err:
        pass

    return "SUCCESS", "Openshift container application deployed successfully", ""