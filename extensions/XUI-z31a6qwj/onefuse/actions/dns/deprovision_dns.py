if __name__ == "__main__":
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.append("/opt/cloudbolt")
    sys.path.append("/var/opt/cloudbolt/proserv")
    django.setup()

from common.methods import set_progress
from jobs.models import Job
from utilities.logger import ThreadLogger
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities

logger = ThreadLogger(__name__)


def run(job, **kwargs):
    server = job.server_set.first()
    if server:
        utils = Utilities(logger)
        logger.debug(f"Dictionary of keyword args passed to this "
                     f"plug-in: {kwargs.items()}")
        hook_point = 'post_decom'
        properties_stack = utils.get_cb_object_properties(server,
                                                                  hook_point)
        dns_props = utils.get_matching_properties('OneFuse_Dns_Nic',
                                                      properties_stack)
        logger.debug(f'dns_props: {dns_props}')
        if len(dns_props) > 0:
            for dns_prop in dns_props:
                dns_id = dns_prop.get("id")
                dns_name = dns_prop.get("name")
                onefuse_endpoint = dns_prop.get("endpoint")
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                set_progress(f'Calling OneFuse to delete DNS '
                             f'Managed Object. ID: {dns_id}')
                ofm.deprovision_dns(dns_id)
                logger.info("DNS deletion completed.")
        else:
            logger.info("No OneFuse_Dns_NicN properties found on "
                         "the server")
        
        additional_prop = 'OneFuse_Dns_Additional_'
        additional_objects = utils.get_key_value_objects(additional_prop,
                                                         properties_stack)
        logger.debug(f'additional_objects: {additional_objects}')
        for additional_object in additional_objects:
            mo = additional_object["value"]
            suffix = additional_object["suffix"]
            onefuse_endpoint = mo["endpoint"]
            mo_name = mo["name"]
            mo_id = mo["id"]
            logger.debug(f"Starting OneFuse Delete Additional DNS "
                         f"Object. Name: {mo_name}, "
                         f"Endpoint: {onefuse_endpoint}, "
                         f"DNS ID: {mo_id}, "
                         f"Suffix: {suffix}")
            from xui.onefuse.globals import VERIFY_CERTS
            ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                   logger=logger)
            set_progress(f'Calling OneFuse to deprovision Additional DNS '
                         f'Managed Object. ID: {mo_id}. Suffix: {suffix}')
            ofm.deprovision_dns(mo_id)
            logger.info("Additional DNS deletion completed.")
        
        return "SUCCESS", "", ""
    else:
        logger.error("Server was not found")
        return "FAILURE", "", "Server was not found"


if __name__ == "__main__":
    job_id = sys.argv[1]
    j = Job.objects.get(id=job_id)
    run = run(j)
    if run[0] == "FAILURE":
        set_progress(run[1])