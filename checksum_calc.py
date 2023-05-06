"""
contains all checksum calculation functions
"""

import hashlib
from os import listdir
from os.path import isfile, isdir
from pathlib import Path

def add_file_to_hash_obj(path_to_file, hash_obj, block_size):
	"""
	add a file to the given hash object
	"""
	with open(path_to_file, 'rb') as f:
		this_block = f.read(block_size)
		while b'' != this_block:
			hash_obj.update(this_block)
			this_block = f.read(block_size)
			
def get_all_files_in_dir(path_to_dir, known_files=[]):
	"""
	get all the *file* paths in the given dir
	"""
	path_to_dir = Path(path_to_dir)
	# get all the files in this directory, immediately
	this_dir_contents = [path_to_dir / path for path in listdir(path_to_dir)]
	# get all the files in those paths which are dirs
	for path in this_dir_contents:
		new_files = []
		if isdir(path):
			# recursive call
			new_files = get_all_files_in_dir(path)
		elif isfile(path):
			# already a file, just add it
			new_files = [path]
		else:
			# no idea what to do with this
			print("WARNING: unknown path end result: {}".format(path)) #TODO log instead
		
		known_files += new_files
	
	return known_files

def md5_dirs(paths_to_dirs, block_size=1024):
	#TODO this is slow as hell but it works fine enough for now
	"""
	calculate the md5 of an entire directory, file contents only
	"""
	# create the hash object that will hold all the things
	hash_obj = hashlib.new('md5')
	# for all the directories...
	for path_to_dir in paths_to_dirs:
		path_to_dir = Path(path_to_dir)
		# get all the file paths in this dir
		paths = get_all_files_in_dir(path_to_dir)
		# mash all the checksums together
		for path in paths:
			add_file_to_hash_obj(path, hash_obj, block_size)
	
	return hash_obj.hexdigest()

def get_dirs_checksum_mismatch(paths_to_dirs, path_to_old_checksum_file, block_size=1024):
	"""
	determine if the current checksum is the same as it used to be
	"""
	# get the old checksum
	old_check = ""
	if not isfile(path_to_old_checksum_file):
		#TODO log instead
		print("old-checksum file does not exist. mismatch by default")
	else:
		with open(path_to_old_checksum_file, 'r') as f:
			old_check = f.readline().replace('\n','')
	# get the current checksum
	current_check = md5_dirs(paths_to_dirs, block_size)
	return (old_check == current_check), current_check

def md5_single_file(path_to_file,block_size=1024):
	hash_obj = hashlib.new('md5')
	add_file_to_hash_obj(path_to_file,hash_obj,block_size)
	return hash_obj.hexdigest()

#TODO remove test code
# print(md5_dirs(['./test_target_dir_1','./test_target_dir_2']))
# print(md5_dirs(['./test_target_dir_1','./test_target_dir_2']))
# print(get_dirs_checksum_mismatch(['./test_target_dir_1','./test_target_dir_2'],'test_old_checksum_file'))