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

from checksum_calc import get_dirs_checksum_mismatch, md5_single_file
from pathlib import Path
from datetime import datetime
from bitwarden_manager import *
import zipfile

#TODO parameterize all of these
# checksum related
TARGET_DIRS = [Path('./test_target_dir_1/'),Path('./test_target_dir_2/')]
OLD_CHECKSUM_FILE = Path('./test_old_checksum_file')
CHECKSUM_BLOCK_SIZE = 1024

# crypto/bitwarden related
PATH_TO_BITWARDEN_EXE = Path("path/to/bw") # TODO config file instead of hardcode (also fix references later on... somehow. this is basically a 'context' thing so maybe that? or we could just read the config here; actually we basically sidestepped this problem by switching from singleton to dep inject)
PATH_TO_PASSWORD_FILE = Path("path/to/pw") # TODO config file, same here
TARGET_COLLECTION_NAME = "automation-test/wrt-bak-tbp"
TARGET_ORGANIZATION_NAME = "cardboard"
TARGET_ITEM_PARTIAL_MATCH_ALL = "AUTO_BAK"

# file handling related
TMP_DIR = Path("./tmp/")

# misc config
PERFORM_REDOWNLOAD_CHECK = True # whether to redownload the file and do a checksum verification on it vs the zip we uploaded

def gen_filename(additional_file_name_info:str=""):
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
	return TMP_DIR / f"{additional_file_name_info}AUTO_BAK_{year}-{month}-{day}_{hour}{minute}{second}_{microsecond}.zip"

def zip_dirs(paths_to_dirs):
	"""
	zip the target directories
	"""
	# make the tmp dir if it doesn't exist
	if not os.path.isdir(TMP_DIR):
		os.mkdir(TMP_DIR)
	# first get the new file name
	zipfname = gen_filename()
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
	
	# first, check if we actually need to do anything
	dirs_are_same, current_checksum = get_dirs_checksum_mismatch(TARGET_DIRS, OLD_CHECKSUM_FILE, CHECKSUM_BLOCK_SIZE)
	
	if dirs_are_same:
		print("Nothing to do, no changes detected!")
		exit(0)
	
	print("Detected change in directories-checksum. Attempting to perform backup")
	
	# first, zip the dirs together
	temp_zipfname = zip_dirs(TARGET_DIRS)
	print(f"target directories zipped to {temp_zipfname}")

	# next, calculate checksum on the zip itself
	if PERFORM_REDOWNLOAD_CHECK:
		print("calculating checksum on zipped dirs")
		temp_zip_checksum = md5_single_file(temp_zipfname,CHECKSUM_BLOCK_SIZE)
		print(f"zipfile checksum: {temp_zip_checksum}")

	# set up bitwarden commander
	sbp_cmdr = RealSubprocessCommander()
	bw_cmdr = BitwardenCommander(sbp_cmdr,PATH_TO_BITWARDEN_EXE,PATH_TO_PASSWORD_FILE)

	# now get the organization we're targeting
	print(f"getting organization info for {TARGET_ORGANIZATION_NAME}...")
	org = BitwardenOrganization.find_organization(bw_cmdr,TARGET_ORGANIZATION_NAME)

	# now get the collection within that organization that we want
	print(f"getting collection info for {TARGET_COLLECTION_NAME}...")
	coll = org.find_collection(TARGET_COLLECTION_NAME)

	# now find the most recent backup in that collection (there should only be one there)
	print("Checking for existing backups...")
	bak_item = None
	try:
		bak_item = coll.find_item(TARGET_ITEM_PARTIAL_MATCH_ALL)
	except BitwardenItemNotFoundError as e:
		print("no backup already exists in this collection -- making a new one but NOT deleting anything!")

	# make a new item to attach the new backup to
	new_item_name = re.match(r'.*(AUTO_BAK.*)\.zip',str(temp_zipfname)).group(1) # everything but the '.zip'
	print(f"creating new item for this upload: {new_item_name}")
	new_item = coll.create_note_item_for_attachment(new_item_name,org.bw_id)

	# upload the zip to that note
	print(f"performing attachment upload...")
	attach_obj = new_item.create_upload_attachment(temp_zipfname)
	print("attachment upload complete!")

	# redownload (if requested)
	if PERFORM_REDOWNLOAD_CHECK:
		print("performing re-download check")
		# make a new item to attach the new download to
		redownload_fname = gen_filename("REDL_CHECK_")
		print(f"redownloaded file will be saved to {redownload_fname}")

		# sync prior to performing further bitwarden commands (this is so we can get the attachment properly)
		print("syncing prior to redownload")
		bw_cmdr.sync()

		# the attached-to item object should still be valid though
		print("getting attachments for attach-to item...")
		attachments = new_item.get_attachments()

		# should only be one of these
		if len(attachments) > 1:
			print(f"WARNING: multiple attachments found on newly created attach-to item, will assume first ({attachments[0].name})")

		redl_attach_obj = attachments[0]
		print(f"attachment found! name is {redl_attach_obj.name}")
		# set output file
		redl_attach_obj.output_path = redownload_fname

		# download
		print("redownloading attachment...")
		redl_attach_obj.download()
		print(f"attachment redownloaded to {redownload_fname}")

		# verify checksum
		redl_checksum = md5_single_file(redownload_fname)

		if redl_checksum != temp_zip_checksum:
			print("ERROR: redownloaded file checksum does not match original file checksum.")
		else:
			print("uploaded and original zip files have matching checksums")
		print(f"old: {temp_zip_checksum}")
		print(f"new: {redl_checksum}")

		print("removing temp-redownload file")
		os.remove(redownload_fname)

	# delete the old record (if it existed)
	if bak_item is not None:
		print("deleting old record from bitwarden...")
		bak_item.delete_from_bw()

	# relock
	bw_cmdr.lock()

	print("deleting temporary zip file...")
	os.remove(temp_zipfname)

	# update last known checksum
	print(f"updating last-known-checksum to {current_checksum}")
	with open(OLD_CHECKSUM_FILE,'w') as checksum_file:
		checksum_file.write(current_checksum)