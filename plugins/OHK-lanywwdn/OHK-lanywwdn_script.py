#!/usr/bin/env python

"""
This action should be run as a recurring job, 
"""
import datetime
from common.methods import set_progress
from infrastructure.models import Server


def run(job, *args, **kwargs):
    threshold_days = '{{ threshold_days }}'
    if not threshold_days:
        threshold_days = 365
    delete_date = datetime.datetime.now() - datetime.timedelta(days=int(threshold_days))
    msg = "Will delete historical servers older than {} days (from before {}) ".format(
        threshold_days, delete_date.date())
    set_progress(msg)
    deleted_servers = 0
    old_job_ids = []
    for server in Server.objects.filter(status="HISTORICAL"):
        last_event = server.serverhistory_set.last()
        if not last_event: continue
        if last_event.action_time < delete_date:
            server.delete()
            deleted_servers += 1
    set_progress("Purged {} old server records".format(len(old_job_ids)))
    
    return ("SUCCESS", "", "")

if __name__ == '__main__':
    run()