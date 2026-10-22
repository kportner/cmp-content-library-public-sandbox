"""
Build service item action for Azure Resource Manager Templates deployment

This action was created by the ARM Template UI Extension

Do not edit this script directly as all resources provisioned by the ARM
Builder Blueprint use this script. If you need to make one-off modifications,
copy this script and create a new action leveraged by the blueprint that needs
the modifications.
"""
from jobs.models import Job
from common.methods import set_progress
from infrastructure.models import Environment
import json
from utilities.logger import ThreadLogger
from xui.arm_templates.shared import (
    get_or_create_cfs,
    get_arm_template_for_resource,
    get_arm_deploy_params,
    submit_arm_template_request,
    create_deployment_params,
    write_outputs_to_resource,
    render_parameters,
)

logger = ThreadLogger(__name__)


##################
def run(job, **kwargs):
    resource = kwargs.get("resource")
    if resource:
        set_progress(f"Starting deploy of ARM Template for resource: " 
                     f"{resource}")
        arm_template = get_arm_template_for_resource(resource)
        env_id = resource.get_cfv_for_custom_field("arm_env_id").value
        resource_group = resource.get_cfv_for_custom_field(
            "arm_resource_group").value

        # Other Params
        owner = job.owner
        group = resource.group
        env = Environment.objects.get(id=env_id)
        rh = env.resource_handler.cast()
        resource = render_parameters(resource, env, job)
        deployment_name = resource.get_cfv_for_custom_field(
            "arm_deployment_name").value
        parameters = get_arm_deploy_params(resource, env)

        # Convert ARM template to dict
        template = json.loads(arm_template)

        wrapper = rh.get_api_wrapper()
        deployment = submit_arm_template_request(
            deployment_name, resource_group, template, parameters, wrapper
        )
        get_or_create_cfs()
        create_deployment_params(
            resource, deployment, rh, env, resource_group, wrapper, group, job
        )
        write_outputs_to_resource(resource, deployment)

        return "SUCCESS", "ARM Template deployment complete", ""
    else:
        msg = f"Resource not found."
        set_progress(msg)
        return "FAILURE", msg, ""
