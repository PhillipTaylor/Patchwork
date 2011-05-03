#!/usr/bin/env python

import sys
import os.path
import shutil
import traceback
import fnmatch

VERSION = "0.1 (alpha)"
PATCHWORK_FOLDER_NAME = 'patches'
TEMP_FILE = PATCHWORK_FOLDER_NAME + '/patchwork_tmp_file'

PATCHWORK_ROOT = None
PATCHES = []

# patch names are filenames. (with .patchwork on the end)
# disallowed patch names are: 'all' and 'END' or things that can't go in filenames

class Patch():
	
	def __init__(self, patch_name, is_applied, dependencies, patch_desc):

		for illegal_symbol in [ '\\', '/', '*', '.', '?', '"' ]:
			if illegal_symbol in patch_name:
				raise Exception('Invalid patch name')

		self.patch_name = patch_name
		self.is_applied = is_applied
		self.dependencies = dependencies
		self.patch_desc = patch_desc

	@classmethod
	def load_from_file(module, filename):

		patch_file_data = open(filename, 'r')

		# format of the file is:
		# line     1: PATCHNAME: xxxx
		# line     2: "DEPENDENCIES:"
		# line   3-X: PATCHNAME of dependency
		# line     X: END_DEPENDENCIES
		# line X-EOF: DESCRIPTION put in by user

		line1 = patch_file_data.readline()

		if line1 is not None and line1.startswith('PATCHNAME: '):
			patch_name = line1[11:-1]
		else:
			print_err_and_exit('Corrupted patchfile: line 1:%s' % patch_desc_file)

		line2 = patch_file_data.readline()
		if line2 is not None and line2 == 'APPLIED: ON\n':
			patch_applied = True
		elif line2 is not None and line2 == 'APPLIED: OFF\n':
			patch_applied = False
		else:
			print_err_and_exit('Corrupted patchfile: line 2:%s' % patch_desc_file)

		line3 = patch_file_data.readline()
		if line3 is None or not line3 == 'DEPENDENCIES:\n':
			print_err_and_exit('Corrupted patchfile: line 3:%s' % patch_desc_file)

		dependencies = []

		while True:
			dep_name = patch_file_data.readline()

			if dep_name == 'END\n':
				break
			else:
				dependencies.append(dep_name[:-1])

		patch_description = patch_file_data.read()

		patch_file_data.close()

		p = Patch(
			patch_name,
			patch_applied,
			dependencies,
			patch_description
		)
		
		return p
	
	def save(self):
		# write the description out.

		outfile = os.path.join(
			PATCHWORK_FOLDER_NAME,
			self.patch_name + '.patchwork'
		)

		f = open(outfile, 'w')
		f.write('PATCHNAME: %s\n' % self.patch_name)

		applied = 'ON' if self.is_applied else 'OFF'

		f.write('APPLIED: %s\n' % applied)
		f.write('DEPENDENCIES:\n')
		for dep in self.dependencies:
			f.write(dep + '\n')
		f.write('END\n')
		for l in self.patch_desc.split('\n'):
			if not l.startswith('#'):
				f.write(l + '\n')
		f.close()

def patchwork_init():
	if PATCHWORK_ROOT is not None:
		print_err_and_exit('patchwork has already been initialised')

	try:
		os.mkdir(PATCHWORK_FOLDER_NAME)

	except OSError, e:
		print_err_and_exit('could not init patchwork. %s' % e)

def move_to_patchwork_root():
	global PATCHWORK_ROOT

	print "moving to patchwork root"
	orig_cwd = os.getcwd()

	print orig_cwd

	while True:
		if os.path.isdir(PATCHWORK_FOLDER_NAME):
			PATCHWORK_ROOT = os.getcwd()
			break

		# root directory on *nix systems.
		# the "give up" claus
		# TODO add support for windows.
		if os.getcwd() == '/': 
			break

		os.chdir(os.pardir)
	
	if PATCHWORK_ROOT is None:
		# reset to original working directory
		os.chdir(orig_cwd)
	
def load_patches():
	global PATCHES

	print "loading..."
	patches_dir = os.path.join(PATCHWORK_ROOT, PATCHWORK_FOLDER_NAME)

	for patch_file in os.listdir(patches_dir):
		if not fnmatch.fnmatch(patch_file, '*.patchwork'):
			continue
	
		try:

			patch_desc_file = os.path.join(patches_dir, patch_file)
			patch = Patch.load_from_file(patch_desc_file)
			PATCHES.append(patch)

		except (ValueError, IOError), e:
			print_err_and_exit('Corrupted patchfile: %s', patch_desc_file)

# args expected to be list of files to take
# a snapshot of, or empty list if everything
def make_snapshot(args, force=False):

	snapshot_dir = os.path.join(PATCHWORK_ROOT, PATCHWORK_FOLDER_NAME, 'snapshot')

	if os.path.exists(snapshot_dir):
		if force:
			shutil.rmtree(os.path.join(PATCHWORK_ROOT, PATCHWORK_FOLDER_NAME, 'snapshot'))
		else:
			print_err_and_exit(
			"""snapshot already exists. use 'patchwork revert' to undo those changes.
alernatively use 'patchwork tag' to store this as a patch. Then changes
from here are considered to be depended on the work done so far.
			""")

	os.mkdir(snapshot_dir)

	if len(args) == 0:
		copy_dir(PATCHWORK_ROOT, snapshot_dir, exclude_list=[ PATCHWORK_FOLDER_NAME ])
	else:
		# valid all args up front.
		for file in args:
			if not os.path.exists(file):
				print_err_and_exit("file doesn't exist: %s" % file)

		for file in args:
			shutil.copyfile(file, snapshot_dir)

def print_diff(args):
	print get_diff(args)

def get_diff(args, reverse=False):

	print "here"
	dst_dir = os.path.join(PATCHWORK_ROOT, PATCHWORK_FOLDER_NAME, 'snapshot')

	if reverse:
		diff_cmd = 'diff -uN "%(root)s" "%(pw_dir)s/snapshot" --exclude="%(pw_dir)s"' % {
			'root'   : PATCHWORK_ROOT,
			'pw_dir' : PATCHWORK_FOLDER_NAME
		}
	else:
		diff_cmd = 'diff -uN "%(pw_dir)s/snapshot" "%(root)s" --exclude="%(pw_dir)s"' % {
			'root'   : PATCHWORK_ROOT,
			'pw_dir' : PATCHWORK_FOLDER_NAME
		}

	f = os.popen(diff_cmd)
	diff = f.read()
	return diff

def perform_revert(args):

	diff = get_diff(args, reverse=True)

	# write the actual patch out.
	f = open(TEMP_FILE, 'w')
	f.write(diff)
	f.close()

	# now revert it!
	patch_cmd = 'patch -uN -i "%s"' % TEMP_FILE

	f = os.popen(patch_cmd)
	patch_result = f.read()
	f.close()

def apply_patch(patch_name):

	patch = get_patch(patch_name)
	if patch.is_applied:
		print_err_and_exit('patch already applied')

	patch_filename = os.path.join(
		PATCHWORK_ROOT,
		PATCHWORK_FOLDER_NAME,
		patch_name + '.diff'
	)
	
	patch_cmd = 'patch -u -i "%s"' % patch_filename

	f = os.popen(patch_cmd)
	patch_result = f.read()
	f.close()
		
	patch.is_applied = True
	patch.save()

	# update the snapshot.
	make_snapshot([], force=True)

def remove_patch(patch_name):

	if patch_name == 'all':

		# turns off patches in the correct order...

		patches_on = [ p for p in PATCHES if p.is_applied ]
		patch_names = [ p.patch_name for p in patches_on ]
		switch_off_order = []

		while len(patches_on) > 0:

			change_made = False

			for p in patches_on:
				if len([ dep for dep in p.dependencies in patch_names ]) == 0:
					switch_off_order.append(p)
					patch_names.remove(p.patch_name)
					change_made = True

			if not change_made:
				print_err_and_exit('dependency loop?: %s', patch_names)
		
		for p in switch_off_order:
			do_remove_patch(p.patch_name)

	else:
		do_remove_patch(patch_name)

def do_remove_patch(patch_name):

		print "turning off patch: %s" % patch_name
		patch = get_patch(patch_name)

		if patch is None:
			print_err_and_exit('patch %s not found' % patch_name)

		if not patch.is_applied:
			print_err_and_exit('patch is not applied')

		patch_file = os.path.join(
			PATCHWORK_ROOT,
			PATCHWORK_FOLDER_NAME,
			patch_name + '.diff'
		)

		patch_cmd = 'patch -uR -i "%s"' % patch_file

		f = os.popen(patch_cmd)
		patch_result = f.read()
		f.close()

		patch.is_applied = False
		patch.save()
	
		# update the snapshot.
		make_snapshot([], force=True)

def tag_patch(patch_name):
	print 'creating patch %s' % patch_name

	diff = get_diff(None)

	patches_path = os.path.join(
		PATCHWORK_ROOT,
		PATCHWORK_FOLDER_NAME,
	)

	patch_name_prefix = os.path.join(
		patches_path,
		patch_name
	)

	default_msg = """
	
# Enter the description for patch %s.
# Lines beginning with a hash are ignored.
#
#
""" % patch_name

	for d in diff.split('\n'):
		default_msg += '\n#%s' % d

	# this is here so if the user entered
	# a description and the program blew up
	# (maybe some readonly permission was set)
	# they dont have to enter it again
	if not os.path.exists(TEMP_FILE):
		f = open(TEMP_FILE, 'w')
		f.write(default_msg)
		f.close()

	if 'EDITOR' in os.environ:
		editor = os.environ['EDITOR']
	else:
		editor = 'vim'

	os.system('%s "%s"' % (editor, TEMP_FILE))

	f = open(TEMP_FILE, 'r')
	desc = f.read()
	f.close()

	if desc == default_msg:
		print 'abandoned because user cancelled'
		os.remove(TEMP_FILE)
		return

	# create patch
	patch_obj = Patch(
		patch_name,
		True,
		get_dependencies(),
		desc
	)

	patch_obj.save()

	# write the actual patch out.
	f = open(patch_name_prefix + '.diff', 'w')

	f.write(diff)
	f.close()

	# apply the patch to the snapshot as well
	make_snapshot([], force=True)

	# remove at end, so if it fails they can
	# recover their description again
	os.remove(TEMP_FILE)

def get_dependencies():
	return [ p.patch_name for p in PATCHES if p.is_applied ]

def delete_patch(patch_name):
	global PATCHES

	patch = get_patch(patch_name)
	if patch is None:
		print_err_and_exit('patch %s not found')

	PATCHES.remove(patch)

	prefix = os.path.join(
		PATCHWORK_ROOT,
		PATCHWORK_FOLDER_NAME,
		patch_name
	)

	os.remove(prefix + '.diff')
	os.remove(prefix + '.patchwork')


def print_status():
	applied_patches = [ p for p in PATCHES if p.is_applied ]

	print "There are %s patches in this project." % len(PATCHES)

	if len(applied_patches) > 0:
		for p in applied_patches:
			print 'ON  %s' % p.patch_name
	else:
		print "No patches are on"

def print_describe(patch_name):
	print 'describing %s' % patch_name

	patch = get_patch(patch_name)

	if patch is None:
		print_err_and_exit('patch %s not found' % patch_name)

	print "Patch Name: %s" % patch.patch_name
	print "Applied:    %s" % patch.is_applied

	if len(patch.dependencies) > 0:
		print "Dependency List: "
		for d in patch.dependencies:
			print "\t%s" % d
	else:
		print "No dependencies"
	
	print "Description: %s" % patch.patch_desc

def show_all_patches():

	if len(PATCHES) == 0:
		print "0 patches in this project"

	applied_patches = [ p for p in PATCHES if p.is_applied ]
	unapplied_patches = [ p for p in PATCHES if not p.is_applied ]

	for p in applied_patches:
		print 'ON  %s' % p.patch_name
	
	for p in unapplied_patches:
		print 'OFF %s' % p.patch_name

def export_patch(patch_name):
	# TODO: export a patch (basically print
	# the contents of the .patch file to screen)
	pass

def import_patch(patch_file):
	# TODO: import a patch. Basically apply the
	# patch to the current tree and invoke 'tag'
	pass

def get_patch(patch_name):

	for p in PATCHES:
		if p.patch_name == patch_name:
			return p
	
	return None

def copy_dir(src_dir, dst_dir, exclude_list=[]):

	for f in os.listdir(src_dir):

		if f in exclude_list:
			continue

		if os.path.isdir(f):
			os.mkdir(os.path.join(dst_dir, f))

			applicable_exclude_list = [ x[len(f)+1:] for x in exclude_list if x.startswith(f + '/') ]

			copy_dir(
				os.path.join(src_dir, f),
				os.path.join(dst_dir, f),
				applicable_exclude_list
			)
		else:
			shutil.copyfile(f, os.path.join(dst_dir, f))

def print_usage():
	print 'patchwork <cmd> <optional arguments>'
	print 'commands can be from:'
	print '  -h / help                            prints this message'
	print '  -v / version                         prints the version'
	print '  init                                 start using patchwork with this directory as the base.'
	print '  snapshot                             create a snapshot of the current base code so a change can be isolated a patch.'
	print '  diff                                 show the differences between this code and the last snapshot'
	print '  revert                               abort the changes made since the last snapshot'
	print '  on <patch_name>                      apply a patch (and dependencies to the working direcory). For debugging or to build upon it'
	print "  off <patch_name>                     remove a patch from the working directory. use 'off all' to return to the base state"
	print '  tag <patch_name> (-d <description>)  save your changes as a patch. optional description. If you do not provide it, it will be shown to you.'
	print '  delete <patch_name>                  delete a patch perminently from patchwork'
	print '  status                               show the status of the working directory'
	print '  describe <patch_name>                show the description of the patch'
	print '  list-all                             list all the patches for a given system'

	print '\nFor more information read the documentation online at http://philliptaylor.net'

def print_version():
	print """
	Snapshot %s
	Copyright (C) 2011, Phillip Taylor.
	This is free software; see the source for copying conditions.
	There is NO warranty; not even for MERCHANTABILITY or FITNESS FOR A
	PARTICULAR PURPOSE
	""" % VERSION

def print_err_and_exit(err_msg):
	print 'Error: %s' % err_msg
	sys.exit(1)

def run(sys_args):

	try:

		if len(sys_args) < 2:
			print_usage()
		else:

			cmd = sys_args[1]

			# dont pass debug flag around
			args = sys_args[2:]
			if '-d' in args:
				args.remove('-d')

			move_to_patchwork_root()

			if cmd != 'init' and PATCHWORK_ROOT is None:
				print_err_and_exit("patchwork has not been configured. Run 'patchwork init'")
			elif cmd != 'init':
				load_patches()

			if cmd in ('-h', '--help'):
				print_usage()
			elif cmd in ('-v', '--version'):
				print_version()
			elif cmd == 'init':
				patchwork_init()
			elif cmd == 'snapshot':
				make_snapshot(args)
			elif cmd == 'diff':
				print_diff(args)
			elif cmd == 'revert':
				perform_revert(args)
			elif cmd == 'on':

				if len(args) == 0:
					print_err_and_exit('need argument <patch_name>')
				else:
					apply_patch(args[0])

			elif cmd == 'off':

				if len(args) == 0:
					print_err_and_exit('need argument <patch_name> or "all"')
				else:
					remove_patch(args[0])

			elif cmd == 'tag':

				if len(args) == 0:
					print_err_and_exit('need argument <patch_name>')
				else:
					tag_patch(args[0])

			elif cmd == 'delete':
				
				if len(sys_args) == 0:
					print_err_and_exit('need argument <patch_name>')
				else:
					tag_patch(args[0])
				
			elif cmd == 'status':
				print_status()

			elif cmd == 'describe':
				print_describe(args[0])

			elif cmd == 'list-all':
				show_all_patches()

			else:
				print_usage()
				print_err_and_exit('unrecognised command: %s' % cmd)

	except Exception, e:
		print 'Unexpected Error: %s' % str(e)
		if '-d' in sys_args:
			traceback.print_exc()


if __name__=='__main__':
	run(sys.argv)
