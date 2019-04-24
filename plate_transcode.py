#!/usr/local/bin/python

import os
import sys
import requests
import ConfigParser
import glob
import re

platepath = ''

if len(sys.argv) < 2:
    sys.stderr.write('Usage: plate_transcode.py /path/to/exr/folder\n')
    exit(-10)

platepath = sys.argv[1]

if not os.path.exists(platepath):
    sys.stderr.write('Error: Path provided does not exist!\n')
    sys.stderr.write('Usage: plate_transcode.py /path/to/exr/folder\n')
    exit(-1)

if not os.path.isdir(platepath):
    sys.stderr.write('Error: Path provided is not a directory!\n')
    sys.stderr.write('Usage: plate_transcode.py /path/to/exr/folder\n')
    exit(-2)

exr_file_list = glob.glob(os.path.join(platepath, '*.exr'))

if len(exr_file_list) == 0:
    sys.stderr.write('Error: Please provide a folder containing an EXR image sequence\n')
    sys.stderr.write('Usage: plate_transcode.py /path/to/exr/folder\n')
    exit(-3)

g_ih_show_code = None
g_ih_show_root = None
g_ih_show_cfg_path = None
g_plate_transcode_url = None
g_imgseq_regexp = None

try:
    g_ih_show_code = os.environ['IH_SHOW_CODE']
    g_ih_show_root = os.environ['IH_SHOW_ROOT']
    g_ih_show_cfg_path = os.environ['IH_SHOW_CFG_PATH']
except KeyError:
    g_ih_show_cfg_path = '/Volumes/romeo_inhouse/romeo/SHARED/romeo/lib/romeo.cfg'
    g_ih_show_root = '/Volumes/romeo_inhouse/romeo'
    g_ih_show_code = 'romeo'

config = ConfigParser.ConfigParser()

try:
    config.read(g_ih_show_cfg_path)
    g_plate_transcode_url = config.get('scan_ingest', 'lut_transcode_url')
    g_imgseq_regexp = re.compile(config.get(g_ih_show_code, 'imgseq_regexp'))
except:
    g_plate_transcode_url = 'http://glenrothes.qppe.tech/vfxbot/lut_convert'
    g_imgseq_regexp = re.compile(r'^(?P<base>.+)\.(?P<frame>[0-9%a-z-]+)\.(?P<ext>[A-Za-z0-9]+)$')

# make sure that there is exactly one image sequence

imgseq_match = g_imgseq_regexp.search(os.path.basename(exr_file_list[0]))
imgseq_base = None

if not imgseq_match:
    sys.stderr.write('Error: Please provide a folder containing an EXR image sequence\n')
    sys.stderr.write('Usage: plate_transcode.py /path/to/exr/folder\n')
    exit(-5)
else:
    imgseq_base = imgseq_match.groupdict('base')

s_exr_file_list = sorted(exr_file_list)
for exr_file in s_exr_file_list:
    if os.path.basename(exr_file).find('%s.'%imgseq_base['base']) == -1:
        sys.stderr.write('Error: Please provide a folder containing only one EXR image sequence\n')
        sys.stderr.write('Usage: plate_transcode.py /path/to/exr/folder\n')
        exit(-6)

final_img_seq = os.path.join(platepath, '%s.%%04d.exr'%imgseq_base)
json_dict = {'filepath': final_img_seq,
             'overwrite': 'True'}

response = requests.post(g_plate_transcode_url, json=json_dict)
if response.status_code != 200:
    sys.stderr.write('Error: Errors occurred while attempting to transcode the plate.\n')
    sys.stderr.write(str(response.json()))
    sys.stderr.write('\n')
    exit(-4)
else:
    destination_filepath = response.json()['destination_filepath']
    sys.stdout.write('Success!\n')
    sys.stdout.write('Transcoded LUT path: %s\n' % destination_filepath)
    exit()

