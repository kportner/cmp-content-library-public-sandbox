from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler
from infrastructure.models import Environment
from botocore.client import ClientError 


RESOURCE_IDENTIFIER = 'efs_file_system_id'

def get_boto3_service_client(rh, aws_region, service_name="efs"):
    """
    Return boto connection to the EFS in the specified environment's region.
    """
    # get aws wrapper object
    wrapper = rh.get_api_wrapper()

    # get aws client object
    client = wrapper.get_boto3_client(service_name, rh.serviceaccount, rh.servicepasswd, aws_region)

    return client

def discover_resources(**kwargs):
    discovered_efs = []
    for handler in AWSHandler.objects.all():
        set_progress('Connecting to Amazon EC2 for handler: {}'.format(handler))
        for region in handler.current_regions():
            set_progress('Connecting to Amazon EC2 for region: {}'.format(region))
            client = get_boto3_service_client(handler, region)
            try:
                for efs in client.describe_file_systems()['FileSystems']:
                    discovered_efs.append({
                            'name': efs['FileSystemId'],
                            'efs_file_system_id': efs['FileSystemId'],
                            "aws_rh_id": handler.id,
                            "aws_region": region,
                            "state": efs['LifeCycleState'],
                        })

            except ClientError as e:
                set_progress('AWS ClientError: {}'.format(e))
                continue

    return discovered_efs