import time
from common.methods import set_progress
from infrastructure.models import Environment
from resourcehandlers.aws.models import AWSHandler
from utilities.logger import ThreadLogger

logger = ThreadLogger(__name__)


def get_aws_rh_and_region(resource):
    # The AWS Handler ID and AWS region were stored as attributes
    # this service by a build/sync action.
    rh_aws_id = resource.aws_rh_id
    aws_region =  resource.aws_region
    rh_aws = None

    if rh_aws_id != "" or rh_aws_id is not None:
        rh_aws = AWSHandler.objects.get(id=rh_aws_id)

    if aws_region != "" or aws_region is not None:
        # this is deprecated, will be removed later
        env_id_cfv = resource.attributes.filter(field__name__startswith='aws_environment').first()
        
        if env_id_cfv is None:
            return aws_region, rh_aws
            
        env = Environment.objects.get(id=env_id_cfv.value)
        aws_region = env.aws_region

        if rh_aws is None:
            rh_aws = env.resource_handler.cast()

    return aws_region, rh_aws
    
    
def describe_aurora_db_cluster(client,rds_cluster_identifier):
    
    try:
        # fetch RDS instance
        rds_resp = client.describe_db_clusters(DBClusterIdentifier=rds_cluster_identifier)['DBClusters'][0]
    except Exception as err:
        raise RuntimeError(err)
        
    return rds_resp

    
def run(job, resource, logger=None, **kwargs):
    # The Environment ID and RDS Instance data dict were stored as attributes on
    # this service by a build action.
    rds_cluster_identifier = resource.name
    
    # Engine mode of resource 
    engine_mode = resource.get_cf_values_as_dict().get('db_engine_mode')
    
    if engine_mode =='serverless':
        return  "WARNING", f"Start Db cluster operation is not applicable for {engine_mode.capitalize()} Engine Mode, this action only support to Provision Engine Mode",""
        
    # get aws region and resource handler object
    aws: AWSHandler
    region, aws, = get_aws_rh_and_region(resource)

    if aws is None or aws == "":
        return "WARNING", f"RDS Aurora Db Cluster {rds_cluster_identifier} not found, it may have already been deleted", ""

    set_progress('Connecting to Amazon RDS Aurora')
    
    # initialize boto3 client
    client = aws.get_boto3_client(region, 'rds')

    job.set_progress('Starting RDS Aurora Db Cluster {0} ...'.format(rds_cluster_identifier))
    
    rds_resp = describe_aurora_db_cluster(client,rds_cluster_identifier)
    
    if rds_resp['Status'] not in ["stopped"]:
        return "WARNING", f"RDS Aurora Db Cluster {rds_cluster_identifier} is not in stopped state, it may have already been started or in-process state.", ""

    try:
        rds_stop_resp = client.start_db_cluster(DBClusterIdentifier=resource.db_cluster_identifier)['DBCluster']
    except Exception as err:
        raise RuntimeError(err)
        
    status = "Status"

    for instances in rds_stop_resp['DBClusterMembers'][::-1]:
        
        # It takes awhile for the DB to be available.
        set_progress('Waiting Db Instance "{}" for being available'.format(instances['DBInstanceIdentifier']))
        waiter = client.get_waiter('db_instance_available')
        waiter.config.max_attempts = 100  # default is 40 seconds.
        waiter.wait(DBInstanceIdentifier=instances['DBInstanceIdentifier'])
        set_progress('Db Instance "{}" is now available'.format(instances['DBInstanceIdentifier']))

    if rds_stop_resp[status] == "starting":
        while True:
            set_progress('Db Cluster "{}" is being Started'.format(rds_cluster_identifier), increment_tasks=1)
            time.sleep(10)
            
            rds_stop_resp = describe_aurora_db_cluster(client,rds_cluster_identifier)
            
            if rds_stop_resp['Status'] == "stopped":
                break
        
            time.sleep(60)
    
    resource.db_status = "available"
    resource.save()

    job.set_progress('RDS Aurora Db Cluster {0} started successfully.'.format(rds_cluster_identifier))

    return 'SUCCESS', f'RDS Aurora Db Cluster {rds_cluster_identifier} started successfully.', ''