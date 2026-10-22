"""
Delete a AWS Sagemaker notebook instance

** See README for more details for blueprint construction **

"""

from common.methods import set_progress
from infrastructure.models import Environment
import time
from botocore.exceptions import ClientError
from resourcehandlers.aws.models import AWSHandler


###
# Get boto3 client
###
def get_boto_client(env_id=None, boto_service=''):
    if env_id == None:
        return None
    env = Environment.objects.get(id=env_id)
    rh: AWSHandler = env.resource_handler.cast()
    client = rh.get_boto3_client(env.aws_region, boto_service)
    return client, env

###
# Main run() method
###
def run(job, **kwargs):

    # 1. Get attributes stored on meta data
    notebook_instance_status = 'Stopping'
    resource = kwargs.pop('resources').first()
    sagemaker_notebook_instance_name = resource.attributes.get(field__name='sagemaker_notebook_instance_name').value
    env_id = resource.attributes.get(field__name='aws_env_id').value

    # 2. Connect to AWS
    set_progress("Connecting To AWS...")
    client, env = get_boto_client(env_id, 'sagemaker')

    # 3. Delete Notebook instance
    try:
        # stop
        set_progress("Stopping Sagemaker notebook instance[" + sagemaker_notebook_instance_name + "]...")
        response = client.stop_notebook_instance(
            NotebookInstanceName=sagemaker_notebook_instance_name
        )

        # drop
        wait = 0
        while notebook_instance_status != 'Stopped':
            wait += 30
            set_progress("Waiting for notebook instance to shut down ["+str(wait)+"s]...")
            time.sleep(wait)
            response = client.describe_notebook_instance(
                NotebookInstanceName=sagemaker_notebook_instance_name
            )
            notebook_instance_status = response['NotebookInstanceStatus']

        # roll
        set_progress("Deleting Sagemaker notebook instance[" + sagemaker_notebook_instance_name + "]...")
        if notebook_instance_status == 'Stopped':
            response = client.delete_notebook_instance(
                NotebookInstanceName=sagemaker_notebook_instance_name
            )
    except ClientError as ce:
        set_progress("AWS Clouderror: {}".format(ce))
        return "FAILURE", "Sagemaker notebook instance could not be deleted", str(ce)
    except Exception as err:
        set_progress("Exception: {}".format(err))
        return "FAILURE", "Sagemaker notebook instance could not be deleted", str(err)

    # 4. Return results
    return "SUCCESS", "The Sagemaker notebook instance has been successfully deleted", ""