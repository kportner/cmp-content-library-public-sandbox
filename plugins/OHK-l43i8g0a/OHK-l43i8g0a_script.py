from common.methods import set_progress
from infrastructure.models import CustomField, Environment
from accounts.models import Group
from utilities.logger import ThreadLogger
from resourcehandlers.aws.models import AWSHandler

logger = ThreadLogger(__name__)

def create_custom_fields_as_needed():
    CustomField.objects.get_or_create(
        name='aws_rh_id', defaults={
            'label': 'AWS RH ID', 'type': 'STR',
            'description': 'Used by the AWS blueprints'
        }
    )
    CustomField.objects.get_or_create(
        name='table_name', defaults={
            'label': 'DynamoDB table name', 'type': 'STR',
            'description': 'Used by the AWS blueprints'
        }
    )
    CustomField.objects.get_or_create(
        name='aws_region', defaults={
            'label': 'Region', 'type': 'STR',
            'description': 'Used by the AWS blueprints'
        }
    )


def get_boto3_service_client(env, service_name="dynamodb"):
    """
    Return boto connection to the Dynamodb in the specified environment's region.
    """
    # get aws resource handler object
    rh: AWSHandler = env.resource_handler.cast()

    # get aws client object
    client = rh.get_boto3_client(env.aws_region, service_name)
    
    return client
    
def sort_dropdown_options(data, placeholder=None, is_reverse=False):
    """
    Sort dropdown options 
    """
    # remove duplicate option from list
    data = list(set(data))

    # sort options
    sorted_options = sorted(data, key=lambda tup: tup[1].lower(), reverse=is_reverse)
    
    if placeholder is not None:
        sorted_options.insert(0, placeholder)
    
    return {'options': sorted_options, 'override': True}
    
    
def generate_options_for_env_id(**kwargs):
    """
    Generate AWS region options
    """
    group_name = kwargs["group"]
    
    # fetch all group environment
    envs = group_name.get_available_environments()
    
    options= [(env.id, env.name) for env in envs if env.resource_handler.resource_technology.name == "Amazon Web Services"]
    
    return sort_dropdown_options(options, ("", "-----Select Environment-----"))


def run(resource, **kwargs):
    set_progress('Creating AWS Dynamodb table...')
    logger.info('Creating AWS Dynamodb table...')
    
    # create custom fields if needed
    create_custom_fields_as_needed()
     
    env = Environment.objects.get(id='{{ env_id }}')
    table_name = "{{ table_name }}"
    primary_key = "{{ primary_key }}"

    # get boto client object
    dynamodb = get_boto3_service_client(env)
    
    try:
        dynamodb.create_table(
                    TableName=table_name,
                    KeySchema=[
                        {
                            'AttributeName': primary_key,
                            'KeyType': 'HASH'
                        }
                    ],
                    AttributeDefinitions=[
                        {
                            'AttributeName': primary_key,
                            'AttributeType': 'S'
                        }],
                    ProvisionedThroughput={
                        'ReadCapacityUnits': 5,
                        'WriteCapacityUnits': 5
                    }
                )
    except Exception as err:
        return "FAILURE", f"{err}", ""
    
    set_progress(f"Waiting for {table_name} to be available")
    
    # Wait until the table exists.
    dynamodb.get_waiter('table_exists').wait(TableName=table_name)

 
    resource.name = table_name
    resource.aws_rh_id = env.resource_handler.cast().id
    resource.aws_region = env.aws_region
    resource.table_name = table_name
    resource.save()
    
    set_progress(f'Dynamodb table {table_name} created successfully.')
    
    return 'SUCCESS', f'Dynamodb table {table_name} created successfully.', ''