#!/usr/local/bin/python

import os
import sys
import requests
import ConfigParser

lutpath = ''

if len(sys.argv) < 2:
    sys.stderr.write('Usage: lut_convert.py /path/to/lut.cube\n')
    exit()

lutpath = sys.argv[1]

if not os.path.exists(lutpath):
    sys.stderr.write('Error: Path provided does not exist!\n')
    sys.stderr.write('Usage: lut_convert.py /path/to/lut.cube\n')
    exit(-1)

if os.path.isdir(lutpath):
    sys.stderr.write('Error: Path provided is a directory!\n')
    sys.stderr.write('Usage: lut_convert.py /path/to/lut.cube\n')
    exit(-2)

if not os.path.splitext(lutpath)[1] == '.cube':
    sys.stderr.write('Error: Only .cube files are supported at this time.\n')
    sys.stderr.write('Usage: lut_convert.py /path/to/lut.cube\n')
    exit(-3)

json_dict = {'destination_lut_format': 'csp',
             'filepath': lutpath,
             'overwrite': 'True'}

g_ih_show_code = None
g_ih_show_root = None
g_ih_show_cfg_path = None
g_lut_transcode_url = None

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
    g_lut_transcode_url = config.get('scan_ingest', 'lut_transcode_url')
except:
    g_lut_transcode_url = 'http://glenrothes.qppe.tech/vfxbot/lut_convert'

response = requests.post(g_lut_transcode_url, json=json_dict)
if response.status_code != 200:
    sys.stderr.write('Error: Errors occurred while attempting to transcode the LUT.\n')
    sys.stderr.write(str(response.json()))
    sys.stderr.write('\n')
    exit(-4)
else:
    destination_lut_file = response.json()['destination_lut_file']
    sys.stdout.write('Success!\n')
    sys.stdout.write('Transcoded LUT path: %s\n' % destination_lut_file)
    exit()

