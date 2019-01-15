#!/Applications/Nuke11.3v1/Nuke11.3v1.app/Contents/MacOS/python

import sys
import os

if len(sys.argv) < 2:
    print "ERROR: Please provide at least one image sequence or movie on the command line."
    exit()

SYSARGV = None
master_nuke_script = None

if os.path.splitext(sys.argv[1])[-1] == '.nk':
    SYSARGV = sys.argv[2:]
    master_nuke_script = sys.argv[1]
else:
    SYSARGV = sys.argv[1:]

import nuke
import logging
import ConfigParser
import re
import glob
import OpenEXR

homedir = os.path.expanduser('~')
logfile = ""
if sys.platform == 'win32':
    logfile = os.path.join(homedir, 'AppData', 'Local', 'IHPipeline', 'create_nuke_script.log')
elif sys.platform == 'darwin':
    logfile = os.path.join(homedir, 'Library', 'Logs', 'IHPipeline', 'create_nuke_script.log')
elif sys.platform == 'linux2':
    logfile = os.path.join(homedir, 'Logs', 'IHPipeline', 'create_nuke_script.log')
if not os.path.exists(os.path.dirname(logfile)):
    os.makedirs(os.path.dirname(logfile))
logFormatter = logging.Formatter("%(asctime)s:[%(threadName)s]:[%(levelname)s]:%(message)s")
log = logging.getLogger()
log.setLevel(logging.INFO)
fileHandler = logging.FileHandler(logfile)
fileHandler.setFormatter(logFormatter)
log.addHandler(fileHandler)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
log.addHandler(consoleHandler)    

g_ih_show_code = os.environ['IH_SHOW_CODE']
g_ih_show_root = os.environ['IH_SHOW_ROOT']
g_ih_show_cfg_path = os.environ['IH_SHOW_CFG_PATH']
config = ConfigParser.ConfigParser()
config.read(g_ih_show_cfg_path)

use_hires_stub = False
stub = ""
mainplate = None
addl_plates = []

mainref = None
addl_refs = []

hires_exts = config.get('scan_ingest', 'lutted_image_exts').split(',')
movie_exts = config.get('scan_ingest', 'movie_exts').split(',')
g_shot_script_start = config.get(g_ih_show_code, 'shot_script_start')
g_temp_script_start = config.get(g_ih_show_code, 'temp_script_start')
g_shot_dir_format = config.get(g_ih_show_code, 'shot_dir_format')
g_seq_dir_format = config.get(g_ih_show_code, 'seq_dir_format')
g_shot_scripts_dir = config.get(g_ih_show_code, 'shot_scripts_dir')
g_shot_comp_render_dir = config.get(g_ih_show_code, 'shot_comp_render_dir')
g_write_frame_format = config.get(g_ih_show_code, 'write_frame_format')
g_write_extension = config.get(g_ih_show_code, 'write_extension')
g_plate_colorspace = config.get(g_ih_show_code, 'plate_colorspace')
g_movie_colorspace = config.get(g_ih_show_code, 'movie_colorspace')
g_movie_frame_offset = int(config.get('scan_ingest', 'movie_frame_offset'))

mainplate_re = re.compile(config.get(g_ih_show_code, 'mainplate_regexp'))
imgseq_re = re.compile(config.get(g_ih_show_code, 'imgseq_regexp'))

for source_file in SYSARGV:

    ext = os.path.splitext(source_file)[-1].lstrip('.')
    if ext in hires_exts:
        use_hires_stub = True
        if not mainplate:
            mainplate = source_file
        else:
            addl_plates.append(source_file)
    elif ext in movie_exts:
        if not mainref:
            mainref = source_file
        else:
            addl_refs.append(source_file)

g_shot_regexp = config.get(g_ih_show_code, 'shot_regexp')
source_zero_dir = os.path.dirname(SYSARGV[0])

matchobject = re.search(g_shot_regexp, source_zero_dir)
shot = None
seq = None
# make sure this file matches the shot pattern
if not matchobject:
    log.error("Somehow source material directory %s isn't part of a shot!"%source_zero_dir)
    exit()
else:
    shot = matchobject.groupdict()['shot']
    seq = matchobject.groupdict()['sequence']

shot_dir = g_shot_dir_format.format(show_root = g_ih_show_root, pathsep = os.path.sep, sequence = seq, shot = shot)
seq_dir = g_seq_dir_format.format(show_root = g_ih_show_root, pathsep = os.path.sep, sequence = seq)

log.info("Beginning Nuke script process for %s."%shot)
nuke_script_starter = g_shot_script_start.format(**matchobject.groupdict())
temp_nuke_script_starter = g_temp_script_start.format(**matchobject.groupdict())
full_nuke_script_path = os.path.join(shot_dir, g_shot_scripts_dir, "%s.nk"%nuke_script_starter)
temp_full_nuke_script_path = os.path.join(shot_dir, g_shot_scripts_dir, "%s.nk"%temp_nuke_script_starter)

output_script = None
if master_nuke_script:
    output_script = master_nuke_script
    
cdl_dir = os.path.join(shot_dir, config.get(g_ih_show_code, 'cdl_dir_format').format(pathsep = os.path.sep))
cdl_file = '%s.%s'%(shot, config.get(g_ih_show_code, 'cdl_file_ext'))
cdl_full_path = os.path.join(cdl_dir, cdl_file)
    
if use_hires_stub:

    stub = config.get('shot_template', '%s'%sys.platform)
    if not master_nuke_script:
        output_script = full_nuke_script_path
    log.info("Building Nuke Script for final shot from template.")
    comp_render_dir_dict = { 'pathsep' : os.path.sep, 'compdir' : nuke_script_starter }
    comp_write_path = os.path.join(shot_dir, g_shot_comp_render_dir.format(**comp_render_dir_dict), "%s.%s.%s"%(nuke_script_starter, g_write_frame_format, g_write_extension))
    log.info("About to open: %s"%stub)
    nuke.scriptOpen(stub)
    log.info("Shot template loaded.")
    bd_node = nuke.toNode("BackdropNode1")
    bd_node_w = nuke.toNode("BackdropNode2")
    main_read = nuke.toNode("Read1")
    main_write = nuke.toNode("Write_exr")
    main_cdl = nuke.toNode("VIEWER_INPUT.OCIOCDLTransform1")
    
    frames_glob = mainplate.replace(g_write_frame_format, '*')
    frames_list = sorted(glob.glob(frames_glob))
        
    # handle non-standard plate format
    start_file_path = frames_list[0]
    start_file_base = os.path.basename(start_file_path)
    start_file_match = imgseq_re.search(start_file_base)
    file_base = start_file_match.group('base')
    start_frame = int(start_file_match.group('frame'))
    head_in = start_frame + int(config.get('scan_ingest', 'head_in_offset'))
    
    end_file_path = frames_list[-1]
    end_file_base = os.path.basename(end_file_path)
    end_file_match = imgseq_re.search(end_file_base)
    end_frame = int(end_file_match.group('frame'))
    tail_out = end_frame + int(config.get('scan_ingest', 'tail_out_offset'))
    
    start_file = None
    width = int(config.get(g_ih_show_code, 'default_plate_width'))
    height = int(config.get(g_ih_show_code, 'default_plate_height'))
    try:
        start_file = OpenEXR.InputFile(start_file_path)
        dwindow_header = start_file.header()['displayWindow']
        width = dwindow_header.max.x - dwindow_header.min.x + 1
        height = dwindow_header.max.y - dwindow_header.min.y + 1
    except IOError as ioe:
        log.warning("File is not EXR file.")
    fstring = '%d %d Plate Format'%(width, height)
    fobj = nuke.addFormat(fstring)
    nuke.root().knob('format').setValue(fobj)        

    # set the values in the template
    log.info('Adding main hi-res plate %s to script.'%mainplate)
    bd_node.knob('label').setValue("<center>%s"%file_base)
    main_read.knob('file').fromUserText(mainplate)
    main_read.knob('first').setValue(start_frame)
    main_read.knob('last').setValue(end_frame)
    main_read.knob('origfirst').setValue(start_frame)
    main_read.knob('origlast').setValue(end_frame)
    main_read.knob('colorspace').setValue(g_plate_colorspace)
    nuke.root().knob('first_frame').setValue(head_in)
    nuke.root().knob('last_frame').setValue(tail_out)
    nuke.root().knob('txt_ih_show').setValue(g_ih_show_code)
    nuke.root().knob('txt_ih_show_path').setValue(g_ih_show_root)
    nuke.root().knob('txt_ih_seq').setValue(seq)
    nuke.root().knob('txt_ih_seq_path').setValue(seq_dir)
    nuke.root().knob('txt_ih_shot').setValue(shot)
    nuke.root().knob('txt_ih_shot_path').setValue(shot_dir)
    main_cdl.knob('file').setValue(cdl_full_path)
    main_write.knob('file').setValue(comp_write_path)
    bd_node_w.knob('label').setValue("<center>%s\ncomp output"%shot)

    last_read = main_read
    last_read_xpos = 80
    last_bd_xpos = -69
    last_bd = bd_node
    
    # bring in any additional plates
    for addlplate in addl_plates:

        log.info('Adding additional hi-res plate %s to script.'%addlplate)
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
        
        new_frames_glob = addlplate.replace(g_write_frame_format, '*')
        new_frames_list = sorted(glob.glob(new_frames_glob))
        
        # handle non-standard plate format
        start_file_path = new_frames_list[0]
        start_file_base = os.path.basename(start_file_path)
        start_file_match = imgseq_re.search(start_file_base)
        new_plate_base = start_file_match.group('base')
        start_frame = int(start_file_match.group('frame'))
    
        end_file_path = new_frames_list[-1]
        end_file_base = os.path.basename(end_file_path)
        end_file_match = imgseq_re.search(end_file_base)
        end_frame = int(end_file_match.group('frame'))
    
        new_bd.knob('label').setValue("<center>%s"%new_plate_base)
        new_read.knob('file').fromUserText(addlplate)
        new_read.knob('first').setValue(start_frame)
        new_read.knob('last').setValue(end_frame)
        new_read.knob('origfirst').setValue(start_frame)
        new_read.knob('origlast').setValue(end_frame)
        new_read.knob('colorspace').setValue(g_plate_colorspace)
        
        last_read = new_read
        last_read_xpos = new_read_xpos
        last_bd = new_bd
        last_bd_xpos = new_bd_xpos
        
    # bring in reference
    if mainref:

        log.info('Adding reference movie %s to script.'%mainref)
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

        new_plate_base = os.path.splitext(os.path.basename(mainref))[0]
    
        new_bd.knob('label').setValue("<center>Reference\n%s"%new_plate_base)
        new_read.knob('file').fromUserText(mainref)
        new_read.knob('colorspace').setValue(g_movie_colorspace)
        new_read.knob('frame_mode').setValue('offset')
        new_read.knob('frame').setValue(str(-1*g_movie_frame_offset))
        
        last_read = new_read
        last_read_xpos = new_read_xpos
        last_bd = new_bd
        last_bd_xpos = new_bd_xpos

    # bring in additional reference
    for addlref in addl_refs:

        log.info('Adding reference movie %s to script.'%addlref)
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

        new_plate_base = os.path.splitext(os.path.basename(addlref))[0]
    
        new_bd.knob('label').setValue("<center>Reference\n%s"%new_plate_base)
        new_read.knob('file').fromUserText(addlref)
        new_read.knob('colorspace').setValue(g_movie_colorspace)
        new_read.knob('frame_mode').setValue('offset')
        new_read.knob('frame').setValue(str(-1*g_movie_frame_offset))
        
        last_read = new_read
        last_read_xpos = new_read_xpos
        last_bd = new_bd
        last_bd_xpos = new_bd_xpos
    
else:

    stub = config.get('shot_template', 'temp_%s'%sys.platform)
    if not master_nuke_script:
        output_script = temp_full_nuke_script_path
        
    log.info("Building Nuke Script for temp shot from template.")
    comp_render_dir_dict = { 'pathsep' : os.path.sep, 'compdir' : temp_nuke_script_starter }
    comp_write_path = os.path.join(shot_dir, g_shot_comp_render_dir.format(**comp_render_dir_dict), "%s.%s.%s"%(temp_nuke_script_starter, g_write_frame_format, g_write_extension))
    log.info("About to open: %s"%stub)
    nuke.scriptOpen(stub)
    log.info("Shot template loaded.")
    bd_node = nuke.toNode("BackdropNode1")
    bd_node_w = nuke.toNode("BackdropNode2")
    main_read = nuke.toNode("Read1")
    main_write = nuke.toNode("Write_exr")

    # set the values in the template
    file_base = os.path.splitext(os.path.basename(mainref))[0]
    log.info('Adding main movie file %s to script.'%mainref)
    bd_node.knob('label').setValue("<center>%s"%file_base)
    main_read.knob('file').fromUserText(mainref)
    main_read.knob('colorspace').setValue(g_movie_colorspace)
    main_read.knob('frame_mode').setValue('offset')
    main_read.knob('frame').setValue(str(-1*g_movie_frame_offset))

    start_frame = int(main_read.knob('first').value()) + g_movie_frame_offset
    end_frame = int(main_read.knob('last').value()) + g_movie_frame_offset
    head_in = start_frame + int(config.get('scan_ingest', 'head_in_offset'))
    tail_out = end_frame + int(config.get('scan_ingest', 'tail_out_offset'))
    log.debug(str(start_frame))
    log.debug(str(head_in))
    log.debug(str(tail_out))
    log.debug(str(end_frame))
    nuke.root().knob('first_frame').setValue(head_in)
    nuke.root().knob('last_frame').setValue(tail_out)
    nuke.root().knob('txt_ih_show').setValue(g_ih_show_code)
    nuke.root().knob('txt_ih_show_path').setValue(g_ih_show_root)
    nuke.root().knob('txt_ih_seq').setValue(seq)
    nuke.root().knob('txt_ih_seq_path').setValue(seq_dir)
    nuke.root().knob('txt_ih_shot').setValue(shot)
    nuke.root().knob('txt_ih_shot_path').setValue(shot_dir)
    main_write.knob('file').setValue(comp_write_path)
    bd_node_w.knob('label').setValue("<center>%s\ncomp output"%shot)

    last_read = main_read
    last_read_xpos = 80
    last_bd_xpos = -69
    last_bd = bd_node
    
    # bring in any additional plates
    for addlref in addl_refs:

        log.info('Adding additional reference movie %s to script.'%addlref)
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

        new_plate_base = os.path.splitext(os.path.basename(addlref))[0]
    
        new_bd.knob('label').setValue("<center>%s"%new_plate_base)
        new_read.knob('file').fromUserText(addlref)
        new_read.knob('colorspace').setValue(g_movie_colorspace)
        new_read.knob('frame_mode').setValue('offset')
        new_read.knob('frame').setValue(str(-1*g_movie_frame_offset))
        
        last_read = new_read
        last_read_xpos = new_read_xpos
        last_bd = new_bd
        last_bd_xpos = new_bd_xpos
        
log.info("About to save Nuke script %s..."%output_script)
ret_val = nuke.scriptSaveAs(filename = output_script, overwrite = 1)
if ret_val:
    log.error("Something went wrong.")
    log.error(ret_val)
    log.error(sys.last_type)
    log.error(sys.last_value)
    log.error(sys.last_traceback)
else:
    log.info("Successfully wrote out Nuke script at %s!"%output_script)
nuke.scriptClose()

    
    
        




