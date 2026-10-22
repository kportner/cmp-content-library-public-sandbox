if __name__ == '__main__':
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.append('/opt/cloudbolt')
    django.setup()

from common.methods import set_progress
from jobs.models import Job
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities
from utilities.logger import ThreadLogger
from jobs.models import Job

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
        ipam_props = utils.get_matching_properties('OneFuse_Ipam_Nic',
                                                       properties_stack)
        logger.debug(f'ipam_props: {ipam_props}')
        if len(ipam_props) > 0:
            for ipam_prop in ipam_props:
                # ipam_json = ipam_prop
                ipam_id = ipam_prop.get("id")
                ipam_hostname = ipam_prop.get("hostname")
                onefuse_endpoint = ipam_prop.get("endpoint")
                logger.debug(f'Preparing to deprovision IPAM for '
                             f'hostname: {ipam_hostname}')
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                set_progress(f'Calling OneFuse to deprovision IPAM '
                             f'Managed Object. ID: {ipam_id}')
                ofm.deprovision_ipam(ipam_id)
                logger.info("IPAM deletion completed.")
            
        else:
            logger.info("No OneFuse_Ipam_NicN properties found on "
                        "the server.")
        
        additional_prop = 'OneFuse_Ipam_Additional_'
        additional_objects = utils.get_key_value_objects(additional_prop,
                                                         properties_stack)
        logger.debug(f'additional_objects: {additional_objects}')
        for additional_object in additional_objects:
            mo = additional_object["value"]
            suffix = additional_object["suffix"]
            onefuse_endpoint = mo["endpoint"]
            mo_name = mo["hostname"]
            mo_id = mo["id"]
            logger.debug(f"Starting OneFuse Delete Additional IPAM "
                         f"Object. Name: {mo_name}, "
                         f"Endpoint: {onefuse_endpoint}, "
                         f"IPAM ID: {mo_id}, "
                         f"Suffix: {suffix}")
            from xui.onefuse.globals import VERIFY_CERTS
            ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                   logger=logger)
            set_progress(f'Calling OneFuse to deprovision Additional IPAM '
                         f'Managed Object. ID: {mo_id}. Suffix: {suffix}')
            ofm.deprovision_ipam(mo_id)
            logger.info("Additional IPAM deletion completed.")
        
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