#!/usr/bin/python

# Generic Scan ingest, version 0.1a

import sys

SYSARGV = sys.argv

import ConfigParser
import os
import re
import shutil
import glob
import cdl_convert
import pprint
import utilities
from timecode import TimeCode
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom
import OpenEXR
import Imath
import sgtk

import db_access as DB

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
g_shot_thumb_dir = None
g_cdl_mainplate_regexp = None
g_plate_colorspace = None

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
    g_shot_regexp = config.get(g_ih_show_code, 'shot_regexp_ci')
    g_seq_regexp = config.get(g_ih_show_code, 'sequence_regexp_ci')
    g_shot_dir = config.get(g_ih_show_code, 'shot_dir')
    g_show_file_operation = config.get(g_ih_show_code, 'show_file_operation')
    g_imgseq_regexp = config.get(g_ih_show_code, 'imgseq_regexp')
    g_shot_scripts_dir = config.get(g_ih_show_code, 'shot_scripts_dir')
    g_shot_comp_render_dir = config.get(g_ih_show_code, 'shot_comp_render_dir')
    g_shot_script_start = config.get(g_ih_show_code, 'shot_script_start')
    g_write_extension = config.get(g_ih_show_code, 'write_extension')
    g_write_frame_format = config.get(g_ih_show_code, 'write_frame_format')
    g_write_fps = config.get(g_ih_show_code, 'write_fps')
    g_plate_colorspace = config.get(g_ih_show_code, 'plate_colorspace')
    g_cdl_mainplate_regexp = config.get(g_ih_show_code, 'cdl_mainplate_regexp')
    g_shot_template = config.get('shot_template', sys.platform)
    g_shot_thumb_dir = config.get('thumbnails', 'shot_thumb_dir')
    print "Successfully loaded show-specific config file for %s."%g_ih_show_code
except KeyError:
    pass
    
g_dict_img_seq = {}
g_valid_exts = ['exr','dpx','ccc','cdl','jpg','pdf','mov']
g_path = None

def handle_file_copy(m_srcpath):
    file_basename = os.path.basename(m_srcpath)
    shot = None
    seq = None
    file_array = file_basename.split('.')
    m_cdl_element_regexp = '%s[0-9A-Za-z_]*'%g_shot_regexp
    m_cdl_mainplate_regexp = g_cdl_mainplate_regexp
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
        shot = matchobject.group(0).lower()
        seq = re.search(g_seq_regexp, shot).group(0).lower()

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
    
    if file_array[-1] == 'exr' or file_array[-1] == 'dpx':
        badchar_re = r'\(|\)'
        badchar_match = re.search(badchar_re, file_array[0])
        if badchar_match:
            g_skip_list.append(m_srcpath)
            return
        dest_dir = os.path.join(subbed_shot_dir, "pix", "plates", file_array[0].lower())
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        dest_file = os.path.join(dest_dir, file_basename.lower())
        if not os.path.exists(dest_file):
            # os.unlink(dest_file)
            print "%s: %s -> %s"%(g_show_file_operation, m_srcpath, dest_file)
            if g_show_file_operation == "hardlink":
                os.link(m_srcpath, dest_file)
            elif g_show_file_operation == "copy":
                shutil.copyfile(m_srcpath, dest_file)
        
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
            cdl_clean_file_head = matchobject.group(0).lower()
        dest_file = os.path.join(dest_dir, "%s.%s"%(cdl_clean_file_head, file_array[-1]))
        if os.path.exists(dest_file):
            os.unlink(dest_file)
        print "%s: %s -> %s"%(g_show_file_operation, m_srcpath, dest_file)
        if g_show_file_operation == "hardlink":
            os.link(m_srcpath, dest_file)
        elif g_show_file_operation == "copy":
            shutil.copyfile(m_srcpath, dest_file)
            

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
            elif g_show_file_operation == "copy":
                shutil.copyfile(m_srcpath, dest_file)
                                
            # if .cdl file, make a .cc file that Nuke can actually read
            # if file_array[-1] == 'cdl':
            cdltext = open(dest_file, 'r').read()
            # slope
            slope_re_str = r'<Slope>([0-9.-]+) ([0-9.-]+) ([0-9.-]+)</Slope>'
            slope_re = re.compile(slope_re_str)
            slope_match = slope_re.search(cdltext)
            if not slope_match:
                print "WARNING: XML file %s does not appear to have any valid <Slope> element."%dest_file
                slope_r = "1.0"
                slope_g = "1.0"
                slope_b = "1.0"
            else:
                slope_r = slope_match.group(1)
                slope_g = slope_match.group(2)
                slope_b = slope_match.group(3)

            # offset
            offset_re_str = r'<Offset>([0-9.-]+) ([0-9.-]+) ([0-9.-]+)</Offset>'
            offset_re = re.compile(offset_re_str)
            offset_match = offset_re.search(cdltext)
            if not offset_match:
                print "WARNING: XML file %s does not appear to have any valid <Offset> element."%dest_file
                offset_r = "0.0"
                offset_g = "0.0"
                offset_b = "0.0"
            else:
                offset_r = offset_match.group(1)
                offset_g = offset_match.group(2)
                offset_b = offset_match.group(3)
            
            # power
            power_re_str = r'<Power>([0-9.-]+) ([0-9.-]+) ([0-9.-]+)</Power>'
            power_re = re.compile(power_re_str)
            power_match = power_re.search(cdltext)
            if not power_match:
                print "WARNING: XML file %s does not appear to have any valid <Power> element."%dest_file
                power_r = "1.0"
                power_g = "1.0"
                power_b = "1.0"
            else:
                power_r = power_match.group(1)
                power_g = power_match.group(2)
                power_b = power_match.group(3)
            
            # saturation
            saturation_re_str = r'<Saturation>([0-9.-]+)</Saturation>'
            saturation_re = re.compile(saturation_re_str)
            saturation_match = saturation_re.search(cdltext)
            if not saturation_match:
                print "WARNING: XML file %s does not appear to have any valid <Saturation> element."%dest_file
                saturation = "1.0"
            else:
                saturation = saturation_match.group(1)
            
            # build the XML document tree
            dest_cc_file = '.'.join([os.path.splitext(dest_file)[0], 'cc'])
            print "INFO: Creating shot-level .CC file, for Nuke compatibility, at %s"%dest_cc_file
            root = ET.Element("ColorCorrection", id=shot)
            sopnode = ET.SubElement(root, "SOPNode")
            slopenode = ET.SubElement(sopnode, "Slope").text = "%s %s %s"%(slope_r, slope_g, slope_b)
            offsetnode = ET.SubElement(sopnode, "Offset").text = "%s %s %s"%(offset_r, offset_g, offset_b)
            powernode = ET.SubElement(sopnode, "Power").text = "%s %s %s"%(power_r, power_g, power_b)
            satnode = ET.SubElement(root, "SatNode")
            saturationnode = ET.SubElement(satnode, "Saturation").text = saturation
            rough_string = ET.tostring(root)
            reparsed = minidom.parseString(rough_string)
            pretty_xml = reparsed.toprettyxml(indent='  ')
            dest_cc_file_handle = open(dest_cc_file, 'w')
            dest_cc_file_handle.write(pretty_xml)
            dest_cc_file_handle.close()

            # cdl_convert.reset_all()
            # ccc = cdl_convert.parse_cdl(dest_file)
            # cc = ccc.color_decisions[0].cc
            # cc.id=shot
            # dest_cc_file = '.'.join([os.path.splitext(dest_file)[0], 'cc'])
            # cc.determine_dest('cc',dest_dir)
            # cdl_convert.write_cc(cc)
            # print "INFO: Converted CC File written at %s"%cc.file_out
                
    elif file_array[-1] == 'pdf':
        dest_dir = os.path.join(subbed_shot_dir, "data", "count_sheets")
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        dest_file = os.path.join(dest_dir, "%s.%s"%(file_array[0].lower(), file_array[-1]))
        if os.path.exists(dest_file):
            os.unlink(dest_file)
        print "%s: %s -> %s"%(g_show_file_operation, m_srcpath, dest_file)
        if g_show_file_operation == "hardlink":
            os.link(m_srcpath, dest_file)
        elif g_show_file_operation == "copy":
            shutil.copyfile(m_srcpath, dest_file)            

    elif file_array[-1] == 'mov':
        dest_dir = os.path.join(subbed_shot_dir, "ref")
        if not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
        dest_file = os.path.join(dest_dir, "%s.%s"%(file_array[0].lower(), file_array[-1]))
        if os.path.exists(dest_file):
            os.unlink(dest_file)
        print "%s: %s -> %s"%(g_show_file_operation, m_srcpath, dest_file)
        if g_show_file_operation == "hardlink":
            os.link(m_srcpath, dest_file)
        elif g_show_file_operation == "copy":
            shutil.copyfile(m_srcpath, dest_file)            

if len(SYSARGV) != 2:
    print("Error: Please provide a valid path to a directory as the first and only command line argument.")
    usage()
    exit()
    
if not os.path.exists(SYSARGV[1]):
    print("Error: Path provided on the command line does not exist.")
    usage()
    exit()
elif not os.path.isdir(SYSARGV[1]):
    print("Error: Path provided on the command line is not a directory.")
    usage()
    exit()
else:
    g_path = SYSARGV[1]
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
# add shots, sequences, and plates into the database if they don't already exist

ihdb = DB.DBAccessGlobals.get_db_access()
b_create_nuke = False

import nuke
tk = None

# Shotgun Authentication
sa = sgtk.authentication.ShotgunAuthenticator()
user = sa.create_script_user(api_script='goosebumps2_api_access', api_key='a3a1d0ccd72ffdc073ff151dd52c84abe1a5dd6d4fe18fba1efa882df8b1e36a', host='https://qppe.shotgunstudio.com')
sgtk.set_authenticated_user(user)

for shot_dir in g_dict_img_seq.keys():
    shot = None
    seq = None
    b_create_nuke = False
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
        b_create_nuke = True

    plates = []
    for plate_key in g_dict_img_seq[shot_dir].keys():
        if re.search(g_cdl_mainplate_regexp, plate_key):
            plates.insert(0, plate_key)
        else:
            plates.append(plate_key)
    
    print "INFO: Plates for shot %s:"%shot
    print plates
    
    # handle the main plate
    mainplate_dict = g_dict_img_seq[shot_dir][plates[0]]
    mainplate_ext = mainplate_dict['ext']
    mainplate_frames = sorted(mainplate_dict['frames'])
    mainplate_first = int(mainplate_frames[0])
    mainplate_last = int(mainplate_frames[-1])

    subbed_seq_dir = g_shot_dir.replace('/', os.path.sep).replace("SHOW_ROOT", g_ih_show_root).replace("SEQUENCE", seq).replace("SHOT", '')
    subbed_shot_dir = g_shot_dir.replace('/', os.path.sep).replace("SHOW_ROOT", g_ih_show_root).replace("SEQUENCE", seq).replace("SHOT", shot)
    
    # retrieve objects for sequence/shot from the database. 
    # create them if they do not exist.
    b_newshot = False
    
    dbseq = ihdb.fetch_sequence(seq)
    if not dbseq:
        print "INFO: Creating new sequence %s at path %s."%(seq, subbed_seq_dir)
        dbseq = DB.Sequence(seq, subbed_seq_dir, -1)
        ihdb.create_sequence(dbseq)
        
    print "INFO: Got sequence %s object from database with ID of %s."%(dbseq.g_seq_code, dbseq.g_dbid)

    dbshot = ihdb.fetch_shot(shot)
    if not dbshot:
        print "INFO: Creating new shot %s at path %s."%(shot, subbed_shot_dir)
        dbshot = DB.Shot(shot, subbed_shot_dir, -1, dbseq, None, mainplate_first, mainplate_first + 8, mainplate_last - 8, mainplate_last, mainplate_last - mainplate_first - 15)
        ihdb.create_shot(dbshot)
        # useful for creating thumbnails based on a plate, not on the latest comp
        b_newshot = True
        
    print "INFO: Got shot %s object from database with ID of %s."%(dbshot.g_shot_code, dbshot.g_dbid)

    # grab a toolkit object from the shot entity
    tk = sgtk.sgtk_from_entity('Shot', int(dbshot.g_dbid))
    
    # retrive object from database for main plate
    mainplate_base = os.path.basename(plates[0])
    dbplate = ihdb.fetch_plate(mainplate_base, dbshot)
    
    shot_thumb_dir = os.path.join(subbed_shot_dir, g_shot_thumb_dir.format(pathsep=os.path.sep))
    b_new_shot_thumb = False
    existing_thumb_list = glob.glob(os.path.join(shot_thumb_dir, "%s_comp_v*.png"%shot))
    if len(existing_thumb_list) == 0:
        print "INFO: No comp version thumbnails exist for shot %s in folder %s."%(shot, shot_thumb_dir)
        b_new_shot_thumb = True
    
    if not dbplate:
        print "INFO: Creating new plate %s for shot %s."%(mainplate_base, shot)
        plate_name = os.path.basename(plates[0])
        start_frame = mainplate_first
        end_frame = mainplate_last
        duration = (end_frame - start_frame + 1)
        thumb_frame = start_frame + (duration/2)
        plate_path = "%s.%s.%s"%(plates[0], g_write_frame_format, mainplate_ext)
        start_file_path = "%s.%s.%s"%(plates[0], mainplate_first, mainplate_ext)
        end_file_path = "%s.%s.%s"%(plates[0], mainplate_last, mainplate_ext)
        thumb_frame_path = "%s.%s.%s"%(plates[0], thumb_frame, mainplate_ext)
        clip_name = plate_name
        scene = ""
        take = ""
        start_file = None
        start_timecode = 0
        try:
            start_file = OpenEXR.InputFile(start_file_path)
            start_timecode = int(start_frame)*1000
            start_tc_obj = start_file.header()['timeCode']
            header_fps = float(start_file.header()['framesPerSecond'].n)/float(start_file.header()['framesPerSecond'].d)
            start_timecode = int((TimeCode("%02d:%02d:%02d:%02d"%(start_tc_obj.hours, start_tc_obj.minutes, start_tc_obj.seconds, start_tc_obj.frame), inputfps=header_fps).frame_number() * 1000) / header_fps)
            clip_name = start_file.header()['reelName']
            scene = start_file.header()['Scene']
            take = start_file.header()['Take']
        except KeyError:
            e = sys.exc_info()
            print "KeyError: metadata key %s not available in EXR file."%e[1]
        except ValueError as ve:
            print "ERROR: %s"%ve.message
        except IOError as ioe:
            print "WARNING: Image is not in EXR format."            

        end_file = None
        end_timecode = 0

        try:
            end_file = OpenEXR.InputFile(end_file_path)
            end_tc_obj = end_file.header()['timeCode']
            end_timecode = int((TimeCode("%02d:%02d:%02d:%02d"%(end_tc_obj.hours, end_tc_obj.minutes, end_tc_obj.seconds, end_tc_obj.frame)).frame_number() * 1000) / 24)
        except KeyError:
            e = sys.exc_info()
            print "KeyError: metadata key %s not available in EXR file."%e[1]
        except IOError as ioe:
            print "WARNING: Image is not in EXR format."            

        dbplate = DB.Plate(plate_name, start_frame, end_frame, duration, plate_path, start_timecode, clip_name, scene, take, end_timecode, dbshot, -1)
        ihdb.create_plate(dbplate)
        
        # upload a thumbnail for the plate_name
        # first, create a .PNG from the source...
        generated_thumb_path = utilities.create_thumbnail(thumb_frame_path)
        ihdb.upload_thumbnail('Plate', dbplate, generated_thumb_path)
        print "INFO: Uploaded thumbnail %s to DB plate object %s."%(generated_thumb_path, dbplate.g_plate_name)
        
        # publish the plate using the toolkit API
        # first, get a context object
        print "INFO: Retreiving context object for Shot with id = %s from ToolKit API."%dbshot.g_dbid
        context = tk.context_from_entity('Shot', int(dbshot.g_dbid))
        # register the publish
        print "INFO: Registering publish."
        dbpublishplate = sgtk.util.register_publish(tk, context, plate_path, plate_name, 1, comment = 'Publish of plate by Scan Ingestion script', published_file_type = 'Plate')
        # upload a thumbnail
        print "INFO: Uploading thumbnail for publish."
        ihdb.upload_thumbnail('PublishedFile', dbplate, generated_thumb_path, altid = dbpublishplate['id'])

        # upload a thumbnail for the plate to the shot, in the event that this is a new shot
        if b_new_shot_thumb:
            ihdb.upload_thumbnail('Shot', dbshot, generated_thumb_path)
            print "INFO: Uploaded thumbnail %s to DB shot object %s."%(generated_thumb_path, dbshot.g_shot_code)

    print "INFO: Got plate %s object from database with ID of %s."%(dbplate.g_plate_name, dbplate.g_dbid)

    if b_create_nuke:
        print "INFO: Building Nuke Script from template."
        comp_render_dir_dict = { 'pathsep' : os.path.sep, 'compdir' : nuke_script_starter }
        comp_write_path = os.path.join(shot_dir, g_shot_comp_render_dir.format(**comp_render_dir_dict), "%s.%s.%s"%(nuke_script_starter, g_write_frame_format, g_write_extension))
        print "INFO: About to open: %s"%g_shot_template
        nuke.scriptOpen(g_shot_template)
        print "INFO: Shot template loaded."
        bd_node = nuke.toNode("BackdropNode1")
        bd_node_w = nuke.toNode("BackdropNode2")
        main_read = nuke.toNode("Read1")
        main_write = nuke.toNode("Write_exr")
        main_cdl = nuke.toNode("VIEWER_INPUT.OCIOCDLTransform1")
        
        # handle non-standard plate format
        start_file_path = "%s.%s.%s"%(plates[0], mainplate_first, mainplate_ext)
        start_file = None
        width = 3424
        height = 2202
        try:
            start_file = OpenEXR.InputFile(start_file_path)
            dwindow_header = start_file.header()['displayWindow']
            width = dwindow_header.max.x - dwindow_header.min.x + 1
            height = dwindow_header.max.y - dwindow_header.min.y + 1
        except IOError as ioe:
            print "WARNING: File is not EXR file."
        fstring = '%d %d Plate Format'%(width, height)
        fobj = nuke.addFormat(fstring)
        nuke.root().knob('format').setValue(fobj)        
#         nuke.toNode("Reformat1").knob('format').setValue(fobj)
#         nuke.toNode('Crop1').knob('box').setR(width)
#         nuke.toNode('Crop1').knob('box').setT(height)
        
        # set the values in the template
        bd_node.knob('label').setValue("<center>%s"%os.path.basename(plates[0]))
        main_read.knob('file').setValue("%s.%s.%s"%(plates[0], g_write_frame_format, mainplate_ext))
        main_read.knob('first').setValue(mainplate_first)
        main_read.knob('last').setValue(mainplate_last)
        main_read.knob('origfirst').setValue(mainplate_first)
        main_read.knob('origlast').setValue(mainplate_last)
        main_read.knob('colorspace').setValue(g_plate_colorspace)
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
        if b_create_nuke:
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

            # fetch or create the plate in shotgun
            addlplate_base = os.path.basename(addlplate)
            dbplate = ihdb.fetch_plate(addlplate_base, dbshot)
    
            if not dbplate:
                print "INFO: Creating new plate %s for shot %s."%(addlplate_base, shot)
                plate_name = os.path.basename(addlplate)
                start_frame = newplate_first
                end_frame = newplate_last
                duration = (end_frame - start_frame + 1)
                thumb_frame = start_frame + (duration/2)
                plate_path = "%s.%s.%s"%(addlplate, g_write_frame_format, newplate_ext)
                start_file_path = "%s.%s.%s"%(addlplate, newplate_first, newplate_ext)
                end_file_path = "%s.%s.%s"%(addlplate, newplate_last, newplate_ext)
                thumb_frame_path = "%s.%s.%s"%(addlplate, thumb_frame, newplate_ext)

                start_file = None

                try:
                    start_file = OpenEXR.InputFile(start_file_path)
                    start_tc_obj = start_file.header()['timeCode']
                    start_timecode = int((TimeCode("%02d:%02d:%02d:%02d"%(start_tc_obj.hours, start_tc_obj.minutes, start_tc_obj.seconds, start_tc_obj.frame)).frame_number() * 1000) / 24)
                    clip_name = start_file.header()['reelName']
                    scene = start_file.header()['Scene']
                    take = start_file.header()['Take']
                except KeyError:
                    e = sys.exc_info()
                    print e[0]
                    print e[1]
                    print e[2]
                except IOError as ioe:
                    print "WARNING: file %s is not exr file."%start_file_path

                end_file = None

                try:
                    end_file = OpenEXR.InputFile(end_file_path)
                    end_tc_obj = end_file.header()['timeCode']
                    end_timecode = int((TimeCode("%02d:%02d:%02d:%02d"%(end_tc_obj.hours, end_tc_obj.minutes, end_tc_obj.seconds, end_tc_obj.frame)).frame_number() * 1000) / 24)
                except KeyError:
                    e = sys.exc_info()
                    print e[0]
                    print e[1]
                    print e[2]
                except IOError as ioe:
                    print "WARNING: file %s is not exr file."%start_file_path

                dbplate = DB.Plate(plate_name, start_frame, end_frame, duration, plate_path, start_timecode, clip_name, scene, take, end_timecode, dbshot, -1)
                ihdb.create_plate(dbplate)
                # upload a thumbnail for the plate_name
                # first, create a .PNG from the source...
                generated_thumb_path = utilities.create_thumbnail(thumb_frame_path)
                ihdb.upload_thumbnail('Plate', dbplate, generated_thumb_path)
                print "INFO: Uploaded thumbnail %s to DB plate object %s."%(generated_thumb_path, dbplate.g_plate_name)

                # publish the plate using the toolkit API
                # first, get a context object
                print "INFO: Retreiving context object for Shot with id = %s from ToolKit API."%dbshot.g_dbid
                context = tk.context_from_entity('Shot', int(dbshot.g_dbid))
                # register the publish
                print "INFO: Registering publish."
                dbpublishplate = sgtk.util.register_publish(tk, context, plate_path, plate_name, 1, comment = 'Publish of plate by Scan Ingestion script', published_file_type = 'Plate')
                # upload a thumbnail
                print "INFO: Uploading thumbnail for publish."
                ihdb.upload_thumbnail('PublishedFile', dbplate, generated_thumb_path, altid = dbpublishplate['id'])


            print "INFO: Got plate %s object from database with ID of %s."%(dbplate.g_plate_name, dbplate.g_dbid)
                                    
            if b_create_nuke:
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
                new_read.knob('colorspace').setValue(g_plate_colorspace)
                
                last_read = new_read
                last_read_xpos = new_read_xpos
                last_bd = new_bd
                last_bd_xpos = new_bd_xpos
    
    # that should do it!
    if b_create_nuke:
        print "INFO: About to save Nuke script %s..."%full_nuke_script_path
        ret_val = nuke.scriptSaveAs(filename = full_nuke_script_path, overwrite = 1)
        if ret_val:
            print "WARNING: Something went wrong."
            print ret_val
            print sys.last_type
            print sys.last_value
            print sys.last_traceback
        else:
            print "INFO: Successfully wrote out Nuke script at %s!"%full_nuke_script_path
        nuke.scriptClose()
        
        # publish the Nuke script
        print "INFO: Attempting to publish Nuke Script to Shotgun using the Toolkit API..."
        dbtasks = ihdb.fetch_tasks_for_shot(dbshot)
        if len(dbtasks) > 0:
            dbtask = dbtasks[0]
            context = tk.context_from_entity('Task', int(dbtask.g_dbid))
            sg_publish_name = os.path.basename(full_nuke_script_path).split('.')[0].split('_v')[0]
            sg_publish_ver = int(os.path.basename(full_nuke_script_path).split('.')[0].split('_v')[1])
            dbpublishnk = sgtk.util.register_publish(tk, context, full_nuke_script_path, sg_publish_name, sg_publish_ver, comment = 'Initial publish of stub Nuke script by Scan Ingestion script', published_file_type = 'Nuke Script')
            existing_thumb_list = glob.glob(os.path.join(shot_thumb_dir, "%s*.png"%shot))
            if len(existing_thumb_list) > 0:
                ihdb.upload_thumbnail('PublishedFile', dbtask, existing_thumb_list[0], altid = dbpublishnk['id'])
            print "INFO: Done."
        
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
            
    
    
    
    
    
    
    
    
    
    
    
