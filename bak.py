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

from checksum_calc import get_dirs_checksum_mismatch
from pathlib import Path
import zipfile

#TODO parameterize all of these
# checksum related
TARGET_DIRS = [Path('./test_target_dir_1/'),Path('./test_target_dir_2/')]
OLD_CHECKSUM_FILE = Path('./test_old_checksum_file')
CHECKSUM_BLOCK_SIZE = 1024

# crypto/bitwarden related
API_KEY_FILE = Path('./api_key.json')
TARGET_COLLECTION_NAME = "automation-test/wrt-bak-tbp"
TARGET_ORGANIZATION_NAME = "cardboard"

# file handling related
TMP_DIR = Path("./tmp/")

def gen_filename():
	"""
	generate the filename for a zipfile created right now. adding precise times ensures unique file names
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
	return TMP_DIR / "AUTO_BAK_{}-{}-{}_{}{}{}_{}.zip".format(year, month, day, hour, minute, second, microsecond)

def zip_dirs(paths_to_dirs):
	"""
	zip the target directories
	"""
	# first get the new file name
	zipfname = gen_filename()
	# now attempt to do the zip command
	with zipfile.ZipFila(zipfname, 'w') as zf:
		for path in paths_to_dirs:
			zf.write(path)
	
	return zipfname
	
def get_bw_org_id(org_name):
	"""
	get the actual organization id, given the requested organization name
	
	command is: `/path/to/bw/executable list organizations --search <org name>`
	since I don't think you can specify that that has to be the full name, we can post-process once we have the result
	"""
	#TODO cache the org/collection IDs
	pass
	
def get_bw_collection_id(org_name, collection_name):
	"""
	get the actual collection ID, given the requested org/collection name
	note that collection name can be a nested thing to look more like a path (this is provided by default by bitwarden)
	
	command is: `/path/to/bw/executable list org-collections --organizationid <org id> --search <collection name>`
	and as with the org ID, we should postprocess this to make sure we get exactly one collection name
	"""
	#TODO cache the org/collection IDs. may want to use an object to handle them
	org_id = get_bw_org_id(org_name)
	pass
	
def get_bw_obj_in_collection(org_name, collection_name, obj_name_partial):
	"""
	get a list of matching objects within the specified collection
	object name does not need to be complete. partial matching will be done
	
	command is: `/path/to/bw/executable list items --organizationid <org id> --collectionid <coll id> --search <obj name>`
	"""
	pass
	
def create_bw_note_obj_in_coll(obj_details_encoded):
	"""
	create a new object that we can attach things to, and return its ID for attaching
	
	note that the details have to be encoded first and are very particular about the fields being configured correctly. General rules of thumb:
		1. don't have any :null fields
		2. collection IDs are a literal list (e.g. "collectionIds":["some-random-coll-id"])
		3. the 'type' field that isn't within the 'secureNote' field is some kind of encoding type. for secure note you want 2
		4. the 'secureNote' field should contain the type, i.e. "secureNote":{"type":0}
		
	all of that fails if you aren't attaching to notes so... attach to notes I guess
	
	command is: `/path/to/bw/executable create item <encoded item data>`
	"""
	pass

def upload_file_as_attachment_to_bw(item_id, path_to_file):
	"""
	files on bitwarden are really just "attachments". irritatingly, these have a max size of 500 MB, so we'll need to keep that in mind throughout this process
	
	returns the attachment ID
	
	command is: `/path/to/bw/executable create attachment --file <path to file> --itemid <item id>`
	I'm pretty sure the item has to actually exist beforehand, too
	"""
	pass

def download_attachment_from_bw(item_id, attach_name, output_path):
	"""
	download the attachment of the specified name attached to the specified item, and save to the output path
	I'm pretty sure output path actually needs to be nonexistent for this to work so... don't make it beforehand or anything
	
	command is: `/path/to/bw/executable get attachment <attachment name> --itemid <ID of the item it's attached to> --output <output path>`
	"""
	pass
	
def do_bw_sync():
	"""
	often need to sync before actually doing anything to bitwarden, so here's a fn for that
	
	command is: `/path/to/bw/executable sync`
	"""
	pass

if __name__ == '__main__':
	
	# first, check if we actually need to do anything
	dirs_are_different, current_checksum = get_dirs_checksum_mismatch(TARGET_DIRS, OLD_CHECKSUM_FILE, CHECKSUM_BLOCK_SIZE)
	
	if not dirs_are_different:
		print("Nothing to do, no changes detected!")
		exit(0)
	
	print("Detected change in directories-checksum. Attempting to perform backup")
	
	# first, zip the dirs together
	temp_zipfname = zip_dirs(TARGET_DIRS)
	
	# now figure out