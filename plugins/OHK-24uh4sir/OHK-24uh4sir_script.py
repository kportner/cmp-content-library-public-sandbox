from botocore.client import ClientError
from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler
from infrastructure.models import Environment


RESOURCE_IDENTIFIER = 'security_group_name'

def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="ec2"):
    """
    Return boto connection to the EC2 in the specified environment's region.
    """

    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client

def discover_resources(**kwargs):
    discovered_security_groups = []
    for handler in AWSHandler.objects.all():
        set_progress(
            'Connecting to Amazon EC2 for handler: {}'.format(handler))
        for region in handler.current_regions():
            ec2_client = get_boto3_service_client(handler, region)
            try:
                for response in ec2_client.describe_security_groups()['SecurityGroups']:
                    discovered_security_groups.append({
                        "name": response['GroupName'] + " - " + response['GroupId'],
                        "aws_region": region,
                        "aws_rh_id": handler.id,
                        "security_group_name": response['GroupName'] + " - " + response['GroupId'],
                        "security_group_description": response['Description'],
                        "aws_security_group_id": response['GroupId']
                    })
            except ClientError as e:
                set_progress('AWS ClientError: {}'.format(e))
                continue

    return discovered_security_groups