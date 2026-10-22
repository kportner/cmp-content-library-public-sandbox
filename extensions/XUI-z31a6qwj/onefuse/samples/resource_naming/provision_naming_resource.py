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
        utilities.verbose_logging(f"Dictionary of keyword args passed to this "
                                  f"plug-in: {kwargs.items()}")
        endpoint_policy = resource.get_cfv_for_custom_field(
                                        "OneFuse_Deployment_NamingPolicy")
        if endpoint_policy: 
            endpoint_policy = endpoint_policy.value_as_string
            onefuse_endpoint = endpoint_policy.split(':')[0]
            naming_policy_name = endpoint_policy.split(':')[1]
            set_progress(f"Starting OneFuse Deployment Naming Policy: "
                        f"{naming_policy_name}, Endpoint: {onefuse_endpoint}")
            try: 
                tracking_id = resource.OneFuse_Tracking_Id
            except: 
                tracking_id = ""
            from xui.onefuse.globals import VERIFY_CERTS
            ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                   logger=logger)
            name_json = ofm.provision_naming(naming_policy_name,resource, 
                                             tracking_id)            
            deployment_name = name_json.get("name")
            resource.name = deployment_name
            utilities.check_or_create_cf("OneFuse_Naming_Deployment")
            name_json["endpoint"] = onefuse_endpoint
            resource.OneFuse_Naming_Deployment = json.dumps(name_json)
            resource.OneFuse_Tracking_Id = name_json.get("trackingId")
            resource.save()
            set_progress(f"Resource name being set to: {resource.name}")
            return "SUCCESS", deployment_name, ""
        else: 
            set_progress(f"OneFuse_Deployment_NamingPolicy parameter is not set "
                         f"on the resource, OneFuse deployment naming will not "
                         f"be executed. Keeping existing hostname")
    else: 
        set_progress("Resource was not found")
