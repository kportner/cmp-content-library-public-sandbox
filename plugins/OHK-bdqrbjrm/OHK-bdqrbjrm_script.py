import time
from common.methods import set_progress
from infrastructure.models import Environment
from resourcehandlers.aws.models import AWSHandler
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def get_aws_rh_and_region(resource):
    rh_aws_id = resource.aws_rh_id
    aws_region =  resource.aws_region
    rh_aws = None

    if rh_aws_id != "" or rh_aws_id is not None:
        rh_aws = AWSHandler.objects.get(id=rh_aws_id)

    return aws_region, rh_aws
    

    
def run(job, resource, logger=None, **kwargs):
    # The Environment ID and PostgreSQL database data dict were stored as attributes on
    # this service by a build action.
    postgresql_instance_identifier = resource.db_identifier

    # get aws region and resource handler object
    aws: AWSHandler
    region, aws, = get_aws_rh_and_region(resource)

    if aws is None or aws == "":
        return  "WARNING", f"PostgreSQL database instance {postgresql_instance_identifier} not found, it may have already been deleted", ""

    set_progress('Connecting to Amazon RDS')
    
     # initialize boto3 client
    client = aws.get_boto3_client(region, 'rds')
    
    job.set_progress('Stopping PostgreSQL database instance {0}...'.format(postgresql_instance_identifier))
    
    try:
        # fetch PostgreSQL database instance
        postgresql_rsp = client.describe_db_instances(DBInstanceIdentifier=postgresql_instance_identifier)['DBInstances'][0]
    except Exception as err:
        raise RuntimeError(err)
    
    if postgresql_rsp['DBInstanceStatus'] != "available":
        return "WARNING", f"PostgreSQL database instance {postgresql_instance_identifier} is not in available state, it may have already been stopped or in-process state.", ""
    
    try:
        postgresql_rsp = client.stop_db_instance(
                        DBInstanceIdentifier=postgresql_instance_identifier
                    )['DBInstance']
    
    except Exception as err:
        raise RuntimeError(err)
    
    if postgresql_rsp['DBInstanceStatus'] != "stopped":
        while True:
            try:
                # fetch PostgreSQL database instance
                postgresql_rsp = client.describe_db_instances(DBInstanceIdentifier=postgresql_instance_identifier)['DBInstances'][0]
            except Exception as err:
                break
            
            if postgresql_rsp['DBInstanceStatus'] == "stopped":
                break
        
            time.sleep(60)
    
    resource.db_status = "stopped"
    resource.save()

    job.set_progress('PostgreSQL database instance {0} stopped successfully.'.format(postgresql_instance_identifier))

    return 'SUCCESS', f'PostgreSQL database instance {postgresql_instance_identifier} stopped successfully.', ''