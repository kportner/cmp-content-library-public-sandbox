from jobs.models import Job

if __name__ == '__main__':
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.append('/opt/cloudbolt')
    django.setup()

from common.methods import set_progress
from xui.onefuse.globals import (
    MAX_RUNS, IGNORE_PROPERTIES, UPSTREAM_PROPERTY
)
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def run(job, **kwargs):
    server = job.server_set.first()
    utilities = Utilities(logger)
    if server:
        logger.debug(f"Dictionary of keyword args passed to this plug-in: "
                     f"{kwargs.items()}")
        hook_point = kwargs.get("hook_point")
        if hook_point is None:
            # hostname overwrite isn't passing the hook_point in to the job
            hook_point = 'generated_hostname_overwrite'
        properties_stack = utilities.get_cb_object_properties(server,
                                                              hook_point)
        endpoint_policies = utilities.get_connection_and_policy_values(
            'OneFuse_PropertyToolkit', properties_stack)
        if endpoint_policies:
            if len(endpoint_policies) == 1:
                total_runs = 0
                endpoint_policy = endpoint_policies[0]
                onefuse_endpoint = endpoint_policy["endpoint"]
                ptk_enabled = endpoint_policy["policy"]
                if ptk_enabled.lower() != "true":
                    logger.info(f'OneFuse_PropertyToolkit value was not'
                                 f' set to true. Exiting. Value: '
                                 f'{ptk_enabled}')
                    return "SUCCESS", "", ""
                if hook_point == 'generated_hostname_overwrite':
                    calculated_max_runs = MAX_RUNS
                else:
                    calculated_max_runs = 1
                logger.debug(f'PTK running at {hook_point} max runs set '
                             f'to: {calculated_max_runs}')
                while total_runs < calculated_max_runs:
                    logger.info(f'Starting PTK run #: {total_runs + 1}')
                    # OneFuse_SPS groups
                    from xui.onefuse.globals import VERIFY_CERTS
                    ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                           logger=logger)
                    sps_properties = ofm.get_sps_properties(
                                            properties_stack,
                                            UPSTREAM_PROPERTY,
                                            IGNORE_PROPERTIES)
                    properties_stack = ofm.render_and_apply_properties(
                        sps_properties, server, properties_stack)

                    # OneFuse_CreateProperties
                    create_properties = ofm.get_create_properties(
                        properties_stack)
                    properties_stack = ofm.render_and_apply_properties(
                        create_properties, server, properties_stack)

                    # No need for CreateTags, in CB these are a function
                    # of the resource handler and can be driven by looking
                    # at a specific property. What you could do is set the
                    # resource handler to look at a tagEnv parameter to set
                    # the tag value for env,but use the PTK to drive the
                    # tagEnv parameter
                    # Regenerate the properties stack at the end of each
                    # run to ensure all updated properties are captured
                    properties_stack = utilities.get_cb_object_properties(
                        server)
                    total_runs += 1

                return "SUCCESS", "", ""
            else:
                logger.error(f'More than a single OneFuse_PropertyToolkit'
                             f' value was found, unable to proceed. Number: '
                             f'{len(endpoint_policies)}')
                return "FAILURE", "", "More than one PTK value found"
        else:
            logger.info("OneFuse_PropertyToolkit parameter is not set on "
                        "the server, OneFuse Property Toolkit will not be "
                        "executed.")
    else:
        logger.error("Server was not found")
        return "FAILURE", "", "Server was not found"


if __name__ == '__main__':
    job_id = sys.argv[1]
    job = Job.objects.get(id=job_id)
    run = run(job)
    if run[0] == 'FAILURE':
        set_progress(run[1])
