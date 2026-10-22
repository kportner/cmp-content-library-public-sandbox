from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler
import time

def get_boto3_service_client(rh: AWSHandler, aws_region, service_name="fsx"):
    """
    Return boto connection to the FSX in the specified environment's region.
    """

    # get aws client object
    client = rh.get_boto3_client(aws_region, service_name)

    return client


def run(job, *args, **kwargs):
    resource = kwargs.pop('resources').first()
    region = resource.get_cf_values_as_dict()['aws_region']
    rh_id = resource.aws_rh_id
    rh = AWSHandler.objects.get(id=rh_id)
    fsx = get_boto3_service_client(rh, region)
    fsx.delete_file_system(FileSystemId=resource.file_system_id)

    # Wait for the file system to be fully deleted
    def get_lifecycle():
        try:
            res = fsx.describe_file_systems(FileSystemIds=[resource.file_system_id])

            lifecycle = res.get('FileSystems')[0].get('Lifecycle')
        except Exception as e:
            # Once the file system has been deleted,
            # an exception will be raised while trying to describe that file system.
            lifecycle = "DELETED"

        return lifecycle

    lifecycle = get_lifecycle()

    while lifecycle == "DELETING":
        set_progress(f"File System Status: {lifecycle}")
        time.sleep(60)
        lifecycle = get_lifecycle()

    if lifecycle == "DELETED":
        return "SUCCESS", f"{resource.name} Deleted Successfully", ""
    else:
        return "FAILURE", "Failed to delete file system", f"File System Status is {lifecycle}"