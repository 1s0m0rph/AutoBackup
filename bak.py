USAGE = """
bak.py - automatically perform a bitwarden backup. this script checks to see if the target directory has changed since it was last backed up, and if so it does a backup with verification.

USAGE: bak.py <path to config ini>
"""

"""
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

from checksum_calc import get_dirs_checksum_mismatch, md5_single_file
from config_manager import AutobakConfig
from pathlib import Path
from datetime import datetime
from bitwarden_manager import *
import zipfile
import logging
from sys import argv

def gen_filename(cfg:AutobakConfig,additional_file_name_info:str=""):
	"""
	generate the filename for a zipfile created right now. adding precise times ensures unique file names

	additional info added to the beginning of the file name
	"""
	# format (e.g.): AUTO_BAK_2023-03-18_111004_123456.zip
	d8 = datetime.now()
	year = d8.year
	month = f'{d8.month:02}'
	day = f'{d8.day:02}'
	hour = f'{d8.hour:02}'
	minute = f'{d8.minute:02}'
	second = f'{d8.second:02}'
	microsecond = f'{d8.microsecond:06}'
	return cfg.path_to_tmp_dir / f"{additional_file_name_info}AUTO_BAK_{year}-{month}-{day}_{hour}{minute}{second}_{microsecond}.zip"

def zip_dirs(cfg:AutobakConfig,paths_to_dirs,additional_fname_info=""):
	"""
	zip the target directories
	"""
	# make the tmp dir if it doesn't exist
	if not os.path.isdir(cfg.path_to_tmp_dir):
		os.mkdir(cfg.path_to_tmp_dir)
	# first get the new file name
	zipfname = gen_filename(cfg,additional_fname_info)
	# now attempt to do the zip command
	# directory level zipping shamelessly stolen from https://stackoverflow.com/questions/1855095/how-to-create-a-zip-archive-of-a-directory
	with zipfile.ZipFile(zipfname, 'w') as zf:
		for path in paths_to_dirs:
			for root,dirs,files in os.walk(path):
				for file in files:
					zf.write(os.path.join(root,file),
							 os.path.relpath(os.path.join(root,file),os.path.join(path,'..')))
			zf.write(path)

	return zipfname

if __name__ == '__main__':

	# parse command line
	if len(argv) < 2:
		print(USAGE)
		print("Error: required at least 1 argument for config INI location")
		exit(1)

	# first argument is config
	cfg_file_path = Path(argv[1])

	# first, get config
	cfg = AutobakConfig(cfg_file_path)

	# set up logging
	logger = logging.getLogger("AutoBackup")
	log_handler = logging.FileHandler(cfg.path_to_log_file)
	log_fmt = logging.Formatter(fmt = '%(asctime)s, from `%(module)s` %(levelname)s: %(message)s', datefmt = '%Y-%m-%d %H:%M:%S %Z')
	log_handler.setFormatter(log_fmt)
	logger.addHandler(log_handler)
	logger.setLevel(cfg.log_level)

	logger.info("Autobackup script initialized.")

	try: # handle ALL exceptions during runtime so we at least get a log of them
		# check if we actually need to do anything
		dirs_are_same, current_checksum = get_dirs_checksum_mismatch(cfg.target_dirs,
																	 cfg.most_recent_checksum_file,
																	 cfg.checksum_block_size)

		if dirs_are_same:
			logger.info("Nothing to do, no changes detected!")
			exit(0)

		logger.info("Detected change in directories-checksum. Attempting to perform backup")

		# first, zip the dirs together
		temp_zipfname = zip_dirs(cfg,cfg.target_dirs,cfg.additional_prefix)

		logger.debug(f"target directories zipped to {temp_zipfname}")

		# next, calculate checksum on the zip itself
		if cfg.perform_redownload_check:
			logger.debug("calculating checksum on zipped dirs")
			temp_zip_checksum = md5_single_file(temp_zipfname,cfg.checksum_block_size)
			logger.debug(f"zipfile checksum: {temp_zip_checksum}")

		# set up bitwarden commander
		sbp_cmdr = RealSubprocessCommander()
		bw_cmdr = BitwardenCommander(sbp_cmdr,cfg.path_to_bw_exe,cfg.path_to_pw_file)

	except BaseException as e:
		if (SystemExit == type(e)) and ("0" == str(e)):
			# not an error, exit normally
			exit(0)

		logger.critical(f"Caught unhandled exception during runtime, prior to initializing the bitwarden commander: {type(e).__name__}: {e}.")

		# reraise exception after catching -- we just wanted a record of it
		raise e

	# all exceptions from here on out should attempt to relock the vault after being caught
	try:
		# now get the organization we're targeting
		logger.debug(f"getting organization info for {cfg.target_org}...")
		org = BitwardenOrganization.find_organization(bw_cmdr,cfg.target_org)

		# now get the collection within that organization that we want
		logger.debug(f"getting collection info for {cfg.target_coll}...")
		coll = org.find_collection(cfg.target_coll)

		# now find the most recent backup in that collection (there should only be one there)
		logger.debug("Checking for existing backups...")
		bak_item = None
		try:
			bak_item = coll.find_item("AUTO_BAK")
		except BitwardenItemNotFoundError as e:
			logger.info("no backup already exists in this collection -- making a new one but NOT deleting anything!")

		# make a new item to attach the new backup to
		new_item_name = temp_zipfname.stem # everything but the path and the '.zip'
		logger.info(f"creating new item for this upload: {new_item_name}")
		new_item = coll.create_note_item_for_attachment(new_item_name,org.bw_id)

		# upload the zip to that note
		logger.info(f"performing attachment upload...")
		attach_obj = new_item.create_upload_attachment(temp_zipfname)
		logger.info("attachment upload complete!")

		# redownload (if requested)
		if cfg.perform_redownload_check:
			logger.info("performing re-download check")
			# make a new item to attach the new download to
			redownload_fname = gen_filename(cfg,"REDL_CHECK_")
			logger.debug(f"redownloaded file will be saved to {redownload_fname}")

			# sync prior to performing further bitwarden commands (this is so we can get the attachment properly)
			logger.debug("syncing prior to redownload")
			bw_cmdr.sync()

			# the attached-to item object should still be valid though
			logger.debug("getting attachments for attach-to item...")
			attachments = new_item.get_attachments()

			# should only be one of these
			if len(attachments) > 1:
				logger.warning(f"WARNING: multiple attachments found on newly created attach-to item, will assume first ({attachments[0].name})")

			redl_attach_obj = attachments[0]
			logger.debug(f"attachment found! name is {redl_attach_obj.name}")
			# set output file
			redl_attach_obj.output_path = redownload_fname

			# download
			logger.info("redownloading attachment...")
			redl_attach_obj.download()
			logger.info(f"attachment redownloaded to {redownload_fname}")

			# verify checksum
			redl_checksum = md5_single_file(redownload_fname)

			if redl_checksum != temp_zip_checksum:
				logger.error("ERROR: redownloaded file checksum does not match original file checksum.")
			else:
				logger.info("uploaded and original zip files have matching checksums")
			logger.debug(f"old: {temp_zip_checksum}")
			logger.debug(f"new: {redl_checksum}")

			logger.debug("removing temp-redownload file")
			os.remove(redownload_fname)

		# delete the old record (if it existed)
		if bak_item is not None:
			logger.info("deleting old record from bitwarden...")
			bak_item.delete_from_bw()

		# relock
		bw_cmdr.lock()

		logger.debug("deleting temporary zip file...")
		os.remove(temp_zipfname)

		# update last known checksum
		logger.debug(f"updating last-known-checksum to {current_checksum}")
		with open(cfg.most_recent_checksum_file,'w') as checksum_file:
			checksum_file.write(current_checksum)

		logger.info("Update complete!")
	except BaseException as e:
		# we caught an exception after initializing the commander, attempt to relock
		logger.critical(f"Caught unhandled exception during runtime AFTER initializing bitwarden commander: {type(e).__name__}: {e}.")

		# attempt to relock
		logger.critical(f"Attempting to relock vault after critical error.")
		try:
			bw_cmdr.lock()
			logger.critical("Post-critical-error vault relock successful.")
		except BaseException as e:
			logger.critical(f"Caught unhandled exception while attempting to relock vault after critical error. Vault lock state cannot be determined.")

			# reraise exception after catching -- we just wanted a record of it
			raise e