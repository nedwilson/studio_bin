#!/usr/bin/python

import sys
from openpyxl import load_workbook
import os
import ConfigParser

supported_filetypes = None
version_name_transforms = {}
shot_name_ch = None
version_name_ch = None
note_body_ch = None
l_notes = []

spreadsheet_file = ""
config = None

def usage(message):
    global supported_filetypes
    print """
Error: %s

This Python script is designed to take a spreadsheet containing notes and import them into a database.

Usage: note_ingest.py /path/to/spreadsheet.xlsx

Supported file types: %s
"""%(message, ', '.join(supported_filetypes))
    return

def load_config():
    global config
    if config == None:
        config = ConfigParser.ConfigParser()
        show_config_path = None
        try:
            show_config_path = os.environ['IH_SHOW_CFG_PATH']
        except KeyError:
            raise RuntimeError("This system does not have an IH_SHOW_CFG_PATH environment variable defined.")
        if not os.path.exists(show_config_path):
            raise RuntimeError("The IH_SHOW_CFG_PATH environment variable is defined on this system with value %s, but no file exists at that location."%show_config_path)
        try:
            config.read(show_config_path)
        except:
            raise
 
def open_spreadsheet():
    global spreadsheet_file
    global version_name_ch
    global shot_name_ch
    global note_body_ch
    global l_notes
    global version_name_transforms
    
    wb = load_workbook(spreadsheet_file)
    ws = wb[wb.sheetnames[0]]
    colnames = [shot_name_ch, version_name_ch, note_body_ch]
    col_indices = {n: cell.value for n, cell in enumerate(ws.rows.next()) 
               if cell.value in colnames}
    
    for row in ws.iter_rows(min_row=2):
        d_tmp_note = {}
        for index, cell in enumerate(row):
            if index in col_indices:
                if col_indices[index] == shot_name_ch:
                    d_tmp_note['shot_name'] = cell.value
                elif col_indices[index] == version_name_ch:
                    version_name = cell.value
                    for strxf in version_name_transforms.keys():
                        version_name = version_name.replace(strxf, version_name_transforms[strxf])
                    d_tmp_note['version_name'] = version_name
                elif col_indices[index] == note_body_ch:
                    d_tmp_note['note_body'] = cell.value
        l_notes.append(d_tmp_note)
    
    print l_notes
    
def insert_notes():
    pass

# make sure that there is one command line argument, which is the path to a valid spreadsheet
if __name__ == "__main__":

    if len(sys.argv) < 2:
        usage("Please provide a path to a valid spreadsheet file as the first command line argument.")
        exit()
    spreadsheet_file = sys.argv[1]
    if not os.path.exists(spreadsheet_file):
        usage("The path to the file provided on the command line does not exist.")
        exit()
    spreadsheet_ext = os.path.splitext(spreadsheet_file)[1]

    try:
        load_config()
        supported_filetypes = config.get('note_ingest', 'supported_filetypes').split(',')
        for xf in config.get('note_ingest', 'version_name_transforms').split(','):
            version_name_transforms[xf.split('|')[0]] = xf.split('|')[1]
        shot_name_ch = config.get('note_ingest', 'shot_name')
        version_name_ch = config.get('note_ingest', 'version_name')
        note_body_ch = config.get('note_ingest', 'note_body')
    except:
        usage(sys.exc_info()[1])
        exit()
        
    if not spreadsheet_ext in supported_filetypes:
        usage("Spreadsheet file type provided on command line is not supported.")
        exit()

    open_spreadsheet()
    insert_notes()
        
        
    
