# Sample of submitting a generic OneFuse Pluggable Module request as XaaS

if __name__ == "__main__":
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.append("/opt/cloudbolt")
    sys.path.append("/var/opt/cloudbolt/proserv")
    django.setup()

from common.methods import set_progress
import json
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities
from utilities.logger import ThreadLogger
from jobs.models import Job

logger = ThreadLogger(__name__)


def run(job, *args, **kwargs):
    set_progress(f'kwargs: {kwargs}')
    resource = job.resource_set.first()
    module_policy_name = "{{resource.module_policy_name}}"
    onefuse_endpoint = "{{resource.onefuse_endpoint}}"
    tracking_id = "{{resource.OneFuse_Tracking_Id}}"
    if resource and onefuse_endpoint and module_policy_name:
        utilities = Utilities(logger)
        set_progress(f"This plug-in is running for resource {resource}")
        logger.debug(f"Dictionary of keyword args passed to this "
                     f"plug-in: {kwargs.items()}")
        set_progress(f"Starting OneFuse Pluggable Module Policy: "
                     f"{module_policy_name}, Endpoint: {onefuse_endpoint}")
        from xui.onefuse.globals import VERIFY_CERTS
        ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS, logger=logger)
        properties_stack = utilities.get_cb_object_properties(resource)
        response_json = ofm.provision_module(module_policy_name,
                                             properties_stack, tracking_id)
        utilities.check_or_create_cf("OneFuse_Naming_Resource")
        response_json["endpoint"] = onefuse_endpoint
        resource.OneFuse_Naming_Resource = json.dumps(response_json)
        resource.OneFuse_Tracking_Id = response_json.get("trackingId")
        resource.save()
        return "SUCCESS", "", ""
    else:
        set_progress(f"Resource, module_policy_name, or onefuse_endpoint were "
                     f"not found set on the resource. resource: {resource}, "
                     f"module_policy_name: {module_policy_name}, "
                     f"onefuse_endpoint: {onefuse_endpoint}")


if __name__ == "__main__":
    job_id = sys.argv[1]
    j = Job.objects.get(id=job_id)
    run = run(j)
    if run[0] == "FAILURE":
        set_progress(run[1])
