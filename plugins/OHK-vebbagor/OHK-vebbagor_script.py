"""
This CloudBolt plugin provisions an AWS RDS Aurora Serverless v2 PostgreSQL DB cluster
using Terraform, generates database connection settings and stores output metadata.
"""
import ast
import base64
import os
import random
import re
import subprocess
import zlib

from cbhooks.exceptions import TerraformActionException
from common.methods import set_progress
from django.conf import settings
from infrastructure.models import CustomField, Environment
from resourcehandlers.aws.models import AWSHandler
from resources.models import Resource
from servicecatalog.models import BlueprintServiceItem, ServiceBlueprint


def get_or_create_custom_fields():
    CustomField.objects.get_or_create(
        name='ha_db_endpoint_address',
        defaults={
            "label": 'Endpoint Address',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_cluster_port',
        defaults={
            "label": 'DB Cluster Port',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_availability_zone',
        defaults={
            "label": 'Availability Zone',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_engine',
        defaults={
            "label": 'Engine',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_status',
        defaults={
            "label": 'Status',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='ha_dbsubnet_group',
        defaults={
            "label": 'Subnet Group',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint'
        }
    )

    CustomField.objects.get_or_create(
        name="ha_db_instances",
        defaults={
            "label": 'DB Instances',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name="ha_db_cluster_identifier",
        defaults={
            "label": 'DB Cluster Identifier',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name="ha_cluster_reader_endpoint",
        defaults={
            "label": 'DB Cluster Reader Endpoint',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name="ha_db_aws_region",
        defaults={
            "label": 'AWS Region',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            "show_on_servers": True,
            'show_as_attribute': True,
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_engine_mode',
        defaults={
            "label": 'DB Engine Mode',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_cluster_arn',
        defaults={
            "label": 'DB Cluster ARN',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_master_username',
        defaults={
            "label": 'DB Master Username',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_cluster_endpoint',
        defaults={
            "label": 'DB Cluster Endpoint',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_cluster_ReaderEndpoint',
        defaults={
            "label": 'DB Cluster Reader Endpoint',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_engine_version',
        defaults={
            "label": 'DB Engine Version',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_cluster_min_capacity',
        defaults={
            "label": 'Serverless Min capacity',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_cluster_max_capacity',
        defaults={
            "label": 'Serverless Max capacity',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='ha_is_multiaz',
        defaults={
            "label": 'Multi-AZ',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': True,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='main_tf_dir',
        defaults={
            "label": 'Main TF directory',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': False,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='tf_state_dir',
        defaults={
            "label": 'TF State directory',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': False,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='tf_plan_dir',
        defaults={
            "label": 'TF plans directory',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': False,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='tf_backup_dir',
        defaults={
            "label": 'TF Backup directory',
            "type": 'STR',
            "description": 'Used by the AWS Databases blueprint',
            'show_as_attribute': False,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='ha_dbcluster_identifier',
        defaults={
            "label": 'DB Cluster identifier',
            "type": 'STR',
            "description": 'Used by the HA Architecture blueprint',
            'show_as_attribute': False,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='dbstring',
        defaults={
            "label": 'Database Connection String',
            "type": 'STR',
            "description": 'Used by the HA Architecture blueprint',
            'show_as_attribute': False,
            "show_on_servers": True
        }
    )

    CustomField.objects.get_or_create(
        name='ha_db_subnet_group',
        defaults={
            "label": 'Subnet Group',
            "type": 'STR',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture blueprint'
        }
    )


def get_boto3_client(service_name='ec2', **kwargs):
    rh = kwargs.get('resource_handler')
    region = kwargs.get('region', None)
    service_name = kwargs.get('service', service_name)
    wrapper = rh.get_api_wrapper()
    return wrapper.get_boto3_client(service_name, rh.serviceaccount, rh.servicepasswd, region)


def get_parent_bp(**kwargs):
    current_bp = kwargs.get('current_bp')
    bp_service_item = BlueprintServiceItem.objects.filter(
        sub_blueprint=current_bp, blueprint__status="ACTIVE"
    ).prefetch_related("blueprint").first()

    if bp_service_item:
        return ServiceBlueprint.objects.get(id=bp_service_item.blueprint_id)
    return ServiceBlueprint.objects.filter(name__icontains="CloudBolt HA Deployment on AWS").first()


def boto_cluster_to_dict(boto_cluster, aws_region, rh_id):
    """
    Create a pared-down representation of an RDS instance from the full boto dictionary.
    """
    return {
        'ha_db_cluster_identifier': boto_cluster.get("DBClusterIdentifier", ''),
        'ha_database_name': boto_cluster.get('DatabaseName', ''),
        'ha_db_master_username': boto_cluster.get('MasterUsername', ''),
        'ha_db_aws_region': aws_region,
        'ha_aws_rh_id': rh_id,
        'ha_db_cluster_endpoint': boto_cluster.get('Endpoint', ''),
        'ha_db_cluster_ReaderEndpoint': boto_cluster.get('ReaderEndpoint', ''),
        'ha_db_status': boto_cluster.get('Status', ''),
        'ha_db_availability_zone': str(boto_cluster.get('AvailabilityZones', '')),
        'ha_db_cluster_arn': boto_cluster.get('DBClusterArn', ''),
        'ha_db_engine': boto_cluster.get('Engine', ''),
        'ha_db_engine_version': boto_cluster.get('EngineVersion', ''),
        'ha_db_engine_mode': boto_cluster.get('EngineMode', ''),
        'ha_dbsubnet_group': boto_cluster.get('DBSubnetGroup', ''),
        'ha_db_cluster_port': str(boto_cluster.get('Port', '')),
        'ha_is_MultiAZ': str(boto_cluster.get('MultiAZ', ''))
    }


def check_or_make_required_dir_and_terraform_files(main_path):
    variable_file_string_compressed = b'x\x9c\x95\x90Aj\x031\x0cE\xf7s\n1\xf7\xe8"\xeb.\x03\xed\xd2\xc8\x9e\x9f\xa9\xc9\x8cm$y\x9a\xa1\xe4\xee5\t\x94\x12\x088Z\xbf\xa7/\xfd\x8d%\xb2_@\xa3`\x8e9\x8d\xf43\x10\xd9^@m\xdeHMb\x9a\x87\xeb\xb0\xfd\x81\x1c\x02T\xdd\x19\xfb\x1d\x9e\xa0Ab\xb1f7a\xfc\xe0\xa5\x82\xf2\x89\xec\x0bt\xb8\xb1\xd4X:e\xa1\xc3\xe7q\xfc\xb7\xfei\x84"\x08\xac/\xe2xc\xe9\xfd\xc5\x88\xc9;\xad>\xc1f\xc9\xb5\xb8\xc4+:~\x0fKU\x83t\xd2HsLp\x1bD\xfb\xaa\x9d\xd8\xd8\xb3\xa2\xf7\x9c\xaa\xdd\xb7\x14V\xd5\xef,S\x07\xdb*\xad\x12mw\xf7nb\x8f\xb3\xf2\xc5\x05.\x1c\x9a\xf7\x88\xa7\xbaz\xc8p\xfd\x05{\x16\xc8\xd8'
    main_tf_file_compressed = b'x\x9c\x95RAn\xdc0\x0c\xbc\xef+\x04\xdf\xd7\r\xda\xe6\x98~\xa2\xc7"\x10h\x89\xeb\x08\xb5%\x87\x94\x9c\xa6\xc5\xf6\xed\xa5,y\xed\xa4]$=,\xb0\x9e\x19r(r"\x12\xc1)\xd0\xa8~\x1d\x94"|L\x8e\xd0\xea\x89\xc2\xec,\x12/\xb0R\xf0\xc4\xea\xae\xfeW\x8aC"\x83J\x90\xe6\x01\xf8\xc1\x99@\xd3\x07\x914\x95\x9f\xa5\xd0\x05\x9f\xf9\xdf_\xd4\xe7\xf6\xa6\x10\xe7C\xfe\x9d\x0f\x87\xb5\xbbjrQu\xees\x85\x94\xcc@m\xf9\x12\x18\x8cAf\xfd\x1d\x9f+\xb3\x01\xc22\x1a\xc2\xb8c7 \xdb\x10\xd6A\xb3\x8d&\xcb\xda\x0c\x89#R\x93\xe7>\x8ei\x88\x0e~\x1emw\xbc\xe0y\x94\xfa\xa1eB\x1f\xdd\xc9\xc9\x9c\xa5{%<\x8c(2\xdbiN\x9d\x17\xbb\x9eB\x9at\x86\xcb\xf3\x8b\xfa\xc2o\xb4T\xa1\xef\x9d\xaf:\xb5\xca\x1bH\x14\x08\x8eS`Q#?\x0e\xcdE\xaa\xc7`q\']v\x97\xb7\x8bv\'Z7\xbe\xd9\xbf$\xf2\xbc\x10\xa1\x03\xc6\xbf\x07\xdd\x13"\x1cay~\xe2\xf2\xd4M\xb8"\x9bf\x02\xe6\xa7@v\xd3dd\x81D4OF\xcbE\x12\xb9\xf8\\\x97\xe4l\xce\xd1\xb7\xac\xfc\xfa\x9a\xb9\x97\x92\xe5\xa8$C\x0fr\xe5\xf9\xa3f\x03\x83\xf3\xbd6\xc1\x9f\\\x9f\x08b~e\xc9\xe1\x08?\xb4\x81\t\x8c4\xa9\xee{\xa8h\x9c\xdfkn\xda\xdb5\x83W\xc3\xa1\x9d\xe7\x08\xde\xe0\x1b)\t\xc9\xc7\x17w\x94\xfe\x9f\xae\xc5\xe7\x95G\xfb\xcf\xc6\xad\xcb[[\xedE+\xbb\\\xcfn\xbbv[Ls-H\xef\xb3)\xa5\xd7\xc2\xf3?=.\xf1:\xff\x010\x1en\x7f'

    tfplans_path = f"{main_path}/tfplans"
    tfout_path = f"{main_path}/tfout"
    tfbackup_path = f"{main_path}/tfbackup"

    if not os.path.isdir(main_path):
        os.mkdir(main_path)

    if not os.path.exists(f"{main_path}/variables.tf"):
        with open(f"{main_path}/variables.tf", "w") as f:
            f.write(zlib.decompress(variable_file_string_compressed).decode())

    if not os.path.exists(f"{main_path}/main.tf"):
        with open(f"{main_path}/main.tf", "w") as f:
            f.write(zlib.decompress(main_tf_file_compressed).decode())

    if not os.path.exists(tfplans_path):
        os.mkdir(tfplans_path)

    if not os.path.exists(tfout_path):
        os.mkdir(tfout_path)

    if not os.path.exists(tfbackup_path):
        os.mkdir(tfbackup_path)

    return tfplans_path, tfout_path, tfbackup_path


def run_tf_command(tf_bin_path, action, cwd, tf_env_vars=None, tfplan=None, tfstate=None, tfbackup=None, flags=['-no-color', '-input=false']):
    if action == "init":
        final_cmd = [tf_bin_path, action] + flags
    elif action == "plan":
        final_cmd = [tf_bin_path, action, f"-out={tfplan}"] + flags
    elif action == "apply":
        final_cmd = [tf_bin_path, action] + flags
        final_cmd.append("-auto-approve")
        final_cmd.append(f"-state-out={tfstate}")
        final_cmd.append(f"-backup={tfbackup}")
        final_cmd.append(f"{tfplan}")

    return subprocess.Popen(
        final_cmd, cwd=cwd, env=tf_env_vars,
        stderr=subprocess.PIPE, stdout=subprocess.PIPE,
        universal_newlines=True, preexec_fn=None
    )


def show_output_or_error(command_output, action):
    for line in command_output.stdout:
        if line.rstrip() != "":
            set_progress(line.rstrip())

    for line in command_output.stderr:
        if line.rstrip() != "":
            set_progress(line.rstrip())

    command_output.wait()
    if command_output.returncode not in [0, 2]:
        raise TerraformActionException(action)


def set_env_tf_variables(parent_resource):
    tf_env_vars = {}
    region = parent_resource.aws_region_ha
    vpc_subnet_sg_dict = ast.literal_eval(parent_resource.vpc_subnet_structure[-1])
    security_group_id = vpc_subnet_sg_dict[region]['VPC'][-1]
    rh = AWSHandler.objects.get(id=parent_resource.aws_rh_id)
    
    tf_env_vars['TF_VAR_region'] = region
    tf_env_vars['TF_VAR_access_key'] = rh.serviceaccount
    tf_env_vars['TF_VAR_secret_key'] = rh.servicepasswd
    tf_env_vars['TF_VAR_Security_group_id'] = str(security_group_id)
    tf_env_vars.update(os.environ)
    tf_env_vars.update({"TF_IN_AUTOMATION": "1"})
    return tf_env_vars


def generate_options_for_engine_version(control_value=None, **kwargs):
    """
    Dynamically fetches available Aurora PostgreSQL engine versions from AWS RDS
    supporting versions across 13.x, 14.x, 15.x, 16.x, etc.
    """
    current_bp = kwargs.get('blueprint')
    rh_id = None
    aws_ha_region = None
    options = []
    parent_bp = get_parent_bp(current_bp=current_bp)

    if control_value:
        cf_dict = parent_bp.get_cf_values_as_dict() if parent_bp else {}
        if 'global_ha_architecture_rh_id' in cf_dict:
            rh_id = cf_dict['global_ha_architecture_rh_id']
        if 'global_ha_architecture_locations' in cf_dict:
            locations = cf_dict['global_ha_architecture_locations']
            aws_ha_region = locations.split(",")[0].split(")")[0].split("(")[-1]

        if rh_id and aws_ha_region:
            rh = AWSHandler.objects.get(id=rh_id)
            client = get_boto3_client(service='rds', resource_handler=rh, region=aws_ha_region)
            
            filters = [
                {'Name': 'status', 'Values': ['available']},
                {'Name': 'engine-mode', 'Values': ['provisioned', 'serverless']}
            ]

            response = client.describe_db_engine_versions(
                Engine="aurora-postgresql",
                IncludeAll=False,
                Filters=filters
            )

            for engine in response.get('DBEngineVersions', []):
                ver = engine['EngineVersion']
                desc = engine.get('DBEngineVersionDescription', f'Aurora PostgreSQL {ver}')
                option_label = desc if ver in desc else f"{desc} : {ver}"
                options.append((ver, option_label))

    return sorted(options, key=lambda x: [int(c) if c.isdigit() else c for c in re.split(r'(\d+)', x[0])], reverse=True)


def run(job, *args, **kwargs):
    resource = kwargs.get('resource')
    get_or_create_custom_fields()
    dir_name = resource.blueprint.name.replace(" ", "_")
    proserv_path = getattr(settings, "PROSERV_DIR", None)

    max_capacity = "{{max_capacity}}"
    engine_version = "{{engine_version}}"
    database_name = "{{database_name}}"
    username = "{{username}}"
    password = "{{pasword}}"

    if not os.access(proserv_path, os.X_OK | os.W_OK):
        os.chmod(proserv_path, 0o777)

    cwd = f"{proserv_path}{dir_name}"
    tfplans_path, tfout_path, tfbackup_path = check_or_make_required_dir_and_terraform_files(cwd)

    if resource.parent_resource_id:
        parent_resource = Resource.objects.get(id=resource.parent_resource_id)
        rh = AWSHandler.objects.get(id=parent_resource.aws_rh_id)
        aws_ha_region = parent_resource.aws_region_ha
        base_name = parent_resource.base_name
        vpc_subnet_sg_dict = ast.literal_eval(parent_resource.vpc_subnet_structure[-1])
        rds_client = get_boto3_client(service='rds', resource_handler=rh, region=aws_ha_region)
        subnet_id_list = [subnet[0] for subnet in vpc_subnet_sg_dict[aws_ha_region]['Subnet']]
        
        db_subnet_group_name = f"dbsubnetgroup_{base_name.lower()}"
        response = rds_client.describe_db_subnet_groups()
        dbsubnetgrps = [dbs['DBSubnetGroupName'] for dbs in response.get('DBSubnetGroups', [])]
        if db_subnet_group_name in dbsubnetgrps:
            db_subnet_group_name += f"-{random.randrange(100, 999, 3)}"

        dbclustername = f"dbcluster-{base_name.lower()}"
        response = rds_client.describe_db_clusters()
        dbcluster_names = [dbcluster['DBClusterIdentifier'] for dbcluster in response.get('DBClusters', [])]
        if dbclustername in dbcluster_names:
            dbclustername += f"-{random.randrange(100, 999, 3)}"

        set_progress('Creating dbsubnet group...')
        rds_client.create_db_subnet_group(
            DBSubnetGroupName=db_subnet_group_name,
            DBSubnetGroupDescription='Created subnet group for RDS Aurora DB Cluster',
            SubnetIds=subnet_id_list
        )
        set_progress(f'Created dbsubnet group "{db_subnet_group_name}" successfully...')

    tf_bin_path = settings.TERRAFORM_BINARY
    unique_number = resource.id
    action = "init"
    output = run_tf_command(tf_bin_path, action, cwd)
    show_output_or_error(output, action)

    tf_env_vars = set_env_tf_variables(parent_resource)
    tf_env_vars['TF_VAR_engine_version'] = engine_version
    tf_env_vars['TF_VAR_database_name'] = database_name
    tf_env_vars['TF_VAR_username'] = username
    tf_env_vars['TF_VAR_passsword'] = password
    tf_env_vars['TF_VAR_max_capacity'] = max_capacity
    tf_env_vars['TF_VAR_clustername'] = dbclustername
    tf_env_vars['TF_VAR_db_subnetgroup_name'] = db_subnet_group_name

    action = "plan"
    tfplan = f"{tfplans_path}/{unique_number}.tfplan"
    output = run_tf_command(tf_bin_path, action, cwd, tf_env_vars=tf_env_vars, tfplan=tfplan)
    show_output_or_error(output, action)

    action = "apply"
    tfstate = f"{tfout_path}/{unique_number}.tfstate"
    tfbackup = f"{tfbackup_path}/{unique_number}.tfbackup"
    output = run_tf_command(
        tf_bin_path, action, cwd,
        tf_env_vars=tf_env_vars, tfplan=tfplan,
        tfstate=tfstate, tfbackup=tfbackup
    )
    show_output_or_error(output, action)

    client = get_boto3_client(service='rds', resource_handler=rh, region=aws_ha_region)
    dbclusters = client.describe_db_clusters(DBClusterIdentifier=dbclustername)
    dbcluster = dbclusters['DBClusters'][0]
    rds_cluster = boto_cluster_to_dict(dbcluster, aws_ha_region, rh.id)
    db_identifier = dbcluster['DBClusterIdentifier']

    for key, value in rds_cluster.items():
        setattr(resource, key, value)

    resource.main_tf_dir = cwd
    resource.tf_state_dir = tfout_path
    resource.tf_plan_dir = tfplans_path
    resource.tf_backup_dir = tfbackup_path
    resource.save()

    db_string_list = [
        "DATABASES = {\n",
        "'default': {\n",
        "'ENGINE': 'django.db.backends.postgresql_psycopg2',\n",
        f"'NAME':'{resource.ha_database_name}',\n",
        f"'USER': '{resource.ha_db_master_username}',\n",
        f"'PASSWORD': '{password}',\n",
        f"'HOST': '{resource.ha_db_cluster_endpoint}',\n",
        "'PORT': '5432'\n",
        "}\n",
        "}\n"
    ]
    db_string_b64_string = base64.b64encode("".join(db_string_list).encode("ascii")).decode("ascii")
    with open(f"{proserv_path}db_section.txt", "w") as f:
        f.write(db_string_b64_string)

    if resource.parent_resource_id:
        parent_resource.ha_db_subnet_group = db_subnet_group_name
        parent_resource.dbstring = "+".join(db_string_list)
        parent_resource.ha_dbcluster_identifier = db_identifier
        parent_resource.save()

    return "SUCCESS", "Aurora Serverless v2 Multi-AZ DB created successfully...", ""