"""
bak.py - automatically perform a bitwarden backup. this script checks to see if the target directory has changed since it was last backed up, and if so it does a backup with verification.

important questions:

	1. isn't it insecure to store an API key in the clear like that?
	
		A: yes, which is why we will ONLY store the API key for the account we use to back up, and never store anything else on that account. gaining access to that API key only gets you the information we're automatically backing up (which you had anyway, since the originals are stored in the clear on the machine that's doing the backups in the first place). We can still access this easily enough by just putting it in the same organization we're already a part of.
	
	2. won't we run out of space if we store it directly on bitwarden?
	
		yes, but it's easy to buy more and probably less unethical than buying from google anyway

general process:
	1. calculate unzipped checksum on the target directory
	2. compare against recorded checksum. if they're the same, nothing has changed and there's no need to backup, stop here. otherwise...
	3. zip the target dir
	4. log in to bitwarden in the backup-automation account (NOT the main one)
	5. upload zipped file to bitwarden (to a collection that both the main and the backup accoutn can see)
	6. redownload the file we just uploaded
	7. verify checksum on the redownloaded and original zips are the same, if so delete both from local and the old zip from cloud. if not, error out, log everything, and delete the local zips
"""