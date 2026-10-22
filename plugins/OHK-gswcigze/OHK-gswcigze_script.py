"""
Teardown service item action for AWS EBS Volume blueprint.
"""
from common.methods import set_progress
from botocore.client import ClientError
from resourcehandlers.aws.models import AWSHandler

def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="ec2"):
    """
    Return boto connection to the EC2 in the specified environment's region.
    """

    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client

def run(job, logger=None, **kwargs):
    resource = kwargs.pop('resources').first()
    if resource.resource_type.name == "storage":
        volume_id = resource.attributes.get(field__name='ebs_volume_id').value
        rh_id = resource.attributes.get(field__name='aws_rh_id').value
        region = resource.attributes.get(field__name='aws_region').value
        rh = AWSHandler.objects.get(id=rh_id)
    
        set_progress('Connecting to Amazon S3')
        
        ec2 = get_boto3_service_client(rh, region)
        
        set_progress('Deleting EBS volume...')
    
        set_progress('Deleting EBS Volume "{}" and contents'.format(volume_id))
        try:
            response = ec2.delete_volume(VolumeId=volume_id)
        except ClientError as e:
            return "FAILURE", "Failed to delete volume", f"{e}"
        return "", "", ""
    else:
        snapshot_id = resource.name
        parent_resource = resource.parent_resource
        rh_id = parent_resource.attributes.get(field__name='aws_rh_id').value
        region = parent_resource.attributes.get(field__name='aws_region').value
        rh = AWSHandler.objects.get(id=rh_id)
    
        set_progress('Connecting to Amazon S3')

        ec2 = get_boto3_service_client(rh, region)
        set_progress('Deleting EBS volume Snapshot...')
    
        set_progress('Deleting EBS Volume Snapshot "{}" and contents'.format(snapshot_id))
        try:
            response = ec2.delete_snapshot(SnapshotId=snapshot_id)
        except ClientError as e:
            return "FAILURE", "Failed to delete snapshot", f"{e}"
        return "", "", ""