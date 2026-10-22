from common.methods import set_progress
from resourcehandlers.aws.models import AWSHandler

def get_boto3_service_client(rh, aws_region, service_name="efs"):
    """
    Return boto connection to the EFS in the specified environment's region.
    """

    # get aws wrapper object
    wrapper = rh.get_api_wrapper()

    # get aws client object
    client = wrapper.get_boto3_client(service_name, rh.serviceaccount, rh.servicepasswd, aws_region)

    return client


def run(job, *args, **kwargs):
    resource = kwargs.get('resource')
    
    handler = AWSHandler.objects.get(id=resource.aws_rh_id)
    region = resource.attributes.get(field__name='aws_region').value
    
    FileSystemId = "{{ FileSystemId }}"
    subnet_id = "{{ subnet_id }}"
    
    client = get_boto3_service_client(handler, region)
    res = client.create_mount_target(
        FileSystemId=FileSystemId,
        SubnetId=subnet_id,
    )
    set_progress(res)
    if True:
        return "SUCCESS", "Sample output message", ""
    else:
        return "FAILURE", "Sample output message", "Sample error message, this is shown in red"