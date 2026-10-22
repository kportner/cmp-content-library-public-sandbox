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
    resource = job.resource_set.first()
    if resource:
        utilities = Utilities(logger)
        set_progress(f"This plug-in is running for resource {resource}")
        logger.debug(f"Dictionary of keyword args passed to this "
                                  f"plug-in: {kwargs.items()}")
        onefuse_endpoint = "{{resource.onefuse_endpoint}}"
        naming_policy_name = "{{resource.naming_policy_name}}"
        tracking_id = "{{resource.OneFuse_Tracking_Id}}"
        set_progress(f"Starting OneFuse Naming Policy: "
                    f"{naming_policy_name}, Endpoint: {onefuse_endpoint}")
        from xui.onefuse.globals import VERIFY_CERTS
        ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS, logger=logger)
        properties_stack = utilities.get_cb_object_properties(resource)
        response_json = ofm.provision_naming(naming_policy_name,
                                             properties_stack, tracking_id)
        resource_name = response_json.get("name")
        resource.name = resource_name
        utilities.check_or_create_cf("OneFuse_Naming_Resource")
        response_json["endpoint"] = onefuse_endpoint
        resource.OneFuse_Naming_Resource = json.dumps(response_json)
        resource.OneFuse_Tracking_Id = response_json.get("trackingId")
        resource.save()
        set_progress(f"Resource name being set to: {resource.name}")
        return "SUCCESS", resource_name, ""
    else: 
        set_progress("Resource was not found")


if __name__ == "__main__":
    job_id = sys.argv[1]
    j = Job.objects.get(id=job_id)
    run = run(j)
    if run[0] == "FAILURE":
        set_progress(run[1])