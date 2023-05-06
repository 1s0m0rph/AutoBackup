from unittest import TestCase
from unittest.mock import patch,call
from bitwarden_manager import *


class TestBitwardenCommander(TestCase):

	@patch("bitwarden_manager.SubprocessCommander")
	def setUp(self,mock_sbp_cmd_cons):
		self.mock_sbp_cmd = mock_sbp_cmd_cons.return_value
		self.path_to_bw_executable = Path("example/path/to/executable/bw")
		self.path_to_pw_file = Path("example/path/to/password/file")

		self.test_obj = BitwardenCommander(self.mock_sbp_cmd,self.path_to_bw_executable,self.path_to_pw_file)

	@patch("bitwarden_manager.BitwardenObject")
	@patch("bitwarden_manager.BitwardenObject")
	def test_register_sync_observer(self,mock_bw_obj_1,mock_bw_obj_2):
		# silly test -- most of the observer test is delegated to sync-notify
		self.test_obj.register_sync_observer(mock_bw_obj_1)
		self.assertIn(mock_bw_obj_1,self.test_obj.sync_observers)
		self.test_obj.register_sync_observer(mock_bw_obj_2)
		self.assertIn(mock_bw_obj_2,self.test_obj.sync_observers)
		# shouldn't add something more than once
		self.test_obj.register_sync_observer(mock_bw_obj_1)
		self.assertIn(mock_bw_obj_1,self.test_obj.sync_observers)
		self.assertEqual(2,len(self.test_obj.sync_observers))

	@patch("bitwarden_manager.BitwardenObject")
	@patch("bitwarden_manager.BitwardenObject")
	def test_perform_sync_notify(self,mock_bw_obj_1,mock_bw_obj_2):
		# add both as observers
		self.test_obj.register_sync_observer(mock_bw_obj_1)
		self.test_obj.register_sync_observer(mock_bw_obj_2)
		# verify that sync() is called on both observers when we do a notify
		self.test_obj.perform_sync_notify()
		# apparently these have to go after the actual call... gtest you bastard
		mock_bw_obj_1.sync.assert_called_once()
		mock_bw_obj_2.sync.assert_called_once()

	def test_sync(self):
		# set up session key
		self.test_obj.session_key = "this_is_a_session_key"
		# call the fn
		with patch.object(self.test_obj,'perform_sync_notify') as mock_sync_notify:
			self.test_obj.sync()
			mock_sync_notify.assert_called_once()
		# verify we got the right command
		expected_command = [str(self.path_to_bw_executable),'sync','--session','this_is_a_session_key']
		self.mock_sbp_cmd.exe_wait_sbp_command.assert_called_once_with(expected_command)

	def test_lock(self):
		# set up session key
		self.test_obj.session_key = "this_is_a_session_key"
		# call the fn
		self.test_obj.lock()
		# verify we got the right command
		expected_command = [str(self.path_to_bw_executable),'lock','--session','this_is_a_session_key']
		self.mock_sbp_cmd.exe_wait_sbp_command.assert_called_once_with(expected_command)
		# verify our session key got reset
		self.assertIsNone(self.test_obj.session_key)

	@patch("os.path.isfile")
	def test_unlock_password_file_does_not_exist(self,mock_isfile):
		# do a test with the file just straight up not there
		mock_isfile.return_value = False
		with self.assertRaises(FileNotFoundError):
			self.test_obj.unlock()

		# make sure no commands were executed
		self.mock_sbp_cmd.exe_wait_sbp_command.assert_not_called()

	@patch("os.path.isfile")
	def test_unlock_invalid_password(self,mock_isfile):
		# do a test with the session key not set (shouldn't be set by default)
		# set up the isfile injection to say there is a file
		mock_isfile.return_value = True
		# set up the subprocess commander to return something errorful (invalid password in this case)
		self.mock_sbp_cmd.exe_wait_sbp_command.return_value = ["Invalid master password."]
		with self.assertRaises(InvalidMasterPasswordError):
			self.test_obj.unlock()
		# format the expected command
		expected_cmd = [str(self.path_to_bw_executable),'unlock','--passwordfile',str(self.path_to_pw_file),'--raw']
		self.mock_sbp_cmd.exe_wait_sbp_command.assert_called_once_with(expected_cmd)
		# make sure the session key didn't get set
		self.assertIsNone(self.test_obj.session_key)

	@patch("os.path.isfile")
	def test_unlock_good_password(self,mock_isfile):
		# now the same thing with a good password AND a good file
		mock_isfile.return_value = True
		self.mock_sbp_cmd.exe_wait_sbp_command.return_value = ["this_is_a_session_key"]
		self.test_obj.unlock()
		# make sure the session key got set correctly
		self.assertEqual(self.test_obj.session_key,"this_is_a_session_key")
		# make sure we did the right commands
		expected_unlock_cmd = call(
			[str(self.path_to_bw_executable),'unlock','--passwordfile',str(self.path_to_pw_file),'--raw'])
		expected_sync_cmd = call([str(self.path_to_bw_executable),'sync','--session','this_is_a_session_key'])
		self.mock_sbp_cmd.exe_wait_sbp_command.assert_has_calls([expected_unlock_cmd,expected_sync_cmd])

	# now that we've done the test with the session key not set, it's already set, so make sure nothing really happens when we call again
	# self.test_obj.unlock()

	def set_session_key_side_effect(self,set_to):
		def side_effect():
			self.test_obj.session_key = set_to

		return side_effect

	def test_exe_bw_command_no_key_set_unlocks_first(self):
		self.test_obj.session_key = None
		with patch.object(self.test_obj,'unlock') as mock_unlock_cmd:
			mock_unlock_cmd.side_effect = self.set_session_key_side_effect('this_is_a_session_key')
			with patch.object(self.test_obj,'perform_sync_notify') as mock_sync_notify:
				self.test_obj.exe_bw_command(['test_cmd'])
				mock_unlock_cmd.assert_called_once()
				mock_sync_notify.assert_not_called()

		# verify we got the rest of it more or less as expected too
		expected_cmd = [str(self.path_to_bw_executable),'test_cmd','--session','this_is_a_session_key']
		self.mock_sbp_cmd.exe_wait_sbp_command.assert_called_once_with(expected_cmd)

	def test_exe_bw_command_key_set_does_not_unlock(self):
		self.test_obj.session_key = 'this_is_a_session_key'
		with patch.object(self.test_obj,'unlock') as mock_unlock_cmd:
			mock_unlock_cmd.side_effect = self.set_session_key_side_effect('this_is_a_new_session_key')
			with patch.object(self.test_obj,'perform_sync_notify') as mock_sync_notify:
				self.test_obj.exe_bw_command(['test_cmd'])
				mock_unlock_cmd.assert_not_called()
				mock_sync_notify.assert_not_called()

		# verify we got the rest of it more or less as expected too
		expected_cmd = [str(self.path_to_bw_executable),'test_cmd','--session','this_is_a_session_key']
		self.mock_sbp_cmd.exe_wait_sbp_command.assert_called_once_with(expected_cmd)

	def test_exe_bw_command_sync_cmd_notifies(self):
		self.test_obj.session_key = 'this_is_a_session_key'
		with patch.object(self.test_obj,'unlock') as mock_unlock_cmd:
			mock_unlock_cmd.side_effect = self.set_session_key_side_effect('this_is_a_new_session_key')
			with patch.object(self.test_obj,'perform_sync_notify') as mock_sync_notify:
				self.test_obj.exe_bw_command(['sync'])
				mock_unlock_cmd.assert_not_called()
				mock_sync_notify.assert_called_once()

		# verify we got the rest of it more or less as expected too
		expected_cmd = [str(self.path_to_bw_executable),'sync','--session','this_is_a_session_key']
		self.mock_sbp_cmd.exe_wait_sbp_command.assert_called_once_with(expected_cmd)

	def test_find_object_info_not_found_raises_err(self):
		with patch.object(self.test_obj,'exe_bw_command') as mock_exe_cmd:
			mock_exe_cmd.return_value = ["Not found."]
			with self.assertRaises(BitwardenItemNotFoundError):
				self.test_obj.find_object_info(['list','items'],'a_search_term')

	def test_find_object_info_empty_raises_err(self):
		with patch.object(self.test_obj,'exe_bw_command') as mock_exe_cmd:
			mock_exe_cmd.return_value = ["[]"]
			with self.assertRaises(BitwardenItemNotFoundError):
				self.test_obj.find_object_info(['list','items'],'a_search_term')

	def test_find_object_info_no_exact_match_returns_first(self):
		with patch.object(self.test_obj,'exe_bw_command') as mock_exe_cmd:
			mock_exe_cmd.return_value = [
				"""[{"object":"item","id":"an-id","name":"Test name 2"},{"object":"item","id":"an-id","name":"Test name 1"}]"""]
			actual_res = self.test_obj.find_object_info(['list','items'],'Test name')
			expected_res = {"object": "item","id": "an-id","name": "Test name 2"}
			self.assertDictEqual(actual_res,expected_res)

	def test_find_object_info_exact_match_returns_exact_match(self):
		with patch.object(self.test_obj,'exe_bw_command') as mock_exe_cmd:
			mock_exe_cmd.return_value = [
				"""[{"object":"item","id":"an-id","name":"Test name 2"},{"object":"item","id":"an-id","name":"Test name 1"}]"""]
			actual_res = self.test_obj.find_object_info(['list','items'],'Test name 1')
			expected_res = {"object": "item","id": "an-id","name": "Test name 1"}
			self.assertDictEqual(actual_res,expected_res)


class TestCacheableBitwardenObject(TestCase):

	@patch("bitwarden_manager.BitwardenCommander")
	def test_init(self,mock_commander):
		# init an object
		test_obj = CacheableBitwardenObject(mock_commander)
		# make sure we self-registered
		mock_commander.register_sync_observer.assert_called_once_with(test_obj)


class TestBitwardenObject(TestCase):

	@patch("bitwarden_manager.BitwardenCommander")
	def setUp(self,mock_commander):
		self.mock_commander = mock_commander
		self.obj_id = "test-obj-id"

		self.test_obj = BitwardenObject(self.mock_commander,self.obj_id)

	def test_get_info_no_existing_cache(self):
		self.assertIsNone(self.test_obj.info_cache)
		with patch.object(self.test_obj,"get_info_from_bw") as mock_get_info_from_bw:
			mock_get_info_from_bw.return_value = {'field1': 'value1'}
			ret_info = self.test_obj.get_info()
			# make sure we called the fn as expected
			mock_get_info_from_bw.assert_called_once()
			# make sure the ret value is what we expected
			self.assertDictEqual(ret_info,{'field1': 'value1'})
			# make sure we cached the right thing
			self.assertDictEqual(self.test_obj.info_cache,{'field1': 'value1'})

	def test_get_info_with_existing_cache(self):
		self.assertIsNone(self.test_obj.info_cache)
		self.test_obj.info_cache = {'asdf': 'fdsa'}
		with patch.object(self.test_obj,"get_info_from_bw") as mock_get_info_from_bw:
			mock_get_info_from_bw.return_value = {'field1': 'value1'}
			ret_info = self.test_obj.get_info()
			# make sure we didn't call the fn
			mock_get_info_from_bw.assert_not_called()
			# make sure the ret value is what we expected
			self.assertDictEqual(ret_info,{'asdf': 'fdsa'})

	def test_sync(self):
		# super simple test just make sure the cache is cleared

		# once with nothing cached
		self.assertIsNone(self.test_obj.info_cache)
		self.test_obj.sync()
		self.assertIsNone(self.test_obj.info_cache)

		# once with something cached
		self.test_obj.info_cache = {'asdf','fdsa'}
		self.test_obj.sync()
		self.assertIsNone(self.test_obj.info_cache)

