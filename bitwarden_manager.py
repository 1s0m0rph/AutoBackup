"""
bitwarden is apparently a bit of a monster to manage, so we're making a class to do it for us

Class does the following things (more of a plan so I know what to put here):
	get an organization ID
	get an org-collection ID
	list the items in a collection (provides IDs and names)
	create a new note in a collection (used to attach things to)
	upload a file as an attachment to a note
	download a file that was attached to a note
"""

from abc import ABC
from pathlib import Path
import re
import subprocess as sbp
from typing import List
import json
import os

class SingletonMultipleInitError(Exception):
	pass

class InvalidMasterPasswordError(Exception):
	pass

class VaultNotUnlockedError(Exception):
	pass

class BitwardenItemNotFoundError(Exception):
	pass

class SubprocessCommander(ABC):
	"""
	ultimately a very simple class/interface that we can use to cut off execution right before actually spawning the 'command bitwarden' process for unit testing purposes
	"""

	def exe_wait_sbp_command(self,command:List[str]) -> list:
		raise NotImplementedError

	def exe_wait_sbp_command_with_piped_info(self,command:List[str],info:str) -> list:
		raise NotImplementedError

class RealSubprocessCommander(SubprocessCommander):
	def exe_wait_sbp_command(self,command:List[str]) -> list:
		"""
		execute a subprocess command with the given arguments and wait for it to return (blocking call)
		return the output of the command
		"""
		proc = sbp.Popen(command,stdout=sbp.PIPE,stderr=sbp.PIPE,text=True)
		# wait for execution to complete (better be a finite one!)
		proc.wait()
		# a bit of preprocessing here so it's not raw binary
		return list(proc.stdout)

	def exe_wait_sbp_command_with_piped_info(self,command: List[str],info: str) -> list:
		"""
		same as the other one, but we give the command a bit of input too
		"""
		proc = sbp.Popen(command,stdout=sbp.PIPE,stderr=sbp.PIPE,stdin=sbp.PIPE,text=True)
		# give the input using communicate
		stdout_dat, stderr_dat = proc.communicate(info)
		return stdout_dat

class BitwardenCommander:

	def __init__(self, sbp_cmd:SubprocessCommander, path_to_bw_executable:Path, path_to_pw_file:Path):
		"""
		The first file should be the path to the bitwarden executable
		The second file should be a single line password file
			# WARNING: if you aren't careful about how you store this password, you could be exposing yourself to some serious security risks! Ideally, use an alternate account that exists *solely* for automated backups like this.
		"""
		self.sbp_cmd = sbp_cmd
		self.path_to_bw_executable = path_to_bw_executable
		self.path_to_pw_file = path_to_pw_file

		self.sync_observers = set() # will be filled out as we go
		# session keys don't expire (until replaced), so once we get this once we're good
		self.session_key = None # set the first time we do a command

	def register_sync_observer(self, sync_observer):
		self.sync_observers.add(sync_observer)

	def perform_sync_notify(self):
		"""
		notify all of our bitwarden-sync observers that a sync was performed and caches must be cleared
		"""
		for observer in self.sync_observers:
			observer.sync()

	def sync(self):
		"""
		synchronize the vault
		"""
		# just do the command itself and let notify-detection handle it
		sync_result = self.exe_bw_command(['sync'])
		print(sync_result) #TODO log

	def lock(self):
		"""
		lock the vault. need to be calling this every time we are done for a while so the session key doesn't hang around
		"""
		self.exe_bw_command(["lock"])
		self.session_key = None # reset this so we know to get a new one

	def unlock(self):
		"""
		primarily useful since the unlock sequence is somewhat nontrivial
		this function goes through the process of getting a new session key

		Note that we're assuming you already did a login at some point and that things are currently locked!
		"""
		if self.session_key is not None:
			#TODO log instead
			print("WARNING: requested unlock, but session key already existed. Not creating a new one.")
			return # nothing to do

		# make sure the password file exists before proceeding
		if not os.path.isfile(self.path_to_pw_file):
			raise FileNotFoundError(self.path_to_pw_file)

		# otherwise, perform the unlock procedure. fundamentally, this is just one command
		# manually format command since the normal execution method checks for session key existence
		command = [str(self.path_to_bw_executable),
				   "unlock",
				   "--passwordfile",
				   str(self.path_to_pw_file),
				   "--raw"]
		unlock_output = self.sbp_cmd.exe_wait_sbp_command(command)
		# sanity check: if this is not the right password we won't be able to use this is a key, so make sure it's right before continuing
		if re.match(r'.*Invalid.*password.*', unlock_output[0]) is not None:
			raise InvalidMasterPasswordError
		# otherwise, should be valid
		self.session_key = unlock_output[0]
		print("Session key set. Vault is unlocked.")  # TODO: log instead of print
		# also sync just to be sure
		self.sync()

	def exe_bw_command(self, bw_args:List[str]):
		"""
		execute a single bitwarden command

		bw_args contains all of the arguments that the caller wants passed to bitwarden
		for example if you want to do a 'get org ID' command for the organization `example`, you'd pass this string:
			'list organizations --search example'

		this function will add everything else that's needed including managing the session key

		this function will return whatever the command returned
		"""
		if self.session_key is None:
			# unlock first
			self.unlock()
		# check if we need to notify of synchronization
		if re.match(r"\s*sync\s*", bw_args[0]) is not None:
			# sync-notify
			self.perform_sync_notify()
		# add session key info and execute
		sbp_args = [str(self.path_to_bw_executable)] + bw_args + ['--session', self.session_key]
		return self.sbp_cmd.exe_wait_sbp_command(sbp_args)

	def exe_bw_encode_cmd(self,unencoded_json:str):
		"""
		encode the unencoded json and return it as a str
		the bw cli is really dumb about this and *requires* you to pipe the input in
		"""
		command = [str(self.path_to_bw_executable),'encode']
		res = self.sbp_cmd.exe_wait_sbp_command_with_piped_info(command,unencoded_json)
		return res

	def find_object_info(self,get_qry_command: List[str], search_text:str):
		"""
		find an object in bitwarden and return its info text. caller's responsibility to figure out what to do with the info text

		query-text should contain the whole query as it would be passed into exe_bw_cmd, except for the search term e.g. to find an item:
			find_object_info(['list','items'],search_text)
		or to find a collection within an organization
			find_object_info(['list','org-collections','--organizationid',org_id],search_text)
		"""
		# finish the command formatting
		command = get_qry_command + ['--search', search_text]#TODO not entirely sure what happens if you have spaces in your text... but adding ""s breaks it so...
		res = self.exe_bw_command(command)[0]
		if re.match(r"^[\[{].*",res) is None:
			raise BitwardenItemNotFoundError(f"Unable to find items for {search_text}. (got 'Not found' from BW).")
		raw_res = json.loads(res)
		if len(raw_res) == 0:
			raise BitwardenItemNotFoundError(f"Unable to find items for {search_text}.")
		res = dict(raw_res[0]) # default to the first item
		for res_item in raw_res:
			if res_item['name'] == search_text:
				#TODO log
				print(f"Exact match found in search results (for {search_text}). assuming that was the intent")
				res = res_item

		# no further processing to do here, up to the caller		
		return res


class CacheableBitwardenObject(ABC):
	def __init__(self,bw_commander:BitwardenCommander):
		self.bw_commander = bw_commander
		# self-register with the observee
		self.bw_commander.register_sync_observer(self)

	def sync(self):
		raise NotImplementedError

	def __hash__(self):
		raise NotImplementedError

class BitwardenObject(CacheableBitwardenObject):
	"""
	generic bitwarden object (something we can do a get() on)
	"""
	
	def __init__(self,bw_commander:BitwardenCommander,bw_id):
		self.bw_id = bw_id # has to be done before the super class constructor call in order for us to be able to self-reg

		super().__init__(bw_commander)

		self.info_cache = None

	def __hash__(self):
		# since we really only need the ID to implement this, we can do it here
		# TODO is it valid to assume that all BW objects have different IDs?
		return self.bw_id.__hash__()

	def get_info(self):
		if self.info_cache is not None:
			return self.info_cache
		self.info_cache = self.get_info_from_bw()
		return self.info_cache

	def get_info_from_bw(self):
		"""
		get the item's info from bitwarden directly, bypassing any cache
		"""
		raise NotImplementedError
	
	def sync(self):
		self.info_cache = None

class BitwardenItemAttachment(BitwardenObject):
	"""
	handles a single item attachment
	"""
	
	def __init__(self,
				 bw_commander: BitwardenCommander,
				 bw_id,
				 name,
				 item_attached_to: BitwardenObject,
				 path_to_input_file=None,
				 path_to_output=None):
		super().__init__(bw_commander,bw_id)
		self.name = name
		self.item_attached_to = item_attached_to
		self.input_path = path_to_input_file
		self.output_path = path_to_output

	def __repr__(self):
		return f"Item attachment. Attached to {self.item_attached_to}, name is {self.name}, ID is {self.bw_id}"

	def get_info_from_bw(self):
		"""
		item attachments are a bit weird in that you can't get them directly
		this shouldn't ever actually get called since you're only supposed to make these objects from within an item object
		"""
		raise NotImplementedError("Attachment objects should have their info already made on-construction.")

	def download(self):
		"""
		download this item from bitwarden

		command is `get attachment <attach name> --itemid <ID of the attached-to item> --output <path>`
		"""
		command = ['get','attachment',self.name,'--itemid',self.item_attached_to.bw_id]
		if self.output_path is None:
			print(f"WARNING: no output path provided for {self} download. Default path will be used.")#TODO log
		else:
			command += ['--output', str(self.output_path)]
		dl_result = self.bw_commander.exe_bw_command(command)
		print(dl_result) #TODO log, maybe check for errors too

	def upload(self):
		"""
		upload this item to bitwarden

		command is `create attachment --file <path to file> --itemid <item id to attach to>`
		"""
		if self.input_path is None:
			raise ValueError(f"Input path for {self} is not set. Must be set prior to uploading.")

		command = ['create', 'attachment', '--file', str(self.input_path), '--itemid', self.item_attached_to.bw_id]
		ul_result = self.bw_commander.exe_bw_command(command)
		print(ul_result)  #TODO log, maybe check for errors too

class BitwardenItem(BitwardenObject):
	"""
	handles a single item
	"""
	
	def __init__(self,bw_commander: BitwardenCommander,bw_id):
		super().__init__(bw_commander,bw_id)

		self.attachments_have_been_downloaded = False # important distinction since we do cache-as-we-go for uploads
		self.attachments_cache = None # will be filled out as we go
		self.info_cache = None

	def __repr__(self):
		rstr = f"Bitwarden item. ID is {self.bw_id}."
		# add cached info if we have it
		if self.attachments_cache is not None:
			rstr += f" {len(self.attachments_cache)} attachments."
		if self.info_cache is not None:
			rstr += " Server info is cached."
		return rstr

	def get_info_from_bw(self):
		"""
		get the object info from bitwarden

		command is `get item <id>`
		"""
		return dict(json.loads(self.bw_commander.exe_bw_command(['get','item',self.bw_id])[0]))

	def get_attachments(self):
		"""
		return a list of attachments for this item
		format is list of attachment objects
		"""
		if self.attachments_cache is not None and self.attachments_have_been_downloaded:
			return self.attachments_cache
		else:
			self.attachments_cache = []
			# actually get the attachments from bitwarden
			# first have to get this actual item
			item_details = self.get_info()
			# now parse that for the 'attachments' field
			if 'attachments' not in item_details:
				# no attachments
				print(f"No attachments for item {self}.")
			else:
				# some attachments! make objects for them
				for attachment in item_details['attachments']:
					attach_id = attachment['id']
					attach_name = attachment['fileName']
					new_obj = BitwardenItemAttachment(self.bw_commander,attach_id,attach_name,self)
					# cache its info now since we have it
					new_obj.info_cache = attachment
					self.attachments_cache.append(new_obj)
				print(f"{len(self.attachments_cache)} attachments found for item {self}.")

			self.attachments_have_been_downloaded = True
			return self.attachments_cache

	def create_upload_attachment(self,attach_file_input):
		"""
		create, upload, and cache an attachment
		"""
		# first make the new attachment object
		# TODO we will have issues on the observer side if we make more than one attachment this way, unless we want to generate a new ID for the attachment obj. granted, the attachment objects don't have special caches so it isn't a big deal if they aren't sync-notified but still
		new_obj = BitwardenItemAttachment(self.bw_commander,"NO_ID",str(attach_file_input),self,path_to_input_file=attach_file_input)

		# register that in our cache (but don't modify the 'have been downloaded' flag!)
		if self.attachments_cache is None:
			self.attachments_cache = []
		self.attachments_cache.append(new_obj)

		# upload the attachment
		new_obj.upload()

		return new_obj

	def delete_from_bw(self):
		"""
		delete this from bitwarden completely

		command is `delete item <id> --permanent`
		"""
		del_result = self.bw_commander.exe_bw_command(['delete','item',self.bw_id,'--permanent'])
		print(del_result)#TODO log

	def sync(self):
		super().sync()
		# clear all lower level caches
		self.attachments_cache = None
		self.attachments_have_been_downloaded = False

	@staticmethod
	def find_item(bw_commander:BitwardenCommander,search_text):
		"""
		used to find a single bare item (not attached to an collection, and can't really be cached)
		"""
		find_info_cmd = ['list', 'items']
		find_info_res = bw_commander.find_object_info(find_info_cmd,search_text)
		# create an actual object for this
		found_obj = BitwardenItem(bw_commander,find_info_res['id'])
		# precache since we have it already
		found_obj.info_cache = find_info_res
		return found_obj

class BitwardenCollection(BitwardenObject):

	def __init__(self,bw_commander: BitwardenCommander,bw_id):
		super().__init__(bw_commander,bw_id)
		
		self.items_cache = {}

	def __repr__(self):
		rstr = f"Bitwarden collection, id = {self.bw_id}. {len(self.items_cache)} object(s) are cached."

	def get_info_from_bw(self):
		"""
		command is `get collection <id>`
		"""
		return dict(json.loads(
			self.bw_commander.exe_bw_command(
				['get','collection',self.bw_id])[0]))

	def find_item(self,search_text:str):
		"""
		get a specific item within this coll

		command is `list items --collectionid <id> --search <search_text>`
		search_text is a partial serach, so 'est' will match an object called 'Test'
		"""
		if search_text in self.items_cache:
			return self.items_cache[search_text]
		else:
			find_info_cmd = ['list','items','--collectionid',self.bw_id]
			find_info_res = self.bw_commander.find_object_info(find_info_cmd,search_text)
			# create an actual object for this
			found_obj = BitwardenItem(self.bw_commander,find_info_res['id'])
			# precache since we have it already
			found_obj.info_cache = find_info_res
			# add to our cache
			self.items_cache.update({search_text: found_obj})
			# return that
			return found_obj

	def create_note_item_for_attachment(self, note_name:str, organization_id:str = None) -> BitwardenItem:
		"""
		create a new blank note within this collection specifically for attaching something to it

		command is `create item <encoded json>`, but getting that encoded json is nontrivial
		"""
		# first, make the normal json as a dict
		unencoded_dict = {
			"collectionIds":[self.bw_id],
			"type":2,
			"name":note_name,
			"notes":"",
			"favorite":False,
			"fields":[],
			"secureNote":{"type":0},
			"reprompt":0
		}
		if organization_id is not None:
			unencoded_dict.update({'organizationId':organization_id})
		# then throw that in json properly
		unencoded_json = json.dumps(unencoded_dict)
		# then encode it using bitwarden
		encoded_json = self.bw_commander.exe_bw_encode_cmd(unencoded_json)
		# perform the creation command
		create_out_raw = self.bw_commander.exe_bw_command(['create','item',encoded_json])

		# finally, store that info in an item object and return it
		create_out = dict(json.loads(create_out_raw[0]))
		new_obj = BitwardenItem(self.bw_commander,create_out['id'])
		# precache this object
		new_obj.info_cache = create_out
		return new_obj

	def sync(self):
		super().sync()
		self.items_cache = {}

	@staticmethod
	def find_collection(bw_commander:BitwardenCommander,search_text:str):
		"""
		used to find a single bare collection (not attached to an organization, and can't really be cached)
		"""
		find_info_cmd = ['list','collections']
		find_info_res = bw_commander.find_object_info(
			find_info_cmd,search_text)
		# create an actual object for this
		found_obj = BitwardenCollection(find_info_res['id'])
		# precache since we have it already
		found_obj.info_cache = find_info_res
		return found_obj

class BitwardenOrganization(BitwardenObject):

	def __init__(self,bw_commander:BitwardenCommander,bw_id):
		super().__init__(bw_commander,bw_id)

		self.collections_cache = {}

	def __repr__(self):
		return f"Bitwarden organization, id = {self.bw_id}. {len(self.collections_cache)} collections cached."

	def get_info_from_bw(self):
		"""
		command is `get organization <id>`
		"""
		return dict(json.loads(
			self.bw_commander.exe_bw_command(
				['get','organization',self.bw_id])[0]))

	def find_collection(self, search_text:str):
		"""
		similar to finding items within a collection

		command is `list org-collections --organizationid <id> --search <search_text>`
		search_text is a partial serach, so 'est' will match an object called 'Test'
		"""
		if search_text in self.collections_cache:
			return self.collections_cache[search_text]
		else:
			find_info_cmd = ['list','collections','--organizationid',self.bw_id]
			find_info_res = self.bw_commander.find_object_info(find_info_cmd,search_text)
			# create an actual object for this
			found_obj = BitwardenCollection(self.bw_commander,find_info_res['id'])
			# precache since we have it already
			found_obj.info_cache = find_info_res
			# add to our cache
			self.collections_cache.update({search_text:found_obj})
			# return that
			return found_obj

	def sync(self):
		super().sync()
		self.collections_cache = {}

	@staticmethod
	def find_organization(bw_commander: BitwardenCommander,search_text:str):
		"""
		used to find a single bare organization
		"""
		find_info_cmd = ['list','organizations']
		find_info_res = bw_commander.find_object_info(
			find_info_cmd,search_text)
		# create an actual object for this
		found_obj = BitwardenOrganization(bw_commander,find_info_res['id'])
		# precache since we have it already
		found_obj.info_cache = find_info_res
		return found_obj