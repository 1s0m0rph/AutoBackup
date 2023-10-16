"""
manage various config/config contexts

configuration for the autobackup script is an INI file with the following fields/sections:

TARGETS:
	TargetDirectories = <json formatted list of paths>
CHECKSUMS:
	MostRecentChecksumFile = <path>
	ChecksumBlockSize = <int, number of bytes>
BITWARDEN:
	PathToBitwardenExe = <path>
	PathToPasswordFile = <path>
	TargetOrganizationName = <string>
	TargetCollectionName = <string>
FILE_HANDLING:
	TmpDirLocation: <path>
MISC:
	PerformRedownloadCheck: <bool>
"""

from configparser import ConfigParser
from pathlib import Path
import json

class AutobakConfig:

	def __init__(self,path_to_config_file:Path):
		cfg_parser = ConfigParser()
		cfg_parser.read(path_to_config_file)

		# TARGETS
		self.target_dirs = json.loads(cfg_parser['TARGETS'].get('TargetDirectories'))
		# CHECKSUMS
		self.most_recent_checksum_file = Path(cfg_parser['CHECKSUMS'].get('MostRecentChecksumFile',fallback="./most_recent_checksum.txt"))
		self.checksum_block_size = cfg_parser['CHECKSUMS'].getint('ChecksumBlockSize',fallback=1024)
		# BITWARDEN
		self.path_to_bw_exe = Path(cfg_parser['BITWARDEN'].get('PathToBitwardenExe'))
		self.path_to_pw_file = Path(cfg_parser['BITWARDEN'].get('PathToPasswordFile'))
		self.target_org = cfg_parser['BITWARDEN'].get('TargetOrganizationName')
		self.target_coll = cfg_parser['BITWARDEN'].get('TargetCollectionName')
		# FILE_HANDLING
		self.path_to_tmp_dir = Path(cfg_parser['FILE_HANDLING'].get('TmpDirLocation',fallback='./tmp'))
		# MISC
		self.perform_redownload_check = cfg_parser['MISC'].getboolean('PerformRedownloadCheck',fallback=True)
		self.additional_prefix = cfg_parser['MISC'].get("AdditionalPrefix",fallback="")
		# add an underscore if additional prefix was set
		if (len(self.additional_prefix) != 0) and (self.additional_prefix[-1] != '_'):
			self.additional_prefix += "_"
		# LOGGING
		self.path_to_log_file = Path(cfg_parser['LOGGING'].get('PathToLogFile', fallback='./autobak.log'))
		self.log_level = cfg_parser['LOGGING'].get('LogLevel', fallback='CRITICAL')

	def print_info(self):
		pstr = f"""
		target-dirs: {self.target_dirs}
		most recent checksum file: {self.most_recent_checksum_file}
		checksum block size: {self.checksum_block_size}
		path to bitwarden executable: {self.path_to_bw_exe}
		path to password file: {self.path_to_pw_file}
		target org: {self.target_org}
		target collection: {self.target_coll}
		path to tmp dir: {self.path_to_tmp_dir}
		perform redownload check: {self.perform_redownload_check}
		additional prefix: {self.additional_prefix}
		"""
		print(pstr)
