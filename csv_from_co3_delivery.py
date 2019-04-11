#!/usr/bin/python

import os
import csv
import sys
import re

# currently a one-off, only set up to work for ROMEO.

headers = ['Version Name',
           'Link',
           'Task',
           'Type',
           'Submitted For',
           'Description',
           'First Frame Text',
           'Last Frame Text',
           'Frame Count Text']

dirpath = ''

if len(sys.argv) < 2:
    print('Usage: csv_from_co3_delivery.py /path/to/delivery/folder')
    exit()
dirpath = sys.argv[1]

if not os.path.exists(dirpath):
    print('Usage: csv_from_co3_delivery.py /path/to/delivery/folder')
    exit()

if not os.path.isdir(dirpath):
    print('Usage: csv_from_co3_delivery.py /path/to/delivery/folder')
    exit()

shot_regexp_txt = r'([0-9]{3}_[A-Z]{3}_[0-9]{4})_'
sequence_regexp_txt = r'([A-Z]{3})_'
imgseq_regexp_txt = r'\.([0-9]+)\.'

shot_regexp = re.compile(shot_regexp_txt)
sequence_regexp = re.compile(sequence_regexp_txt)
imgseq_regexp = re.compile(imgseq_regexp_txt)

master_files_dict = {}

def handle_file_copy(filepath):
    filename = os.path.basename(filepath)
    filename_array = filename.split('.')
    filebase = filename_array[0]
    if len(filebase) < 1:
        return
    fileext = filename_array[-1]
    if fileext not in ['exr', 'dpx', 'mov', 'cube']:
        return
    tmp_file_dict = None
    try:
        tmp_file_dict = master_files_dict[filebase]
    except KeyError:
        tmp_file_dict = {'base' : filebase,
                         'ext' : fileext,
                         'frames' : [],
                         'type' : None,
                         'link' : None,
                         'task' : None,
                         'formats' : []}
        master_files_dict[filebase] = tmp_file_dict
    tmp_format_spec = None
    if fileext == 'exr':
        tmp_format_spec = 'imgseq_plate'
    elif fileext == 'mov':
        tmp_format_spec = 'movie_plate'
    elif fileext == 'cube':
        tmp_format_spec = 'lut_plate'
    elif fileext == 'dpx':
        tmp_format_spec = 'imgseq_plate'
    if tmp_format_spec not in master_files_dict[filebase]['formats']:
        master_files_dict[filebase]['formats'].append(tmp_format_spec)

    imgseq_match = imgseq_regexp.search(filename)
    if imgseq_match:
        master_files_dict[filebase]['frames'].append(imgseq_match.group(1))

    shot_match = shot_regexp.search(filebase)
    if shot_match:
        master_files_dict[filebase]['type'] = 'Shot'
        master_files_dict[filebase]['link'] = shot_match.group(1)
        master_files_dict[filebase]['task'] = 'Final'
    else:
        sequence_match = sequence_regexp.search(filename)
        if sequence_match:
            master_files_dict[filebase]['type'] = 'Sequence'
            master_files_dict[filebase]['link'] = sequence_match.group(1)
            master_files_dict[filebase]['task'] = 'Ingest'
        else:
            master_files_dict[filebase]['type'] = 'Asset'
            master_files_dict[filebase]['link'] = 'Lens Grid'
            master_files_dict[filebase]['task'] = 'Ingest'

for dirname, subdirlist, filelist in os.walk(dirpath):
    for fname in filelist:
        handle_file_copy(os.path.join(dirname, fname))


dir_basename = os.path.basename(dirpath)

csv_filepath = os.path.join(dirpath, 'vfxpull_%s.csv'%dir_basename)

with open(csv_filepath, 'w') as csvfile:
    writer = csv.DictWriter(csvfile, fieldnames=headers)
    writer.writeheader()

    rowdict = None
    for version_code in sorted(master_files_dict.keys()):
        print('Adding version %s to CSV file...'%version_code)
        rowdict = {}
        rowdict['Version Name'] = version_code
        rowdict['Link'] = master_files_dict[version_code]['link']
        rowdict['Task'] = master_files_dict[version_code]['task']
        rowdict['Type'] = 'Scan'
        rowdict['Submitted For'] = 'Element'
        rowdict['Description'] = 'Scan Ingestion'
        rowdict['First Frame Text'] = ''
        rowdict['Last Frame Text'] = ''
        rowdict['Frame Count Text'] = ''
        if len(master_files_dict[version_code]['frames']) > 0:
            sorted_frames_array = sorted(master_files_dict[version_code]['frames'])
            rowdict['First Frame Text'] = sorted_frames_array[0]
            rowdict['Last Frame Text'] = sorted_frames_array[-1]
            rowdict['Frame Count Text'] = '%d'%len(sorted_frames_array)
        # rowdict['Formats'] = ', '.join(master_files_dict[version_code]['formats'])
        writer.writerow(rowdict)

print('Successfully wrote out CSV file %s.'%csv_filepath)




