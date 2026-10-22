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
    

def run(job, resource, logger=None, **kwargs):
    # The Environment ID and RDS  Aurora Db Cluster data dict were stored as attributes on
    # this service by a build action.
    rds_cluster_identifier = resource.name
    
    # Engine mode of resource db cluster 
    engine_mode = resource.get_cf_values_as_dict().get('db_engine_mode')
    
    if engine_mode =='serverless':
        return  "WARNING", f"Stop Db cluster operation is not applicable for {engine_mode.capitalize()} Engine Mode, this action only support to Provision Engine Mode",""

    # get aws region and resource handler object
    region, aws = get_aws_rh_and_region(resource)

    if aws is None or aws == "":
        return "WARNING", f"RDS Aurora Db Cluster {rds_cluster_identifier} not found, it may have already been deleted", ""

    set_progress('Connecting to Amazon RDS Aurora')
    
    # initialize boto3 client
    client = aws.get_boto3_client(region, 'rds')

    job.set_progress('Stopping RDS Aurora Db Cluster {0}...'.format(rds_cluster_identifier))
    
    try:
        # fetch RDS db cluster
        rds_resp = client.describe_db_clusters(DBClusterIdentifier=rds_cluster_identifier)['DBClusters'][0]
    except Exception as err:
        raise RuntimeError(err)
    
    if rds_resp['Status'] != "available":
        return "WARNING", f"RDS Aurora Db Cluster {rds_cluster_identifier} is not in available state, it may have already been stopped or in-process state.", ""
    
    try:
        rds_stop_resp = client.stop_db_cluster(DBClusterIdentifier=rds_cluster_identifier)['DBCluster']
    except Exception as err:
        raise RuntimeError(err)
        
    status = "Status"
    
    if rds_stop_resp[status] != "stopped":
        while True:
            set_progress('Db Cluster "{}" is being Stopped'.format(rds_cluster_identifier), increment_tasks=1)
            time.sleep(10)
            try:
                # fetch Aurora database cluster
                rds_stop_resp = client.describe_db_clusters(DBClusterIdentifier=rds_cluster_identifier)['DBClusters'][0]
            except Exception as err:
                break
            
            if rds_stop_resp['Status'] == "stopped":
                break
        
            time.sleep(60)
    
    resource.db_status = "stopped"
    resource.save()

    job.set_progress('RDS Aurora Db Cluster {0} stopped successfully.'.format(rds_cluster_identifier))

    return 'SUCCESS', f'RDS Aurora Db Cluster {rds_cluster_identifier} stopped successfully.', ''