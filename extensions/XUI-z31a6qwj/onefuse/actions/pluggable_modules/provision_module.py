if __name__ == '__main__':
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.append('/opt/cloudbolt')
    django.setup()

import json
from common.methods import set_progress
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities
from utilities.logger import ThreadLogger
from jobs.models import Job

logger = ThreadLogger(__name__)


def get_module_name(ofm, response_json):
    path = response_json["_links"]["policy"]["href"].replace('/api/v3/onefuse',
                                                             '')
    policy_response = ofm.get(path)
    policy_response.raise_for_status()
    policy_json = policy_response.json()
    module_name = policy_json["_links"]["blueprint"]["title"]
    return module_name


def run(job, **kwargs):
    server = job.server_set.first()
    if server:
        utilities = Utilities(logger)
        logger.debug(f"Dictionary of keyword args passed to this "
                                  f"plug-in: {kwargs.items()}")
        hook_point = kwargs.get("hook_point")
        if hook_point is None:
            # hostname overwrite isn't passing the hook_point in to the job
            hook_point = 'generated_hostname_overwrite'
        properties_stack = utilities.get_cb_object_properties(server,
                                                              hook_point)
        module_prefix = 'OneFuse_PluggableModulePolicy_'
        if hook_point == "generated_hostname_overwrite":
            hook_point_string = "HostnameOverwrite"
        elif hook_point == "pre_create_resource":
            hook_point_string = "PreCreateResource"
        elif hook_point == "pre_application":
            hook_point_string = "PreApplication"
        elif hook_point == "post_provision":
            hook_point_string = "PostProvision"
        else:
            logger.info("Pluggable Module action launched at an unsupported "
                        f"hook point: {hook_point}. Exiting")
            return "SUCCESS", "", ""
        logger.debug(f'prefix: {module_prefix}{hook_point_string}_')
        endpoint_policies = utilities.get_connection_and_policy_values(
            f'{module_prefix}{hook_point_string}_', properties_stack)
        logger.debug(f'endpoint_policies: {endpoint_policies}')
        # Loop through endpoint policies and execute applicable policies
        if endpoint_policies:
            # Sort Module policies for hook point alphanumerically on suffix
            endpoint_policies.sort(key=lambda x: x["suffix"], reverse=False)
            for endpoint_policy in endpoint_policies:
                onefuse_endpoint = endpoint_policy["endpoint"]
                policy_name = endpoint_policy["policy"]
                suffix = endpoint_policy["suffix"]
                properties_stack["OneFuse_Suffix"] = suffix
                properties_stack["order_id"] = job.order_item.order.id
                logger.debug(f"Starting OneFuse Pluggable Module Policy: "
                             f"{policy_name}, Endpoint: {onefuse_endpoint}, "
                             f"suffix: {suffix}")
                try:
                    tracking_id = server.OneFuse_Tracking_Id
                except:
                    tracking_id = ""
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                set_progress(f'Calling OneFuse to provision Module '
                             f'Managed Object. Policy: {policy_name}')
                response_json = ofm.provision_module(policy_name,
                                                     properties_stack,
                                                     tracking_id)
                response_json["endpoint"] = onefuse_endpoint
                response_json["OneFuse_CBHookPointString"] = hook_point_string
                response_json["OneFuse_Suffix"] = suffix
                response_json["OneFuse_PluggableModuleName"] = get_module_name(
                    ofm, response_json
                )
                response_json = utilities.delete_output_job_results(
                    response_json, 'pluggable_module')
                output_property = f'OneFuse_PluggableModule_{suffix}'
                utilities.check_or_create_cf(output_property, "TXT")
                server.set_value_for_custom_field(output_property,
                                                  json.dumps(response_json))
                server.OneFuse_Tracking_Id = response_json["trackingId"]
                server.save()
                logger.info(f"OneFuse Pluggable Module execution complete. "
                            f"for policy: {policy_name}")
            return "SUCCESS", "", ""
        else:
            logger.info("OneFuse_PluggableModule_ parameter for hook point:"
                        f" {hook_point} is not set on the server, OneFuse "
                        f"Pluggable Modules will not be executed for hook "
                        f"point.")
            return "SUCCESS", "", ""
    else:
        logger.error("Server was not found")
        return "FAILURE", "", "Server was not found"


if __name__ == '__main__':
    job_id = sys.argv[1]
    job = Job.objects.get(id=job_id)
    run = run(job)
    if run[0] == 'FAILURE':
        set_progress(run[1])
