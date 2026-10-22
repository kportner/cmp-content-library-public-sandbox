import socket
import time
import paramiko
from django.conf import settings
from common.methods import set_progress
from infrastructure.models import Server, CustomField
from resources.models import Resource

import time




def copy_file_to_or_from_remote_server(server, key_file_path, from_path, To_path, action, max_retries=10, delay=15):
    """
    Safely connects via Paramiko with retry limits and handles TCP socket timeouts.
    Dynamically pulls the username from server credentials or defaults to 'ec2-user'.
    """
    host_name = server.ip
    if not host_name:
        raise ValueError(f"Server '{server.hostname}' has no IP address assigned.")

    # Dynamically resolve username from server credentials, defaulting to ec2-user
    username = 'ec2-user'
    if getattr(server, 'credentials', None) and server.credentials.username:
        username = server.credentials.username

    for attempt in range(1, max_retries + 1):
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            set_progress(f"Connecting to {server.hostname} ({host_name}) as '{username}' via SSH (Attempt {attempt}/{max_retries})...")
            # Set explicit connect timeout to avoid hanging indefinitely
            ssh_client.connect(
                hostname=host_name,
                username=username,
                key_filename=key_file_path,
                timeout=30,
                banner_timeout=30
            )
            
            sftp = ssh_client.open_sftp()
            if action == "upload":
                set_progress(f"Copying file from '{from_path}' to server '{server.hostname}:{To_path}'")
                sftp.put(from_path, To_path)
            elif action == "download":
                set_progress(f"Copying file from server '{server.hostname}:{from_path}' to local '{To_path}'")
                sftp.get(from_path, To_path)
            sftp.close()
            set_progress(f"File transfer successfully completed for server '{server.hostname}'")
            return  # Success, exit function

        except (paramiko.SSHException, TimeoutError, socket.timeout, OSError) as err:
            set_progress(f"SSH Connection error on server '{server.hostname}' ({err}). Retrying in {delay}s...")
            if attempt == max_retries:
                raise RuntimeError(
                    f"Failed to connect to '{server.hostname}' ({host_name}) after {max_retries} attempts. "
                    f"Please verify security groups, routing, and port 22 accessibility."
                ) from err
        finally:
            ssh_client.close()
            time.sleep(delay)


def run(job, *args, **kwargs):
    proserv_path = getattr(settings, "PROSERV_DIR", "/var/opt/cloudbolt/proserv/")
    if not proserv_path.endswith("/"):
        proserv_path += "/"

    resource = kwargs.get('resource')
    if not resource:
        raise ValueError("Resource parameter is required for pre_configuration_setup plugin.")

    key_file_path = f"{proserv_path}{resource.ec2_key_name}.pem"
    server_ut_dict = {}
    unique_token = ""
    server_id_having_ut = -1

    script_content = f"""#!/usr/bin/env bash
my_out="NA"
if [ -f "{proserv_path}customer_settings.py" ]; then
    my_out=$(grep "UNIQUE_TOKEN" {proserv_path}customer_settings.py || true)
fi

if [[ "$my_out" == "" ]]; then
    echo "NA"
else
    echo "$my_out"
fi"""

    replace_autostart = """sudo runuser -l root -c 'sed -i "/autostart=true/c\\autostart=false" /etc/supervisord.d/jobengine.conf'"""
    replace_autorestart = """sudo runuser -l root -c 'sed -i "/autorestart=true/c\\autorestart=false" /etc/supervisord.d/jobengine.conf'"""

    for server_id in resource.server_ids.split(","):
        server = Server.objects.get(id=int(server_id))

        # Explicitly ensure server username & credentials in CloudBolt are set to ec2-user
        server.username = 'ec2-user'
        if getattr(server, 'credentials', None):
            server.credentials.username = 'ec2-user'
            server.credentials.save()
        server.save()

        set_progress(f"Copying key_file on server '{server.hostname}'")
        copy_file_to_or_from_remote_server(server, key_file_path, key_file_path, f"/tmp/{resource.ec2_key_name}.pem", "upload")

        set_progress(f"Installing Putty on server '{server.hostname}'")
        script_output = server.execute_script(script_contents="sudo runuser -l root -c 'yum -y install putty'", timeout=360)

        set_progress(f"Converting .PEM file to .PPK(private key) on server '{server.hostname}'")
        command_to_exec = f"sudo runuser -l root -c 'puttygen /tmp/{resource.ec2_key_name}.pem -o /tmp/{resource.ec2_key_name}.ppk -O private'"
        script_output = server.execute_script(script_contents=command_to_exec, timeout=300)

        set_progress(f"Modifying permissions of '{resource.ec2_key_name}.pem' and 'secret-key-for-apache.bin' file")
        script_output = server.execute_script(script_contents=f"sudo runuser -l root -c 'chmod 600 /tmp/{resource.ec2_key_name}.pem'")
        
        # Idempotent secrets folder & binary file setup before applying permissions
        setup_secrets_cmd = (
            "sudo runuser -l root -c '"
            "mkdir -p /var/opt/cloudbolt/secrets/ && "
            "touch /var/opt/cloudbolt/secrets/secret-key-for-apache.bin && "
            "chmod 777 /var/opt/cloudbolt/secrets/secret-key-for-apache.bin'"
        )
        script_output = server.execute_script(script_contents=setup_secrets_cmd, timeout=120)

        set_progress(f"Setting 'autostart=false' and 'autorestart=false' in file '/etc/supervisord.d/jobengine.conf' on server '{server.hostname}'")
        script_output = server.execute_script(script_contents=replace_autostart, timeout=240)
        script_output = server.execute_script(script_contents=replace_autorestart, timeout=240)
        script_output = server.execute_script(script_contents="sudo runuser -l root -c 'supervisorctl reload'", timeout=240)

        set_progress(f"Checking Unique token on server '{server.hostname}'")
        script_output = server.execute_script(script_contents=script_content)
        set_progress(f"Unique token found on server '{server.hostname}' is '{script_output}'")

        # Parse token safely
        parsed_token = "NA"
        if script_output and "UNIQUE_TOKEN" in script_output:
            try:
                parsed_token = script_output.split("\n")[0].split("=")[-1].replace(" ", "").replace("'", "")
            except IndexError:
                parsed_token = "NA"

        server_ut_dict[int(server_id)] = parsed_token

    if all(value == "NA" for value in server_ut_dict.values()):
        set_progress("Case :- All instances DOESN'T have UNIQUE_TOKEN")
        server_id = list(server_ut_dict.keys())[0]
        server = Server.objects.get(id=int(server_id))
        command_to_exec = "sudo runuser -l root -c 'uuidgen'"
        unique_token = server.execute_script(script_contents=command_to_exec)
        unique_token = unique_token.split("\n")[0].strip()

    elif all(value != "NA" for value in server_ut_dict.values()):
        set_progress("Case :- All instances have UNIQUE_TOKEN")
        unique_token = next(iter(server_ut_dict.values()))
        server_id_having_ut = next(iter(server_ut_dict.keys()))

    else:
        set_progress("Case :- At least one instance has UNIQUE_TOKEN")
        for key, value in server_ut_dict.items():
            if value != "NA":
                unique_token = value
                server_id_having_ut = key

    CustomField.objects.get_or_create(
        name='unique_token',
        defaults={
            "label": 'Unique Token ID',
            "type": 'STR',
            'show_as_attribute': False,
            "description": 'Used by the HA Architecture blueprint'
        }
    )
    resource.unique_token = unique_token
    resource.save()

    from_path = f"{proserv_path}UniqueToken.txt"
    with open(from_path, "w") as f:
        f.write(f"UNIQUE_TOKEN = '{unique_token}'\n")
    to_path = "/tmp/unique_token.txt"

    for server_id in resource.server_ids.split(","):
        server = Server.objects.get(id=int(server_id))
        if server.id == server_id_having_ut:
            continue

        copy_file_to_or_from_remote_server(server, key_file_path, from_path, to_path, "upload")

        if server_ut_dict[int(server_id)] != "NA":
            command_to_exec = f"""sudo runuser -l root -c 'sed -i "/UNIQUE_TOKEN/d" {proserv_path}customer_settings.py'"""
            server.execute_script(script_contents=command_to_exec)

        command_to_exec = f"sudo runuser -l root -c 'cat {to_path} >> {proserv_path}customer_settings.py'"
        server.execute_script(script_contents=command_to_exec)

    # Copy BIN(secret-key-for-apache.bin) file from the first CloudBolt instance to the rest instances.
    from_path = f"{proserv_path}secret-key-for-apache.bin"
    to_path = "/var/opt/cloudbolt/secrets/secret-key-for-apache.bin"
    first_instance = True
    for server_id in resource.server_ids.split(","):
        server = Server.objects.get(id=int(server_id))
        if first_instance:
            set_progress(f"Copying pg_password from server '{server.hostname}'")
            pg_pwd = server.execute_script(script_contents="sudo runuser -l root -c 'sudo grep postgresql_pass /var/opt/cloudbolt/.postgresql_password'")
            pg_pwd = pg_pwd.split("=")[-1].rstrip("\n").strip()
            
            db_backup_cmd = f"sudo runuser -l root -c 'PGPASSWORD={pg_pwd} pg_dump -h localhost -p 5432 -U cb_dba -w --clean -F t -f /tmp/cloudbolt.tar cloudbolt'"
            set_progress(f"Taking database backup from server '{server.hostname}'")
            server.execute_script(script_contents=db_backup_cmd, timeout=360)

            first_instance = False
            copy_file_to_or_from_remote_server(server, key_file_path, to_path, from_path, "download")
        else:
            copy_file_to_or_from_remote_server(server, key_file_path, from_path, to_path, "upload")