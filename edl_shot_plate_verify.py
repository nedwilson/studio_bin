#!/usr/local/bin/python

import sys
sys.path.insert(0, '/usr/local/lib/python2.7/site-packages')

import glob
import shotgun_api3
from edl import Parser
import os
import logging
import csv
import ConfigParser
import pprint
import re
from datetime import datetime
import tempfile
import xlsxwriter
import copy
import timecode

import smtplib
import base64
import mimetypes


from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

from email.mime.image import MIMEImage
from email.mime.audio import MIMEAudio


B_EXR_LIBRARY_EXISTS = False
if os.path.exists('/usr/local/lib/python2.7/site-packages/OpenEXR.so'):
    sys.path.insert(0, '/usr/local/lib/python2.7/site-packages')
    B_EXR_LIBRARY_EXISTS = True
    import OpenEXR


logging.basicConfig(stream=sys.stdout, level=logging.DEBUG)
logging.info(str(sys.path))
parser=Parser('24')
edl_directory = r'/Volumes/romeo_primary/EDL_ALL'

version_names = []
all_edl_files = glob.glob(os.path.join(edl_directory, '*.edl'))
for edl_file in all_edl_files:
    logging.info('Examing EDL file at %s...'%edl_file)
    edl_base = os.path.basename(edl_file)
    with open(edl_file) as f:
        edl = parser.parse(f)
        for event in edl.events:
            if event.locator_name:
                logging.info('Found plate: %s'%event.locator_name)
                version_names.append([event.locator_name, edl_base])

plate_directory = r'/Volumes/romeo_primary/SHOTS/{sequence}/{shot}/img/plates'
lut_directory = r'/Volumes/romeo_primary/SHOTS/{sequence}/{shot}/data/color'
shot_directory = r'/Volumes/romeo_primary/SHOTS/{sequence}/{shot}'

g_ih_show_code = os.environ['IH_SHOW_CODE']
g_ih_show_root = os.environ['IH_SHOW_ROOT']
g_ih_show_cfg_path = os.environ['IH_SHOW_CFG_PATH']
g_config = ConfigParser.ConfigParser()
g_config.read(g_ih_show_cfg_path)

g_shotgun_api_key = g_config.get('database', 'shotgun_api_key')
g_shotgun_script_name = g_config.get('database', 'shotgun_script_name')
g_shotgun_server_path = g_config.get('database', 'shotgun_server_path')
g_romeo_shotgun_project_id = int(g_config.get('database', 'shotgun_production_project_id'))
g_sg = shotgun_api3.Shotgun(g_shotgun_server_path, g_shotgun_script_name, g_shotgun_api_key)

shot_regexp = re.compile(g_config.get('romeo', 'shot_regexp'))

# email configuration parameters
g_email_server = g_config.get('vfxbot', 'server')
g_email_port = int(g_config.get('vfxbot', 'port'))
g_email_useTLS = True if g_config.get('vfxbot', 'useTLS') in ['Y', 'y', 'YES', 'yes', 'Yes', 'T', 't', 'True', 'TRUE',
                                                              'true'] else False
g_email_username = g_config.get('vfxbot', 'username')
g_email_password = g_config.get('vfxbot', 'password')
# The from address that should be used in emails.
g_email_from = g_config.get('email', 'mail_from')
# A comma delimited list of email addresses to whom these alerts should be sent.
g_email_to = g_config.get('email', 'production_audit_to')
g_email_cc = g_config.get('email', 'production_audit_cc')
g_email_subject = g_config.get('email', 'production_audit_subject').format(date_format=datetime.now().strftime('%m/%d/%Y'))
g_email_message = g_config.get('email', 'production_audit_message').format(date_format=datetime.now().strftime('%m/%d/%Y')).replace('\\r', '\r')

if not g_email_port:
    g_email_port = smtplib.SMTP_PORT


# excel header format
l_subform_excel_header_format = g_config.get('delivery', 'subform_excel_header_format').split(',')
d_subform_excel_header_format = {}
for kvpair in l_subform_excel_header_format:
    names = kvpair.split('|')
    if names[1] == 'False':
        d_subform_excel_header_format[names[0]] = False
    elif names[1] == 'True':
        d_subform_excel_header_format[names[0]] = True
    else:
        d_subform_excel_header_format[names[0]] = names[1]

# excel data format
l_subform_excel_data_format = g_config.get('delivery', 'subform_excel_data_format').split(',')
d_subform_excel_data_format = {}
for kvpair in l_subform_excel_data_format:
    names = kvpair.split('|')
    if names[1] == 'False':
        d_subform_excel_data_format[names[0]] = False
    elif names[1] == 'True':
        d_subform_excel_data_format[names[0]] = True
    else:
        d_subform_excel_data_format[names[0]] = names[1]

# grab the shot from the database if the shot exists

headers = ['EDL File', 'Plate Name', 'Plate Message', 'Is Shot?', 'Shot', 'Shot Message', 'Scan Request',
           'Latest Delivery', 'Image Sequence Path', 'Start Frame', 'End Frame', 'LUT File',
           'Plate Transcoded?', 'LUT Converted?']
# logging.info(pprint.pprint(sorted(g_sg.schema_field_read('Version').keys())))
ver_fields = ['created_at', 'code', 'sg_path_to_frames', 'sg_scan_request', 'updated_at', 'playlists']
ver_filters = [['project', 'is', {'type' : 'Project', 'id' : g_romeo_shotgun_project_id}],
               ['code', 'is', None]]
csv_rows = []

shot_fields = ['id', 'code']
shot_filters = [['project', 'is', {'type' : 'Project', 'id' : g_romeo_shotgun_project_id}],
               ['code', 'is', None]]

for version_name_obj in version_names:
    version_name = version_name_obj[0]
    shot_match = shot_regexp.search(version_name)
    version_edl_file = version_name_obj[1]
    b_isshot = False
    version_shot = None
    rowdict = {'EDL File':version_edl_file,
               'Plate Name':version_name,
               'Plate Message':'ERROR',
               'Is Shot?':'NO',
               'Shot':'None',
               'Shot Message':'',
               'Scan Request':'',
               'Latest Delivery':'',
               'Image Sequence Path':'',
               'Start Frame':'',
               'End Frame':'',
               'LUT File':'',
               'Plate Transcoded?':'NO',
               'LUT Converted?':'NO'}
    csv_rows.append(rowdict)

    if shot_match:
        b_isshot = True
        rowdict['Is Shot?'] = 'YES'
        version_shot = shot_match.groupdict()['shot']
        rowdict['Shot'] = version_shot
        logging.info('Version %s matches shot %s.'%(version_name, version_shot))
        shot_filters[1][2] = version_shot
        sg_shot = g_sg.find_one('Shot', shot_filters, shot_fields)
        if sg_shot:
            rowdict['Shot Message'] = 'Found in Shotgun with DB ID = %d'%sg_shot['id']
        else:
            rowdict['Shot Message'] = 'ERROR: Shot not found in Shotgun!'
    else:
        rowdict['Shot Message'] = 'Clip does not match pattern for shot.'

    ver_filters[1][2] = version_name

    sg_version = g_sg.find_one('Version', ver_filters, ver_fields)
    plate_path = None

    if not sg_version:
        logging.warning('Unable to find record in the database for Version with name %s.'%version_name)
        rowdict['Plate Message'] = 'ERROR: Unable to locate plate in database!'
        continue
    else:
        logging.info('Found Version %s, ID %d, scan reqest %s, created at %s, path %s.'%(sg_version['code'], sg_version['id'], sg_version['sg_scan_request'], sg_version['created_at'], sg_version['sg_path_to_frames']))
        rowdict['Plate Message'] = 'Found in Shotgun with DB ID = %d'%sg_version['id']
        rowdict['Scan Request'] = sg_version['sg_scan_request']
        rowdict['Latest Delivery'] = sg_version['playlists'][0]['name'] if sg_version['playlists'] else ''
        if sg_version['sg_path_to_frames'] == None:
            rowdict['Image Sequence Path'] = ''
            rowdict['Plate Message'] = 'ERROR: Database record does not contain path to image sequence!'
            continue
        else:
            rowdict['Image Sequence Path'] = sg_version['sg_path_to_frames']
            plate_path = sg_version['sg_path_to_frames']

    if b_isshot:
        sequence = shot_match.groupdict()['sequence']
        plate_dir = plate_directory.format(shot = version_shot, sequence = sequence)
        lut_dir = lut_directory.format(shot = version_shot, sequence = sequence)
        shot_dir = shot_directory.format(shot = version_shot, sequence = sequence)
        if not os.path.exists(shot_dir):
            logging.error("No shot directory exists for shot %s!"%version_shot)
            rowdict['Shot Message'] = "ERROR: Shot directory not found."
            continue
        if not os.path.exists(plate_dir):
            logging.warning("No plate directory exists for shot %s!"%version_shot)
            rowdict['Shot Message'] = "ERROR: Plate directory not found."
            continue
        if not os.path.exists(lut_dir):
            logging.warning("No LUT directory exists for shot %s!"%version_shot)
            rowdict['Shot Message'] = "ERROR: LUT directory not found."
            continue

        plate_path_glob = plate_path.replace('%04d', '*')
        frames = sorted(glob.glob(plate_path_glob))
        framecount = len(frames)
        if len(frames) == 0:
            rowdict['Plate Message'] = 'ERROR: No image sequence found!'
            logging.error("No image sequence found for shot %s, plate %s!"%(version_shot, version_name))
            continue
        else:
            rowdict['Start Frame'] = frames[0].split('.')[-2]
            rowdict['End Frame'] = frames[-1].split('.')[-2]
        logging.info('Found image sequence at %s.'%plate_path_glob.replace('*', '%s-%s#'%(rowdict['Start Frame'], rowdict['End Frame'])))
        this_plate_lut = os.path.join(lut_dir, '%s.cube'%version_name)
        if not os.path.exists(this_plate_lut):
            rowdict['Plate Message'] = 'ERROR: No LUT found!'
            logging.warning("No LUT found for shot %s, plate %s."%(version_shot, version_name))
            continue
        else:
            rowdict['LUT File'] = this_plate_lut
            logging.info('LUT file for plate: %s'%this_plate_lut)
        this_plate_tc_lut = os.path.join(lut_dir, '%s.csp'%version_name)
        if not os.path.exists(this_plate_tc_lut):
            rowdict['Plate Message'] = 'ERROR: No converted LUT found!'
            logging.warning("No converted LUT found for shot %s, plate %s."%(version_shot, version_name))
            continue
        else:
            rowdict['LUT Converted?'] = 'YES'
            logging.info('Converted LUT file for plate: %s'%this_plate_tc_lut)

        transcode_dir = os.path.join(shot_dir, 'delivery', version_name, 'exr')
        logging.info('Searching for transcode directory %s...'%transcode_dir)
        if os.path.exists(transcode_dir):
            logging.info('Found transcode directory at %s.'%transcode_dir)
            transcode_plate_glob = os.path.join(transcode_dir, '%s.*.exr'%version_name)
            transcode_plate_frames = sorted(glob.glob(transcode_plate_glob))
            rowdict['3.2K Transcode Exists?'] = 'YES'
            if len(transcode_plate_frames) != framecount and len(transcode_plate_frames) != (framecount + 1):
                rowdict['Plate Message'] = 'ERROR: Transcoded plate exists but image sequence is incomplete.'
            else:
                if B_EXR_LIBRARY_EXISTS:
                    slate_file = OpenEXR.InputFile(transcode_plate_frames[0])
                    slate_tc_obj = slate_file.header().get('timeCode')
                    tmp_slate_frame = int(os.path.basename(transcode_plate_frames[0]).split('.')[-2])
                    # timecode.Timecode('24', start_timecode='00:01:22:23')
                    if slate_tc_obj:
                        slate_tc_str = "%02d:%02d:%02d:%02d" % (
                        slate_tc_obj.hours, slate_tc_obj.minutes, slate_tc_obj.seconds, slate_tc_obj.frame)
                        logging.info('Found frame %s with timecode %s.'%(os.path.basename(transcode_plate_frames[0]), slate_tc_str))
                        tmp_slate_frame = timecode.Timecode('24', start_timecode = slate_tc_str).frame_number
                    start_file = OpenEXR.InputFile(transcode_plate_frames[1])
                    start_tc_obj = start_file.header().get('timeCode')
                    tmp_start_frame = int(os.path.basename(transcode_plate_frames[2]).split('.')[-2])
                    if start_tc_obj:
                        start_tc_str = "%02d:%02d:%02d:%02d" % (
                            start_tc_obj.hours, start_tc_obj.minutes, start_tc_obj.seconds, start_tc_obj.frame)
                        logging.info('Found frame %s with timecode %s.' % (
                        os.path.basename(transcode_plate_frames[1]), start_tc_str))
                        tmp_start_frame = timecode.Timecode('24', start_timecode = start_tc_str).frame_number
                    if tmp_start_frame != (tmp_slate_frame + 1):
                        rowdict['Plate Message'] = 'ERROR: Transcoded plate has bad timecode values.'

        else:
            logging.warning('No transcoded plate exists for shot %s, plate %s.'%(version_shot, version_name))
            rowdict['Plate Message'] = 'ERROR: No transcoded plate exists.'

tmp_dir = tempfile.gettempdir()

report_xlsx_file = os.path.join(tmp_dir, datetime.now().strftime('Shot_Plate_Verification_%Y%m%d-%H%M%S.xlsx'))
logging.info("About to write out XLSX file: %s" % report_xlsx_file)
workbook = xlsxwriter.Workbook(report_xlsx_file)
worksheet = workbook.add_worksheet('Shot Plate Verification')
# column width hack
d_column_width = {}
d_subform_excel_header_format['align'] = 'left'
d_subform_excel_data_format['align'] = 'left'
header_format = workbook.add_format(d_subform_excel_header_format)
data_format = workbook.add_format(d_subform_excel_data_format)
d_subform_excel_error_format = copy.deepcopy(d_subform_excel_data_format)
d_subform_excel_error_format['font_color'] = 'red'
error_data_format = workbook.add_format(d_subform_excel_error_format)
# write headers
for header_idx, header_value in enumerate(headers):
    worksheet.write(0, header_idx, header_value, header_format)
    d_column_width[header_idx] = len(header_value)

row_idx = 1
for tmp_rowdict in csv_rows:
    tmp_data_format = data_format
    if tmp_rowdict['Plate Message'].startswith('ERROR') or tmp_rowdict['Shot Message'].startswith('ERROR'):
        tmp_data_format = error_data_format

    for idx, colname in enumerate(headers):
        colval = tmp_rowdict[colname]
        if not colval:
            colval = ''
        if len(colval) > d_column_width[idx]:
            d_column_width[idx] = len(colval)
        worksheet.write(row_idx, idx, colval, tmp_data_format)

    row_idx = row_idx + 1

# Set column widths correctly
for tmp_col_idx in d_column_width.keys():
    worksheet.set_column(tmp_col_idx, tmp_col_idx, d_column_width[tmp_col_idx] + 1)
workbook.close()

logging.info('Successfully wrote out XLSX file %s.'%report_xlsx_file)

logging.info('Sending email...')

# open the file to be sent
filepath = report_xlsx_file
filename = os.path.basename(filepath)

message = MIMEMultipart()
message['to'] = g_email_to
message['cc'] = g_email_cc
message['from'] = g_email_from
message['subject'] = g_email_subject

logging.info("Email Message: %s" % g_email_message)
message.attach(MIMEText(g_email_message))

logging.info("Creating message with attachment: file: %s" % filepath)
content_type, encoding = mimetypes.guess_type(filepath)

if content_type is None or encoding is not None:
    content_type = 'application/octet-stream'
main_type, sub_type = content_type.split('/', 1)
msg = None
if main_type == 'text':
    fp = open(filepath, 'rb')
    msg = MIMEText(fp.read(), _subtype=sub_type)
    fp.close()
elif main_type == 'image':
    fp = open(filepath, 'rb')
    msg = MIMEImage(fp.read(), _subtype=sub_type)
    fp.close()
elif main_type == 'audio':
    fp = open(filepath, 'rb')
    msg = MIMEAudio(fp.read(), _subtype=sub_type)
    fp.close()
else:
    fp = open(filepath, 'rb')
    msg = MIMEBase(main_type, sub_type)
    msg.set_payload(fp.read())
    fp.close()

msg.add_header('Content-Disposition', 'attachment', filename=filename)
message.attach(msg)

text = message.as_string()

# creates SMTP session
s = smtplib.SMTP(g_email_server, g_email_port)
# s.set_debuglevel(True)

# start TLS for security
s.starttls()

# Authentication
s.login(g_email_username, g_email_password)

# sending the mail
rcpt = g_email_cc.split(',') + g_email_to.split(',')

smtp_response = s.sendmail(g_email_from, rcpt, text)
logging.info('SMTP response: %s'%str(smtp_response))

# terminating the session
s.quit()

logging.info('Done.')


