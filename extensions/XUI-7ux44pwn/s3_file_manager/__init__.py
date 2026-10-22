"""
S3 File Manager XUI: an AWS-console-style browser tab on every s3_bucket
Resource, plus a super-admin admin page.

The tab's table is CMP DataTables fed by objects.json; every write is a
CloudBolt dialog (@dialog_view + C2Form) run through one dispatcher that also
writes a ResourceHistory row per action. AWS work and the ConnectionInfo-backed
authorization live in models.py; bucket deletion goes through an approval Order.

Docs: proserv/s3_file_manager/README.md
"""
