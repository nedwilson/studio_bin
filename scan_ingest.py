#!/usr/bin/python

# Generic Scan ingest, version 0.1a

import ConfigParser
import os
import sys
import re
import shutil

g_ih_show_code = None
g_ih_show_root = None
g_ih_show_cfg_path = None
g_shot_regexp = None
g_seq_regexp = None
g_shot_dir = None
g_show_file_operation = None
g_skip_list = []

def usage():
	print ""
	print "scan_ingest.py PATH_TO_FOLDER"
	print ""
	print "Where PATH_TO_FOLDER is a path to a directory that contains images, color correction files, PDF files, etc."

try:
	g_ih_show_code = os.environ['IH_SHOW_CODE']
	g_ih_show_root = os.environ['IH_SHOW_ROOT']
	g_ih_show_cfg_path = os.environ['IH_SHOW_CFG_PATH']
	config = ConfigParser.ConfigParser()
	config.read(g_ih_show_cfg_path)
	g_shot_regexp = config.get(g_ih_show_code, 'shot_regexp')
	g_seq_regexp = config.get(g_ih_show_code, 'sequence_regexp')
	g_shot_dir = config.get(g_ih_show_code, 'shot_dir')
	g_show_file_operation = config.get(g_ih_show_code, 'show_file_operation')
	print "Successfully loaded show-specific config file for %s."%g_ih_show_code
except KeyError:
	pass
	

g_valid_exts = ['exr','ccc','cdl','jpg','pdf']
g_path = None

def handle_file_copy(m_srcpath):
	file_basename = os.path.basename(m_srcpath)
	shot = None
	seq = None
	file_array = file_basename.split('.')
	# skip files not in the valid extension list
	if file_array[-1] not in g_valid_exts:
		return
	matchobject = re.search(g_shot_regexp, file_basename)
	# make sure this file matches the shot pattern
	if not matchobject:
		g_skip_list.append(m_srcpath)
		return
	else:
		shot = matchobject.group(0)
		seq = re.search(g_seq_regexp, shot).group(0)

	subbed_shot_dir = g_shot_dir.replace("SHOW_ROOT", g_ih_show_root).replace("SEQUENCE", seq).replace("SHOT", shot)

	# create the shot if it doesn't exist	
	if not os.path.exists(subbed_shot_dir):
		print "Creating new shot %s."%shot
		shot_stub_dir = os.path.join(g_ih_show_root, "SHARED", "lib", "shot_stub")
		shutil.copytree(shot_stub_dir, subbed_shot_dir)

	# handle different file types
	
	if file_array[-1] == 'exr':
		dest_dir = os.path.join(subbed_shot_dir, "pix", "plates", file_array[0])
		if not os.path.exists(dest_dir):
			os.makedirs(dest_dir)
		dest_file = os.path.join(dest_dir, file_basename)
		if os.path.exists(dest_file):
			os.unlink(dest_file)
		print "%s: %s -> %s"%(g_show_file_operation, m_srcpath, dest_file)
		if g_show_file_operation == "hardlink":
			os.link(m_srcpath, dest_file)
	elif file_array[-1] == 'ccc':
		dest_dir = os.path.join(subbed_shot_dir, "data", "cdl")
		if not os.path.exists(dest_dir):
			os.makedirs(dest_dir)
		dest_file = os.path.join(dest_dir, "%s.%s"%(shot, file_array[-1]))
		if os.path.exists(dest_file):
			os.unlink(dest_file)
		print "%s: %s -> %s"%(g_show_file_operation, m_srcpath, dest_file)
		if g_show_file_operation == "hardlink":
			os.link(m_srcpath, dest_file)
	elif file_array[-1] == 'cdl':
		dest_dir = os.path.join(subbed_shot_dir, "data", "cdl")
		if not os.path.exists(dest_dir):
			os.makedirs(dest_dir)
		dest_file = os.path.join(dest_dir, "%s.%s"%(shot, file_array[-1]))
		if os.path.exists(dest_file):
			os.unlink(dest_file)
		print "%s: %s -> %s"%(g_show_file_operation, m_srcpath, dest_file)
		if g_show_file_operation == "hardlink":
			os.link(m_srcpath, dest_file)
	elif file_array[-1] == 'pdf':
		dest_dir = os.path.join(subbed_shot_dir, "data", "count_sheets")
		if not os.path.exists(dest_dir):
			os.makedirs(dest_dir)
		dest_file = os.path.join(dest_dir, "%s.%s"%(file_array[0], file_array[-1]))
		if os.path.exists(dest_file):
			os.unlink(dest_file)
		print "%s: %s -> %s"%(g_show_file_operation, m_srcpath, dest_file)
		if g_show_file_operation == "hardlink":
			os.link(m_srcpath, dest_file)
			

if len(sys.argv) != 2:
	print("Error: Please provide a valid path to a directory as the first and only command line argument.")
	usage()
	exit()
	
if not os.path.exists(sys.argv[1]):
	print("Error: Path provided on the command line does not exist.")
	usage()
	exit()
elif not os.path.isdir(sys.argv[1]):
	print("Error: Path provided on the command line is not a directory.")
	usage()
	exit()
else:
	g_path = sys.argv[1]
	print "Located source folder %s."%g_path
	
# traverse the file structure

for dirname, subdirlist, filelist in os.walk(g_path):
	for fname in filelist:
		handle_file_copy(os.path.join(dirname, fname))
	
if len(g_skip_list) > 0:	
	print "\n\nSkipping the following files since they do not match the shot regular expression:\n\n"
	for skip_file in g_skip_list:
		print skip_file
	

