"""
Teardown service item action for AWS Elastic File System blueprint.
"""
from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler


def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="efs"):
    """
    Return boto connection to the EFS in the specified environment's region.
    """

    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client


def run(job, logger=None, **kwargs):
    resource = kwargs.pop('resources').first()

    file_system_id = resource.attributes.get(field__name='efs_file_system_id').value
    rh_id = resource.attributes.get(field__name='aws_rh_id').value
    region = resource.attributes.get(field__name='aws_region').value
    rh = AWSHandler.objects.get(id=rh_id)

    set_progress('Connecting to Amazon EFs...')
    client = get_boto3_service_client(rh, region)

    set_progress('Deleting EBS "{}" and contents'.format(file_system_id))
    response = client.delete_file_system(FileSystemId=file_system_id)

    set_progress('response: %s' % response)

    return "", "", ""