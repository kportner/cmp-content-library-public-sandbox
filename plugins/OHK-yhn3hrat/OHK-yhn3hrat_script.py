"""
Delete an aws security group
"""
from common.methods import set_progress
from azure.common.credentials import ServicePrincipalCredentials
from botocore.exceptions import ClientError
from resourcehandlers.aws.models import AWSHandler

def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="ec2"):
    """
    Return boto connection to the EC2 in the specified environment's region.
    """

    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client

def run(job, **kwargs):
    resource = kwargs.pop('resources').first()

    aws_security_group_id = resource.attributes.get(field__name='security_group_id').value
    rh_id = resource.attributes.get(field__name='aws_rh_id').value
    region = resource.attributes.get(field__name='aws_region').value
    rh = AWSHandler.objects.get(id=rh_id)

    set_progress("Connecting to aws ec2...")
    ec2_client = get_boto3_service_client(rh, region)

    set_progress("Deleting the security group...")

    try:
        ec2_client.delete_security_group(GroupId=aws_security_group_id)
        set_progress('Security Group Deleted')
    except ClientError as e:
        return "FAILURE", "Network security group could not be deleted", e

    return "SUCCESS", "The network security group has been succesfully deleted", ""