#!/usr/bin/python

# Generic Scan ingest, version 0.1a

import ConfigParser
import os
import sys
import re
import shutil
import glob
import cdl_convert
import pprint

g_ih_show_code = None
g_ih_show_root = None
g_ih_show_cfg_path = None
g_shot_regexp = None
g_seq_regexp = None
g_shot_dir = None
g_show_file_operation = None
g_skip_list = []
g_imgseq_regexp = None
g_shot_scripts_dir = None
g_shot_script_start = None
g_shot_template = None


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
    g_imgseq_regexp = config.get(g_ih_show_code, 'imgseq_regexp')
    g_shot_scripts_dir = config.get(g_ih_show_code, 'shot_scripts_dir')
    g_shot_comp_render_dir = config.get(g_ih_show_code, 'shot_comp_render_dir')
    g_shot_script_start = config.get(g_ih_show_code, 'shot_script_start')
    g_write_extension = config.get(g_ih_show_code, 'write_extension')
    g_write_frame_format = config.get(g_ih_show_code, 'write_frame_format')
    g_write_fps = config.get(g_ih_show_code, 'write_fps')
    g_shot_template = config.get('shot_template', sys.platform)
    print "Successfully loaded show-specific config file for %s."%g_ih_show_code
except KeyError:
    pass
    
g_dict_img_seq = {}
g_valid_exts = ['exr','ccc','cdl','jpg','pdf']
g_path = None

def handle_file_copy(m_srcpath):
    file_basename = os.path.basename(m_srcpath)
    shot = None
    seq = None
    file_array = file_basename.split('.')
    m_cdl_element_regexp = '%s[0-9A-Za-z_]*'%g_shot_regexp
    m_cdl_mainplate_regexp = 'GS|BS|MP'
    b_nocdl = False
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

    subbed_seq_dir = g_shot_dir.replace('/', os.path.sep).replace("SHOW_ROOT", g_ih_show_root).replace("SEQUENCE", seq).replace("SHOT", '')
    # create the sequence if it doesn't exist   
    if not os.path.exists(subbed_seq_dir):
        print "Creating new sequence %s."%seq
        seq_stub_dir = os.path.join(g_ih_show_root, "SHARED", "lib", "seq_stub")
        shutil.copytree(seq_stub_dir, subbed_seq_dir)
    
    subbed_shot_dir = g_shot_dir.replace('/', os.path.sep).replace("SHOW_ROOT", g_ih_show_root).replace("SEQUENCE", seq).replace("SHOT", shot)

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
        
        # part of an image sequence?
        matchobject = re.search(g_imgseq_regexp, dest_file)
        if matchobject:
            img_seq_gd = matchobject.groupdict()
            if not g_dict_img_seq.get(subbed_shot_dir):
                g_dict_img_seq[subbed_shot_dir] = { img_seq_gd['base'] : { 'frames' : [img_seq_gd['frame']], 'ext' : img_seq_gd['ext']} }
            else:
                if not g_dict_img_seq[subbed_shot_dir].get(img_seq_gd['base']):
                    g_dict_img_seq[subbed_shot_dir][img_seq_gd['base']] = { 'frames' : [img_seq_gd['frame']], 'ext' : img_seq_gd['ext']}
                else:
                    g_dict_img_seq[subbed_shot_dir][img_seq_gd['base']]['frames'].append(img_seq_gd['frame'])
                
    elif file_array[-1] == 'ccc' or file_array[-1] == 'cdl':
        
        b_nocdl = False
        dest_dir = os.path.join(subbed_shot_dir, "data", "cdl")
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        
        # any files in the CDL directory?
        l_cc_files = glob.glob(os.path.join(dest_dir, "*.cdl"))
        if len(l_cc_files) == 0:
            b_nocdl = True
        
        # clean up file name
        cdl_file_head = file_array[0]
        cdl_clean_file_head = None
        matchobject = re.search(m_cdl_element_regexp, cdl_file_head)
        
        # check to be see if this CDL file matches a plate name
        if not matchobject:
            cdl_clean_file_head = shot
        else:
            cdl_clean_file_head = matchobject.group(0)
        dest_file = os.path.join(dest_dir, "%s.%s"%(cdl_clean_file_head, file_array[-1]))
        if os.path.exists(dest_file):
            os.unlink(dest_file)
        print "%s: %s -> %s"%(g_show_file_operation, m_srcpath, dest_file)
        if g_show_file_operation == "hardlink":
            os.link(m_srcpath, dest_file)

        # if cdl file name matches the main plate for the shot, then create the shot-level CDL
        # also, if NO cdl has been created for the shot, then create the shot-level CDL by default
        # since we are the shot-level CDL, make a .cc file that Nuke can read
        
        if re.search(m_cdl_mainplate_regexp, cdl_clean_file_head) or b_nocdl:
        
            dest_file = os.path.join(dest_dir, "%s.%s"%(shot, file_array[-1]))
            if not b_nocdl and os.path.exists(dest_file):
                os.unlink(dest_file)
            print "%s: %s -> %s"%(g_show_file_operation, m_srcpath, dest_file)
            if g_show_file_operation == "hardlink":
                os.link(m_srcpath, dest_file)
                
            # if .cdl file, make a .cc file that Nuke can actually read
            if file_array[-1] == 'cdl':
                cdl_convert.reset_all()
                ccc = cdl_convert.parse_cdl(dest_file)
                cc = ccc.color_decisions[0].cc
                cc.id=shot
                dest_cc_file = '.'.join([os.path.splitext(dest_file)[0], 'cc'])
                cc.determine_dest('cc',dest_dir)
                cdl_convert.write_cc(cc)
                print "INFO: Converted CC File written at %s"%cc.file_out
                
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
    

# create template Nuke scripts if they don't exist
# if they do exist, add the plate to them

import nuke

for shot_dir in g_dict_img_seq.keys():
    shot = None
    seq = None
    matchobject = re.search(g_shot_regexp, shot_dir)
    # make sure this file matches the shot pattern
    if not matchobject:
        print "ERROR: somehow shot directory %s isn't actually a shot!"%shot_dir
        continue
    else:
        shot = matchobject.groupdict()['shot']
        seq = matchobject.groupdict()['sequence']

    print "INFO: Beginning Nuke script process for %s."%shot
    nuke_script_starter = g_shot_script_start.format(**matchobject.groupdict())
    full_nuke_script_path = os.path.join(shot_dir, g_shot_scripts_dir, "%s.nk"%nuke_script_starter)
    if os.path.exists(full_nuke_script_path):
        print "INFO: Nuke script already exists at %s. Skipping."%full_nuke_script_path
    else:
        print "INFO: Creating new Nuke script at %s!"%full_nuke_script_path
    

    subbed_seq_dir = g_shot_dir.replace('/', os.path.sep).replace("SHOW_ROOT", g_ih_show_root).replace("SEQUENCE", seq).replace("SHOT", '')
    subbed_shot_dir = g_shot_dir.replace('/', os.path.sep).replace("SHOW_ROOT", g_ih_show_root).replace("SEQUENCE", seq).replace("SHOT", shot)
    
    comp_render_dir_dict = { 'pathsep' : os.path.sep, 'compdir' : nuke_script_starter }
    comp_write_path = os.path.join(shot_dir, g_shot_comp_render_dir.format(**comp_render_dir_dict), "%s.%s.%s"%(nuke_script_starter, g_write_frame_format, g_write_extension))
    nuke.scriptOpen(g_shot_template)
    bd_node = nuke.toNode("BackdropNode1")
    bd_node_w = nuke.toNode("BackdropNode2")
    main_read = nuke.toNode("Read1")
    main_write = nuke.toNode("Write_exr")
    main_cdl = nuke.toNode("VIEWER_INPUT.OCIOCDLTransform1")
    plates = g_dict_img_seq[shot_dir].keys()
    # handle the main plate
    mainplate_dict = g_dict_img_seq[shot_dir][plates[0]]
    mainplate_ext = mainplate_dict['ext']
    mainplate_frames = sorted(mainplate_dict['frames'])
    mainplate_first = int(mainplate_frames[0])
    mainplate_last = int(mainplate_frames[-1])
    
    # set the values in the template
    bd_node.knob('label').setValue("<center>%s"%os.path.basename(plates[0]))
    main_read.knob('file').setValue("%s.%s.%s"%(plates[0], g_write_frame_format, mainplate_ext))
    main_read.knob('first').setValue(mainplate_first)
    main_read.knob('last').setValue(mainplate_last)
    main_read.knob('origfirst').setValue(mainplate_first)
    main_read.knob('origlast').setValue(mainplate_last)
    nuke.root().knob('first_frame').setValue(mainplate_first)
    nuke.root().knob('last_frame').setValue(mainplate_last)
    nuke.root().knob('txt_ih_show').setValue(g_ih_show_code)
    nuke.root().knob('txt_ih_show_path').setValue(g_ih_show_root)
    nuke.root().knob('txt_ih_seq').setValue(seq)
    nuke.root().knob('txt_ih_seq_path').setValue(subbed_seq_dir)
    nuke.root().knob('txt_ih_shot').setValue(shot)
    nuke.root().knob('txt_ih_shot_path').setValue(subbed_shot_dir)
    main_cdl.knob('file').setValue(os.path.join(shot_dir, "data", "cdl", "%s.cc"%shot))
    main_write.knob('file').setValue(comp_write_path)
    bd_node_w.knob('label').setValue("<center>%s\ncomp output"%shot)
    
    # bring in any additional plates
    if len(plates) > 1:
        last_read = main_read
        last_read_xpos = 80
        last_bd_xpos = -69
        last_bd = bd_node
        for addlplate in plates[1:]:
            newplate_dict = g_dict_img_seq[shot_dir][addlplate]
            newplate_ext = newplate_dict['ext']
            newplate_frames = sorted(newplate_dict['frames'])
            newplate_first = int(newplate_frames[0])
            newplate_last = int(newplate_frames[-1])
            # copy/paste read and backdrop
            new_read = nuke.createNode("Read")
            new_bd = nuke.createNode("BackdropNode")
            
            new_bd.knob('note_font_size').setValue(42)
            new_bd.knob('bdwidth').setValue(373)
            new_bd.knob('bdheight').setValue(326)
            
            
            new_bd_xpos = last_bd_xpos + 450
            new_read_xpos = last_read_xpos + 450
            
            new_bd.knob('xpos').setValue(new_bd_xpos)
            new_bd.knob('ypos').setValue(-1025)
            new_read.knob('xpos').setValue(new_read_xpos)
            new_read.knob('ypos').setValue(-907)

            newplate_dict = g_dict_img_seq[shot_dir][addlplate]
            newplate_ext = newplate_dict['ext']
            newplate_frames = sorted(newplate_dict['frames'])
            newplate_first = int(newplate_frames[0])
            newplate_last = int(newplate_frames[-1])
            
            new_bd.knob('label').setValue("<center>%s"%os.path.basename(addlplate))
            new_read.knob('file').setValue("%s.%s.%s"%(addlplate, g_write_frame_format, newplate_ext))
            new_read.knob('first').setValue(newplate_first)
            new_read.knob('last').setValue(newplate_last)
            new_read.knob('origfirst').setValue(newplate_first)
            new_read.knob('origlast').setValue(newplate_last)
            
            last_read = new_read
            last_read_xpos = new_read_xpos
            last_bd = new_bd
            last_bd_xpos = new_bd_xpos
            
    # that should do it!
    nuke.scriptSaveAs(full_nuke_script_path)
    print "INFO: Successfully wrote out Nuke script at %s!"%full_nuke_script_path
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
    
    
    
    
    
    
    
    
    
    
    
