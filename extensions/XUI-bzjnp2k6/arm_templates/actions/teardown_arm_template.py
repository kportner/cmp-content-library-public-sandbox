"""
Teardown Service Item Action for ARM Template Blueprint

This action was created by the ARM Builder Blueprint

Do not edit this script directly as all resources provisioned by the ARM
Builder Blueprint use this script. If you need to make one-off modifications,
copy this script and create a new action leveraged by the blueprint that needs
the modifications.
"""

from infrastructure.models import Environment
from utilities.exceptions import NotFoundException

if __name__ == "__main__":
    import django

    django.setup()
from resourcehandlers.azure_arm.models import AzureARMHandler
from common.methods import set_progress
import sys
from utilities.logger import ThreadLogger
from msrestazure.azure_exceptions import CloudError
from xui.arm_templates.shared import (
    get_provider_type_from_id,
    get_resource_type_from_id,
    get_api_version,
)

logger = ThreadLogger(__name__)


def run(job, *args, **kwargs):
    resource = job.resource_set.first()
    if resource:
        set_progress(f"ARM Delete plugin running for resource: {resource}")
        try:
            env_id = resource.arm_env_id
            if not env_id:
                raise Exception(f"Environment ID not found.")
        except:
            msg = "No Environment ID set on the blueprint, continuing"
            set_progress(msg)
            return "SUCCESS", msg, ""

        # Instantiate Azure Resource Client
        env = Environment.objects.get(id=env_id)
        rh = env.resource_handler.cast()
        wrapper = rh.get_api_wrapper()
        resource_client = wrapper.resource_client
        azure_resource_ids = []

        # Gather IDs to be deleted
        result_found = True
        resource_dict = resource.get_cf_values_as_dict()
        i = 0
        while result_found:
            field_name_id = f"output_resource_{i}_id"
            try:
                resource_id = resource_dict[field_name_id]
            except:
                result_found = False
                break
            resource_type = get_resource_type_from_id(resource_id)
            if resource_type == "virtualMachines":
                logger.info(
                    f"Virtual Machine Resource found. ID: "
                    f"{resource_id}. Virtual machines will be deleted"
                    f"first."
                )
                if len(resource_id.split("/")) == 9:
                    azure_resource_ids.insert(0, resource_id)
                i += 1
                continue
            if resource_id not in azure_resource_ids:
                # If the resource ID has 9 splits on '/' then it is a parent
                # resource. If not, it is a child resource and deleting the
                # parent should remove the child as well.
                if len(resource_id.split("/")) == 9:
                    azure_resource_ids.append(resource_id)
            i += 1

        set_progress(f"{len(azure_resource_ids)} Azure resources will be " f"deleted")

        # Delete Resources
        attempts = 0
        while attempts < 2:
            failed_ids = []
            for resource_id in azure_resource_ids:
                api_version = get_api_version(resource_client, resource_id)
                try:
                    resource_client.resources.get_by_id(resource_id, api_version)
                except CloudError as ce:
                    try:
                        reason = ce.error.error
                    except:
                        reason = ce.error.response.reason
                    if (
                        reason == "ResourceNotFound"
                        or reason == "DeploymentNotFound"
                        or reason == "Not Found"
                    ):
                        logger.info(
                            f"resource_id: {resource_id} could not be "
                            f"found, it may have already been deleted. "
                            f"Continuing"
                        )
                        continue
                    else:
                        failed_ids.append(resource_id)
                        logger.warn(
                            f"Could not get resource id: {resource_id}"
                            f"Error: {ce.message}"
                        )
                        continue
                try:
                    set_progress(
                        f"Deleting Azure Resource with ID: "
                        f"{resource_id}, using api_version: "
                        f"{api_version}"
                    )
                    response = resource_client.resources.delete_by_id(
                        resource_id, api_version
                    )
                    # Need to wait for each delete to complete in case there are
                    # resources dependent on others (VM disks, etc.)
                    wrapper._wait_on_operation(response)
                except:
                    error_string = (
                        f"Error: {sys.exc_info()[0]}. {sys.exc_info()[1]},"
                        f" line: {sys.exc_info()[2].tb_lineno}"
                    )
                    msg = (
                        f"Delete Failed on resource_id: {resource_id}. "
                        f"Error: {error_string}."
                    )
                    if attempts == 0:
                        msg = (
                            f"{msg} Deletion will be retried after all "
                            f"other resources are finished with deletion."
                        )
                    logger.warn(msg)
                    failed_ids.append(resource_id)
            if len(failed_ids) > 0:
                # Retry if object deletions failed. We may have cleaned up the
                # dependent objects and deletion may succeed on the 2nd pass
                attempts += 1
            else:
                break
        # Set CB Server Records to HISTORICAL if they are deleted by ARM
        for server in resource.server_set.all():
            created_by_arm = server.get_cfv_for_custom_field("created_by_arm").value
            if created_by_arm:
                try:
                    server.refresh_info()
                except CloudError as ce:
                    try:
                        reason = ce.error.error
                    except:
                        reason = ce.error.response.reason
                    if (
                            reason == "ResourceNotFound"
                            or reason == "DeploymentNotFound"
                            or reason == "Not Found"
                    ):
                        logger.info(f'Server refresh failed for '
                                    f'{server.hostname}, assuming deleted by '
                                    f'ARM - setting server to HISTORICAL.')
                        server.status = 'HISTORICAL'
                        server.save()
        if len(failed_ids) > 0:
            logger.error(f"These IDs failed deletion: {failed_ids}")
            return "WARNING", "Some resources failed deletion", ""
        else:
            return "SUCCESS", "All resources successfully deleted", ""

    else:
        set_progress("Resource was not found")
        return "SUCCESS", "Resource was not found", ""


if __name__ == "__main__":
    run()
