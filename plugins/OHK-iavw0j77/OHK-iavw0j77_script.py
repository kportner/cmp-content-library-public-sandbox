from infrastructure.models import Environment
from resourcehandlers.aws.models import AWSHandler

def _boto3_ecs_client(env_obj):
    """
    Return boto connection to the ecs in the specified environment's region.
    """
    rh: AWSHandler = env_obj.resource_handler.cast()

    client = rh.get_boto3_client(env_obj.aws_region, 'ecs')
    return client


def generate_options_for_task_definition(resource, **kwargs):
    if resource is None:
        return []
        
    env_obj = Environment.objects.get(id=resource.env_id)
    
    client = _boto3_ecs_client(env_obj)
    
    result = client.list_task_definitions(status='ACTIVE')

    task_definitions = result.get('taskDefinitionArns')
    
    return [task_definition.split('/')[-1] for task_definition in task_definitions]


def run(resource, *args, **kwargs):
    
    taskDefinition = "{{ task_definition }}"
    
    env_obj = Environment.objects.get(id=resource.env_id)

    client = _boto3_ecs_client(env_obj)

    try:
        client.deregister_task_definition(
            taskDefinition=taskDefinition,
        )
    except Exception as error:
        return "FAILURE", "", f"{error}"

    return "SUCCESS", "Task Definition deregister successfully", ""