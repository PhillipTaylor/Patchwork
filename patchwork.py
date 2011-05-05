#!/usr/bin/env python

import sys
import os.path
import shutil
import traceback
import fnmatch

VERSION = "0.3 (alpha)"
PATCHWORK_FOLDER_NAME = 'patches'
TEMP_FILE = PATCHWORK_FOLDER_NAME + '/patchwork_tmp_file'

PATCHWORK_ROOT = None
PATCHES = []

DEBUG = True

# patch names are filenames. (with .patchwork on the end)
# disallowed patch names are: 'all' and 'END' or things that can't go in filenames

class Patch():
	
	def __init__(self, patch_name, is_applied, dependencies, patch_desc):

		for illegal_symbol in [ '\\', '/', '*', '.', '?', '"' ]:
			if illegal_symbol in patch_name:
				raise Exception('Invalid patch name: %s' % patch_name)

		for illegal_name in [ 'END', 'all' ]:
			if illegal_name == patch_name:
				raise Exception('Invalid patch name: %s' % patch_name)

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
		
		move_to_patchwork_root() # should go nowhere, just set variable.
		update_snapshot()

	except OSError, e:
		print_err_and_exit('could not init patchwork. %s' % e)

def load_patches():
	global PATCHES

	for patch_file in os.listdir(PATCHWORK_FOLDER_NAME):
		if not fnmatch.fnmatch(patch_file, '*.patchwork'):
			continue
	
		try:

			patch_desc_file = os.path.join(PATCHWORK_FOLDER_NAME, patch_file)
			patch = Patch.load_from_file(patch_desc_file)
			PATCHES.append(patch)

		except (ValueError, IOError), e:
			print_err_and_exit('Corrupted patchfile: %s', patch_desc_file)

def print_diff():
	changes = get_diff()

	if changes != '':
		print get_diff()

def perform_revert():

	# write the current diff state out
	diff = get_diff(reverse=True)

	f = open(TEMP_FILE, 'w')
	f.write(diff)
	f.close()

	# then reverse it
	do_apply_patch(TEMP_FILE)
	os.remove(TEMP_FILE)

def apply_patch(patch_name, skip_applied=False):

	if patch_name.upper() == 'ALL':
		for p in PATCHES:
			apply_patch(
				p.patch_name,
				skip_applied=True
			)
		return

	patch = get_patch(patch_name)
	if patch.is_applied:
		if skip_applied:
			return
		else:
			print_err_and_exit('patch already applied')
	
	# time to switch on dependencies.
	for dependency in patch.dependencies:
		apply_patch(dependency, skip_applied=True)

	patch_filename = os.path.join(
		PATCHWORK_FOLDER_NAME,
		patch_name + '.diff'
	)

	do_apply_patch(patch_filename)

	patch.is_applied = True
	patch.save()

	update_snapshot()

def remove_patch(patch_name, skip_applied=False):

	if patch_name.upper() == 'ALL':
		for p in PATCHES:
			remove_patch(
				p.patch_name,
				skip_applied=True
			)
		return

	patch = get_patch(patch_name)
	all_applied_patches = [ p for p in PATCHES if p.is_applied ]

	# see if something is depending on our patch.
	for applied_patch in all_applied_patches:
		if patch_name in applied_patch.dependencies:
			remove_patch(
				applied_patch.patch_name,
				skip_applied=True
			)

	# can now safely remove this patch.
	patch = get_patch(patch_name)

	if patch is None:
		print_err_and_exit('patch %s not found' % patch_name)

	if not patch.is_applied:
		if skip_applied:
			return
		else:
			print_err_and_exit('patch is not applied')

	patch_file = os.path.join(
		PATCHWORK_FOLDER_NAME,
		patch_name + '.diff'
	)

	do_apply_patch(patch_file, reverse=True)

	patch.is_applied = False
	patch.save()

	update_snapshot()

def tag_patch(patch_name):

	diff = get_diff()

	patch_name_prefix = os.path.join(
		PATCHWORK_FOLDER_NAME,
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
		os.remove(TEMP_FILE)
		print_err_and_exit('abandoned because user cancelled')

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
	update_snapshot()

	# remove at end, so if it fails they can
	# recover their description again
	os.remove(TEMP_FILE)

def delete_patch(patch_name):
	global PATCHES

	patch = get_patch(patch_name)
	if patch is None:
		print_err_and_exit('patch %s not found' % patch_name)
	elif patch.is_applied:
		print_err_and_exit('cannot delete a patch which is currently applied')
	
	# ensure no patches depend on this patch (recursively!)
	dependencies = show_dependencies_for_patch(patch_name)
	if len(dependencies) > 0:
		print_err_and_exit(
			'dependencies must be deleted before this patch can be deleted'
		)

	PATCHES.remove(patch)

	prefix = os.path.join(
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

def list_all():

	if len(PATCHES) == 0:
		print "0 patches in this project"

	applied_patches = [ p for p in PATCHES if p.is_applied ]
	unapplied_patches = [ p for p in PATCHES if not p.is_applied ]

	for p in applied_patches:
		print 'ON  %s' % p.patch_name
	
	for p in unapplied_patches:
		print 'OFF %s' % p.patch_name

def print_usage():
	print 'patchwork <cmd> <optional arguments>'
	print 'commands can be from:'
	print '  -h / help                            prints this message'
	print '  -v / version                         prints the version'
	print '  init                                 start using patchwork with this directory as the base.'
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
	This is free software; licensed under the GPL3, see the source for copying conditions.
	There is NO warranty; not even for MERCHANTABILITY or FITNESS FOR A
	PARTICULAR PURPOSE
	""" % VERSION

# Helper functions below
# -----------------------------------------------------------------------------

def get_patch(patch_name):

	for p in PATCHES:
		if p.patch_name == patch_name:
			return p
	
	return None

def show_dependencies_for_patch(patch_name):

	depends = []

	for p in PATCHES:
		if patch_name in p.dependencies:

			depends.append(p.patch_name)

			related_patch_deps = show_dependencies_for_patch(p.patch_name)
			depends.extend(related_patch_deps)

	unique_depends = []
	for d in depends:
		if d not in unique_depends:
			unique_depends.append(d)
			print '%s -> %s' % (patch_name, d)

	return unique_depends

def get_dependencies():
	return [ p.patch_name for p in PATCHES if p.is_applied ]

def get_diff(reverse=False):

	dst_dir = os.path.join(PATCHWORK_FOLDER_NAME, 'snapshot')

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

def do_apply_patch(patch_file, reverse=False):

	if reverse:
		patch_cmd = 'patch -uR -i "%s"' % patch_file
	else:
		patch_cmd = 'patch -u -i "%s"' % patch_file

	f = os.popen(patch_cmd)
	patch_result = f.read()
	f.close()

def update_snapshot():

	snapshot_dir = os.path.join(PATCHWORK_FOLDER_NAME, 'snapshot')

	if os.path.exists(snapshot_dir):
		shutil.rmtree(os.path.join(PATCHWORK_FOLDER_NAME, 'snapshot'))
	
	os.mkdir(snapshot_dir)	
	copy_dir(PATCHWORK_ROOT, snapshot_dir, exclude_list=[ PATCHWORK_FOLDER_NAME ])

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

def print_err_and_exit(err_msg):
	print 'Error: %s' % err_msg
	sys.exit(1)


def run():
	global DEBUG

	try:

		if len(sys.argv) < 2:
			print_usage()
		else:

			# dont pass debug flag around
			if '-d' in sys.argv:
				sys.argv.remove('-d')
				DEBUG = True

			cmd = sys.argv[1]

			move_to_patchwork_root()

			if cmd != 'init' and PATCHWORK_ROOT is None:
				print_err_and_exit("patchwork has not been configured. Run 'patchwork init'")

			if cmd not in ('-h', '--help', '-v', '--version', 'init'):
				load_patches()
			
			if cmd in ('on', 'off', 'tag', 'delete', 'describe'):
				if len(sys.argv) > 2:
					patch_name = sys.argv[2]
				else:
					print_err_and_exit('need argument <patch_name>')

			if cmd in ('-h', '--help'):
				print_usage()
			elif cmd in ('-v', '--version'):
				print_version()
			elif cmd == 'init':
				patchwork_init()
			elif cmd == 'diff':
				print_diff()
			elif cmd == 'revert':
				perform_revert()
			elif cmd == 'status':
				print_status()
			elif cmd == 'list-all':
				list_all()
			elif cmd == 'on':
				apply_patch(patch_name)
			elif cmd == 'off':
				remove_patch(patch_name)
			elif cmd == 'tag':
				tag_patch(patch_name)
			elif cmd == 'delete':
				delete_patch(patch_name)
			elif cmd == 'describe':
				print_describe(patch_name)

			else:
				print_usage()
				print_err_and_exit('unrecognised command: %s' % cmd)

	except Exception, e:
		print 'Unexpected Error: %s' % str(e)
		if DEBUG:
			traceback.print_exc()

if __name__=='__main__':
	run()
