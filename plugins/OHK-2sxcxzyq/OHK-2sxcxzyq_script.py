import socket
import time
import paramiko
from django.conf import settings
from common.methods import set_progress
from infrastructure.models import Server


def copy_file_to_or_from_remote_server(server, key_file_path, from_path, To_path, action, max_retries=10, delay=10):
    """
    Safely connects via Paramiko with retry limits using ec2-user.
    """
    host_name = server.ip
    if not host_name:
        raise ValueError(f"Server '{server.hostname}' has no IP address assigned.")

    username = 'ec2-user'
    if getattr(server, 'credentials', None) and server.credentials.username:
        username = server.credentials.username

    for attempt in range(1, max_retries + 1):
        ssh_client = paramiko.SSHClient()
        ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            set_progress(f"Connecting to {server.hostname} ({host_name}) as '{username}' via SSH (Attempt {attempt}/{max_retries})...")
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
            return

        except (paramiko.SSHException, TimeoutError, socket.timeout, OSError) as err:
            set_progress(f"SSH Connection error on server '{server.hostname}' ({err}). Retrying in {delay}s...")
            if attempt == max_retries:
                raise RuntimeError(
                    f"Failed to connect to '{server.hostname}' ({host_name}) after {max_retries} attempts."
                ) from err
        finally:
            ssh_client.close()
            time.sleep(delay)


def run(job, *args, **kwargs):
    resource = kwargs.get('resource')
    if not resource:
        raise ValueError("Resource parameter is required for configure_shared_database plugin.")

    proserv_path = getattr(settings, "PROSERV_DIR", "/var/opt/cloudbolt/proserv/")
    if not proserv_path.endswith("/"):
        proserv_path += "/"

    key_file_path = f"{proserv_path}{resource.ec2_key_name}.pem"
    first_instance = True

    for server_id in resource.server_ids.split(","):
        server = Server.objects.get(id=int(server_id))

        # Explicitly ensure server username in CloudBolt DB is set to ec2-user
        server.username = 'ec2-user'
        if getattr(server, 'credentials', None):
            server.credentials.username = 'ec2-user'
            server.credentials.save()
        server.save()

        if first_instance:
            set_progress(f"Disabling local postgresql service on server '{server.hostname}'")
            server.execute_script(
                script_contents="sudo runuser -l root -c 'systemctl stop postgresql-15 postgresql-14 postgresql || true'",
                timeout=120
            )
            server.execute_script(
                script_contents="sudo runuser -l root -c 'systemctl disable postgresql-15 postgresql-14 postgresql || true'",
                timeout=120
            )

            set_progress(f"Copying database setting file on server '{server.hostname}'")
            copy_file_to_or_from_remote_server(server, key_file_path, f"{proserv_path}db_section.txt", "/tmp/db_section.txt", "upload")

            set_progress(f"Modifying customer_settings.py file on server '{server.hostname}'")
            update_db_settings_cmd = (
                "sudo runuser -l root -c '"
                "cat /tmp/db_section.txt | base64 --decode >> /var/opt/cloudbolt/proserv/customer_settings.py'"
            )
            server.execute_script(script_contents=update_db_settings_cmd, timeout=120)

            set_progress(f"Restarting web server on '{server.hostname}'")
            server.execute_script(script_contents="sudo runuser -l root -c 'systemctl restart httpd'", timeout=180)

            set_progress(f"Initiating database migration in background on server '{server.hostname}'...")
            
            # Clean up old log files before starting
            server.execute_script(script_contents="sudo runuser -l root -c 'rm -f /tmp/cb_migration.log /tmp/cb_migration.done'", timeout=60)

            # Launch migration in background using nohup so script returns immediately
            start_bg_migration_cmd = (
                "sudo runuser -l root -c '"
                "nohup bash -c \"/opt/cloudbolt/manage.py migrate --noinput > /tmp/cb_migration.log 2>&1; echo \\$? > /tmp/cb_migration.done\" >/dev/null 2>&1 &'"
            )
            server.execute_script(script_contents=start_bg_migration_cmd, timeout=60)

            # Poll the log file continuously to display real-time progress in CloudBolt UI
            max_poll_time_seconds = 3600  # 1 hour limit
            poll_interval = 15            # Check log every 15 seconds
            elapsed = 0
            last_line_count = 0

            while elapsed < max_poll_time_seconds:
                time.sleep(poll_interval)
                elapsed += poll_interval

                # Check if process is complete
                res = server.execute_script(
                    script_contents="sudo runuser -l root -c 'test -f /tmp/cb_migration.done && cat /tmp/cb_migration.done || echo RUNNING'",
                    timeout=30
                ).strip()

                # Stream new log output lines back to CloudBolt set_progress
                log_output = server.execute_script(
                    script_contents="sudo runuser -l root -c 'tail -n 10 /tmp/cb_migration.log 2>/dev/null || true'",
                    timeout=30
                ).strip()

                if log_output:
                    # Print the last active line in CloudBolt progress bar
                    latest_status = log_output.split("\n")[-1]
                    set_progress(f"Migration Status ({elapsed}s elapsed): {latest_status}")

                if res != "RUNNING":
                    if res == "0":
                        set_progress(f"Database migration completed successfully on '{server.hostname}'!")
                        break
                    else:
                        full_error_log = server.execute_script(
                            script_contents="sudo runuser -l root -c 'tail -n 50 /tmp/cb_migration.log'",
                            timeout=60
                        )
                        raise RuntimeError(f"Database migration failed on '{server.hostname}' with exit code {res}. Log details:\n{full_error_log}")

            if elapsed >= max_poll_time_seconds:
                raise RuntimeError(f"Timed out waiting for database migration to complete after {max_poll_time_seconds} seconds.")

            first_instance = False
        else:
            set_progress(f"Restarting httpd on secondary node '{server.hostname}'")
            server.execute_script(script_contents="sudo runuser -l root -c 'systemctl restart httpd'", timeout=180)