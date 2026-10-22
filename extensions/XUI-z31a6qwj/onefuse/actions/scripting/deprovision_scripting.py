if __name__ == '__main__':
    import os
    import sys
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "settings")
    sys.path.append('/opt/cloudbolt')
    django.setup()

from common.methods import set_progress
from onefuse.cloudbolt_admin import CbOneFuseManager, Utilities
from onefuse.exceptions import OneFuseError
from utilities.logger import ThreadLogger
from jobs.models import Job
logger = ThreadLogger(__name__)


def run(job, **kwargs):
    server = job.server_set.first()
    if server:
        utilities = Utilities(logger)
        logger.debug(f"Dictionary of keyword args passed to this "
                     f"plug-in: {kwargs.items()}")
        properties_stack = utilities.get_cb_object_properties(server)
        matching_props = utilities.get_matching_properties('OneFuse_Scripting_',
                                                           properties_stack)
        if len(matching_props) > 0:
            matching_props = utilities.sort_deprovision_props(matching_props)
            logger.debug(f'matching_props: {matching_props}')
            hostname = server.hostname
            for matching_prop in matching_props:
                id = matching_prop.get("id")
                onefuse_endpoint = matching_prop.get("endpoint")
                logger.debug(f'Preparing to deprovision scripting'
                             f' for hostname: {hostname}, suffix: '
                             f'{matching_prop["OneFuse_Suffix"]}, Hook string: '
                             f'{matching_prop["OneFuse_CBHookPointString"]}')
                from xui.onefuse.globals import VERIFY_CERTS
                ofm = CbOneFuseManager(onefuse_endpoint, VERIFY_CERTS,
                                       logger=logger)
                try:
                    set_progress(f'Calling OneFuse to deprovision Scripting '
                                 f'Managed Object. ID: {id}')
                    ofm.deprovision_scripting(id)
                except OneFuseError as err:
                    if err.args[0].find('is already archived') > -1:
                        logger.info('Object is already archived. Continuing.')
                    else:
                        raise
                logger.info("Scripting deletion completed.")
            return "SUCCESS", "", ""
        else:
            logger.info("No OneFuse_Scripting_ properties found on the server"
                        ", Deprovision Scripting will not be executed.")
    else:
        logger.error("Server was not found")
        return "FAILURE", "", "Server was not found"


if __name__ == '__main__':
    job_id = sys.argv[1]
    job = Job.objects.get(id=job_id)
    run = run(job)
    if run[0] == 'FAILURE':
        set_progress(run[1])