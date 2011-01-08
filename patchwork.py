#!/usr/bin/env python

import sys
import os.path
import shutil

VERSION = "0.1 (alpha)"
PATCHWORK_FOLDER_NAME = '.patchwork'

PATCHWORK_ROOT = None
PATCHES = []

# disallowed patch names are: 'all' and 'END' or things that can't go in filenames

class Patch():
	
	def __init__(self, patch_name, is_applied, dependencies, patch_desc):
		self.patch_name = patch_name
		self.is_applied = is_applied
		self.dependencies = dependencies
		self.patch_desc = patch_desc

def patchwork_init():
	if PATCHWORK_ROOT is not None:
		print_err_and_exit('patchwork has already been initialised')

	try:
		os.mkdir(PATCHWORK_FOLDER_NAME)
		os.mkdir(PATCHWORK_FOLDER_NAME + '/patches')
	
	except OSError, e:
		print_err_and_exit('could not init patchwork. %s' % e)

def move_to_patchwork_root():
	global PATCHWORK_ROOT

	orig_cwd = os.getcwd()

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

	patches_descriptors_dir = os.path.join(PATCHWORK_ROOT, PATCHWORK_FOLDER_NAME, 'patches')

	for patch_file in os.listdir(patches_descriptors_dir):
		
		patch_desc_file = os.path.join(patches_descriptors_dir, patch_file)
		patch_file_data = open(patch_desc_file, 'r')

		# format of the file is:
		# line     1: PATCHNAME: xxxx
		# line     2: "DEPENDENCIES:"
		# line   3-X: PATCHNAME of dependency
		# line     X: END_DEPENDENCIES
		# line X-EOF: DESCRIPTION put in by user

		line1 = patch_file_data.readline()

		if line1 is None or not line1.startswith('PATCHNAME: '):
			print_err_and_exit('Corrupted patchfile: line 1:%s' % patch_desc_file)
		else:
			patch_name = line1[11:-1]

		line2 = patch_file_data.readline()
		if line2 is None or not line2 not in ('APPLIED: ON\n', 'APPLIED OFF\n'):
			print_err_and_exit('Corrupted patchfile: line 2:%s' % patch_desc_file)
		elif line2 == 'APPLIED_ON\n':
			patch_applied = True
		else:
			patch_applied = False

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
		
		PATCHES.append(p)

# args expected to be list of files to take
# a snapshot of, or empty list if everything
def make_snapshot(args):

	snapshot_dir = os.path.join(PATCHWORK_ROOT, PATCHWORK_FOLDER_NAME, 'snapshot')

	if os.path.exists(snapshot_dir):
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

def print_diff():
	print 'displaying diff'

def perform_revert():
	print 'reverting changes since last snapshot'

def apply_patch(patch_name):
	print 'appling patch %s'

def remove_patch(patch_name):
	print 'removing patch %s' % patch_name

def tag_patch(patch_name):
	print 'creating patch %s' % patch_name

def delete_patch(patch_name):
	print 'deleting patch'

def print_status():
	print 'status'

def describe(patch_name):
	print 'describing %s' % patch_name


def show_all_patches():

	applied_patches = [ p for p in PATCHES if p.is_applied ]
	unapplied_patches = [ p for p in PATCHES if not p.is_applied ]

	for p in applied_patches:
		print 'ON  %s' % p.patch_name
	
	for p in unapplied_patches:
		print 'OFF %s' % p.patch_name

def export_patch(patch_name):
	print 'export patch'

def import_patch(patch_name):
	print 'import patch'

def copy_dir(src_dir, dst_dir, exclude_list=[]):

	for f in os.listdir(src_dir):

		if f in exclude_list:
			continue

		if os.path.isdir(f):
			os.mkdir(os.path.join(dst_dir, f))

			applicable_exclude_list = [ x for x in exclude_list if x.startswith('f' + '/') ]

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
	print '  list_all                             list all the patches for a given system'

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

def run():

	if len(sys.argv) < 2:
		print_usage()
	else:

		cmd = sys.argv[1]

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
			make_snapshot(sys.argv[2:])
		elif cmd == 'diff':
			print_diff()
		elif cmd == 'revert':
			perform_revert()
		elif cmd == 'on':

			if len(sys.argv) == 2:
				print_err_and_exit('need argument <patch_name>')
			else:
				apply_patch(sys.argv[2])

		elif cmd == 'off':

			if len(sys.argv) == 2:
				print_err_and_exit('need argument <patch_name> or "all"')
			else:
				remove_patch(sys.argv[2])

		elif cmd == 'tag':

			if len(sys.argv) == 2:
				print_err_and_exit('need argument <patch_name>')
			else:
				tag_patch(sys.argv[2])

		elif cmd == 'delete':
			
			if len(sys.argv) == 2:
				print_err_and_exit('need argument <patch_name>')
			else:
				tag_patch(sys.argv[2])
			
		elif cmd == 'status':
			print_status()

		elif cmd == 'list_all':
			show_all_patches()

		else:
			print_usage()
			print_err_and_exit('unrecognised command: %s' % cmd)

if __name__=='__main__':
	run()
