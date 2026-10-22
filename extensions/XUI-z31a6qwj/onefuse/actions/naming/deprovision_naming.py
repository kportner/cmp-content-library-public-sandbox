if __name__ == '__main__':
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.append('/opt/cloudbolt')
    django.setup()

import json
from common.methods import set_progress
from jobs.models import Job
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def run(job, **kwargs):
    utils = Utilities(logger)
    for server in job.server_set.all():
        logger.debug(f"Dictionary of keyword args passed to this "
                     f"plug-in: {kwargs.items()}")
        hook_point = 'post_decom'
        properties_stack = utils.get_cb_object_properties(server,
                                                                  hook_point)
        naming_json = server.get_cfv_for_custom_field("OneFuse_Naming")
        logger.debug(f'naming_json: {naming_json}')
        if naming_json:
            naming_json = naming_json.value_as_string
            mo = json.loads(naming_json)
            onefuse_endpoint = mo["endpoint"]
            mo_name = mo["name"]
            mo_id = mo["id"]
            if onefuse_endpoint and mo_id:
                logger.debug(f"Starting OneFuse Delete Name "
                             f"Object. Policy: {mo_name}, Endpoint: "
                             f"{onefuse_endpoint}, Name ID: {mo_id}")
                # Delete Name Object
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                set_progress(f'Calling OneFuse to deprovision Name '
                             f'Managed Object. ID: {mo_id}')
                deleted_name = ofm.deprovision_naming(mo_id)
                logger.info(f"Name was successfully deleted from the "
                             f"OneFuse database. Path: {deleted_name}")
                
            else:
                logger.info(f"OneFuse Naming, endpoint of Name ID was"
                            f" missing.")
        else:
            logger.info("No OneFuse Name Object found.")
        
        additional_prop = 'OneFuse_Naming_Additional_'
        additional_objects = utils.get_key_value_objects(additional_prop,
                                                         properties_stack)
        logger.debug(f'additional_objects: '
                     f'{additional_objects}')
        for additional_object in additional_objects:
            mo = additional_object["value"]
            suffix = additional_object["suffix"]
            onefuse_endpoint = mo["endpoint"]
            mo_name = mo["name"]
            mo_id = mo["id"]
            if onefuse_endpoint and mo_id:
                logger.debug(f"Starting OneFuse Delete Additional Name "
                             f"Object. Name: {mo_name}, "
                             f"Endpoint: {onefuse_endpoint}, "
                             f"Name ID: {mo_id}, "
                             f"Suffix: {suffix}")
                # Delete Name Object
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                set_progress(f'Calling OneFuse to deprovision Additional Name '
                             f'Managed Object. ID: {mo_id}. Suffix: {suffix}')
                deleted_name = ofm.deprovision_naming(mo_id)
                logger.info(f"Additional Name was successfully deleted "
                            f"from the OneFuse database. Path: {deleted_name}")
            else:
                logger.info(f"OneFuse Naming, endpoint of Name ID was"
                            f" missing, for Suffix: {suffix}")

        return "SUCCESS", "", ""
        
if __name__ == '__main__':
    job_id = sys.argv[1]
    job = Job.objects.get(id=job_id)
    run = run(job)
    if run[0] == 'FAILURE':
        set_progress(run[1])