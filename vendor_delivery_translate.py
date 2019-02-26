#!/usr/local/bin/python

import os
import csv
import sys
import re
from openpyxl import load_workbook

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
    print('Usage: vendor_delivery_translate.py /path/to/delivery/folder')
    exit()
dirpath = sys.argv[1]

if not os.path.exists(dirpath):
    print('Usage: vendor_delivery_translate.py /path/to/delivery/folder')
    exit()

if not os.path.isdir(dirpath):
    print('Usage: vendor_delivery_translate.py /path/to/delivery/folder')
    exit()

shot_regexp_txt = r'([0-9]{3}_[A-Z]{3}_[0-9]{4})_'
sequence_regexp_txt = r'([A-Z]{3})_'
imgseq_regexp_txt = r'\.([0-9]+)\.'
version_name_regexp_text = r'([0-9]{3}_[A-Z]{3}_[0-9]{4}_[A-Za-z0-9\-_]+_v[0-9]+)'
version_regexp_text = r'_v([0-9]+)'

shot_regexp = re.compile(shot_regexp_txt)
sequence_regexp = re.compile(sequence_regexp_txt)
imgseq_regexp = re.compile(imgseq_regexp_txt)
version_name_regexp = re.compile(version_name_regexp_text)
version_regexp = re.compile(version_regexp_text)

filename_extras_regexp_text_list = [r'(.*)_vfx', r'(.*)_avid', r'(.*)_prores', r'(.*)_pr422', r'(.*)_matte']
filename_extras_regexp_list = [re.compile(pattern) for pattern in filename_extras_regexp_text_list]
master_files_list = []
subform_header_columns = []
subform_rows = []

def extract_excel(filepath):
    print('Info: Parsing XLSX file: %s'%filepath)
    wb = load_workbook(filepath)
    ws = wb[wb.sheetnames[0]]

    for header in ws.rows.next():
        subform_header_columns.append(header.value)

    for row in ws.iter_rows(min_row=2):
        rowdict = {}
        for idx, column in enumerate(row):
            rowdict[subform_header_columns[idx]] = column.value
        subform_rows.append(rowdict)
    old_filepath = os.path.join(os.path.dirname(filepath), '%s.bak'%os.path.splitext(os.path.basename(filepath))[0])
    print('Info: Saving out XLSX file as: %s'%old_filepath)
    os.rename(filepath, old_filepath)


def extract_csv(filepath):
    print('Info: Parsing CSV file: %s'%filepath)
    csvhandle = open(filepath, 'r')
    csvreader = csv.reader(csvhandle)
    for header in csvreader.next():
        subform_header_columns.append(header)
    for row in csvreader:
        rowdict = {}
        for idx, column in enumerate(row):
            rowdict[subform_header_columns[idx]] = column
        subform_rows.append(rowdict)
    csvhandle.close()
    old_filepath = os.path.join(os.path.dirname(filepath), '%s.bak'%os.path.splitext(os.path.basename(filepath))[0])
    print('Info: Saving out CSV file as: %s'%old_filepath)
    os.rename(filepath, old_filepath)


def check_file_naming(filepath):
    filename = os.path.basename(filepath)
    filedir = os.path.dirname(filepath)
    filename_array = filename.split('.')
    filebase = filename_array[0]
    if len(filebase) < 1:
        return
    fileext = filename_array[-1]
    if fileext == 'xlsx':
        extract_excel(filepath)
        return
    elif fileext == 'csv':
        extract_csv(filepath)
        return
    else:
        if fileext not in ['exr', 'dpx', 'mov', 'cube']:
            return
    filebase_new = filebase
    for filename_extra_regexp in filename_extras_regexp_list:
        filename_extra_match = filename_extra_regexp.search(filebase)
        if filename_extra_match:
            filebase_new = filename_extra_match.group(1)
            new_filename_array = filename_array
            new_filename_array[0] = filebase_new
            filename_destination = '.'.join(new_filename_array)
            print('Info: %s will be renamed to %s.'%(filename, filename_destination))
            os.rename(os.path.join(filedir, filename), os.path.join(filedir, filename_destination))

    master_files_list.append(filebase_new)

# make sure the directories are named correctly
directory_regexp_text_list = [r'(avid)', r'(vfx)', r'(exr)', r'(support_files)', r'(matte)']
directory_regexp_list = [re.compile(pattern) for pattern in directory_regexp_text_list]

directory_list = os.listdir(dirpath)
for file in directory_list:
    if os.path.isdir(os.path.join(dirpath, file)):
        for directory_regexp in directory_regexp_list:
            directory_regexp_match = directory_regexp.search(file)
            if directory_regexp_match:
                match_group = directory_regexp_match.group(1)
                if file != match_group:
                    print('Info: directory %s will be renamed to %s.'%(file, match_group))
                    os.rename(os.path.join(dirpath, file), os.path.join(dirpath, match_group))

for dirname, subdirlist, filelist in os.walk(dirpath):
    for fname in filelist:
        check_file_naming(os.path.join(dirname, fname))

uniq_master_files_list = sorted(set(master_files_list))
master_files_dict = {}
for file in uniq_master_files_list:
    tmp_file_dict = {'type' : None,
                     'link' : None,
                     'task' : None,
                     'subreason' : None,
                     'desc' : None,
                     'first' : None,
                     'last' : None,
                     'count' : None}
    print('Info: Found Version: %s'%file)
    master_files_dict[file] = tmp_file_dict
    version_match = version_regexp.search(file)
    if version_match:
        version_number = int(version_match.group(1))
        if version_number == 0:
            master_files_dict[file]['subreason'] = 'Scan Check'
        else:
            master_files_dict[file]['subreason'] = 'WIP Comp'

    shot_match = shot_regexp.search(file)
    if shot_match:
        master_files_dict[file]['type'] = 'Shot'
        master_files_dict[file]['link'] = shot_match.group(1)
        master_files_dict[file]['task'] = 'Final'
    else:
        sequence_match = sequence_regexp.search(file)
        if sequence_match:
            master_files_dict[file]['type'] = 'Sequence'
            master_files_dict[file]['link'] = sequence_match.group(1)
            master_files_dict[file]['task'] = 'R&D'
        else:
            print(
                'Warning: Unable to determine entity type for Version %s. Setting to Asset, but this will need to be manually adjusted.' % file)
            master_files_dict[file]['type'] = 'Asset'
            master_files_dict[file]['link'] = 'Miscellaneous'
            master_files_dict[file]['task'] = 'R&D'

    b_subform_match = False
    for subform_row in subform_rows:
        tmp_subform_version_code = ''
        try:
            tmp_subform_version_code = subform_row['Shot/Asset']
        except KeyError:
            print('Warning: Submission form does not have Shot/Asset column. Will try with Version Name instead.')
            try:
                tmp_subform_version_code = subform_row['Version Name']
            except KeyError:
                print('Warning: Submission form does not have Version Name column either. Skipping.')
                continue

        if tmp_subform_version_code.find(file) != -1:
            b_subform_match = True
            print('Info: Found record for %s in submission form.'%file)
            try:
                master_files_dict[file]['desc'] = subform_row['Submission Notes']
                master_files_dict[file]['first'] = subform_row['Comp Start Frame']
                master_files_dict[file]['last'] = subform_row['Comp End Frame']
                master_files_dict[file]['count'] = subform_row['Duration']
            except KeyError:
                print('Warning: This submission form does not have columns for one or more of the following: Submission Notes, Comp Start Frame, Comp End Frame, or Duration.')

    if not b_subform_match:
        master_files_dict[file]['desc'] = 'Shotgun Toolkit Create Delivery'


dir_basename = os.path.basename(dirpath)

csv_filepath = os.path.join(dirpath, '%s.csv'%dir_basename)
print('Info: Writing out CSV: %s'%csv_filepath)

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
        rowdict['Type'] = 'Comp'
        rowdict['Submitted For'] = master_files_dict[version_code]['subreason']
        rowdict['Description'] = master_files_dict[version_code]['desc']
        rowdict['First Frame Text'] = master_files_dict[version_code]['first']
        rowdict['Last Frame Text'] = master_files_dict[version_code]['last']
        rowdict['Frame Count Text'] = master_files_dict[version_code]['count']
        writer.writerow(rowdict)

print('Successfully wrote out CSV file %s.'%csv_filepath)




