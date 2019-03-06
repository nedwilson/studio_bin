#!/usr/local/bin/python

import argparse
import delivery
import sys
import logging
import os

parser = argparse.ArgumentParser(description='Command-line Python Tool that creates delivery packages and sends them to production.')
parser.add_argument('-g', '--gui', help='Launches the GUI version of the application', action='store_true')
parser.add_argument('-i', '--interactive', help='Will prompt the user for version removal in the Terminal', action='store_true')
parser.add_argument('-n', '--noemail', help='Will not sync or send email', action='store_true')
pkg_type_group = parser.add_mutually_exclusive_group()
pkg_type_group.add_argument('-r', '--hires', help='Creates a hi-resolution delivery instead of a Quicktime-only delivery', action='store_true')
pkg_type_group.add_argument('-m', '--matte', help='Creates a matte delivery', action='store_true')
pkg_type_group.add_argument('-c', '--combined', help='Delivers both high resolution and movie files', action='store_true')
two_step_delivery_group = parser.add_mutually_exclusive_group()
two_step_delivery_group.add_argument('-p', '--playlistonly', help='Only creates a playlist in the database, does not actually perform the submission or copy data', action='store_true')
two_step_delivery_group.add_argument('-d', '--deliveryonly', help='Assumes that you have already reviewed shots, and want to copy media and send email. Allows user to pick from a list of playlists.', action='store_true')
# deliver a specific playlist?
parser.add_argument('-l', '--playlist', help='Deliver this specific playlist to production, do not pick from a list of playlists.')
args = parser.parse_args()

b_gui = False
b_hires = False
b_interactive = False
b_email = True
b_matte = False
b_combined = False
b_playlistonly = False
b_deliveryonly = False
s_hero_playlist = None

if args.gui:
    b_gui = True
    print "INFO: Executing in GUI mode."
else:
    print "INFO: Executing in Terminal mode."
    
if args.hires:
    b_hires = True
    print "INFO: Building a hi-resolution delivery."
    
if args.interactive:
    b_interactive = True
    print "INFO: Executing in interactive mode - user will be prompted for versions to exclude."

if args.noemail:
    b_email = False
    print "INFO: Setting noemail to True - will not send email or sync delivery folder."

if args.combined:
    b_combined = True
    print "INFO: Setting combined to true - will include both movie files and high resolution images in this package."

if args.playlistonly:
    b_playlistonly = True
    print "INFO: Setting playlist only to true - will only build a playlist for this submission, will not copy data or actually build the submisson."

if args.deliveryonly:
    b_deliveryonly = True
    b_playlistonly = False
    print("INFO: Setting delivery only to true - will display a list of available playlists. Please pick one to deliver to production.")

if args.matte:
    b_matte = True
    b_hires = False
    print "INFO: Building a matte delivery."

if args.playlist:
    s_hero_playlist = args.playlist

homedir = os.path.expanduser('~')
logfile = ""
if sys.platform == 'win32':
    logfile = os.path.join(homedir, 'AppData', 'Local', 'IHPipeline', '%s.log' % 'publish_delivery')
elif sys.platform == 'darwin':
    logfile = os.path.join(homedir, 'Library', 'Logs', 'IHPipeline', '%s.log' % 'publish_delivery')
elif sys.platform == 'linux2':
    logfile = os.path.join(homedir, 'Logs', 'IHPipeline', '%s.log' % 'publish_delivery')
if not os.path.exists(os.path.dirname(logfile)):
    os.makedirs(os.path.dirname(logfile))
logFormatter = logging.Formatter("%(asctime)s:[%(threadName)s]:[%(levelname)s]:%(message)s")
log = logging.getLogger()
log.setLevel(logging.INFO)
try:
    devmode = os.environ['NUKE_DEVEL']
    log.setLevel(logging.DEBUG)
except:
    pass
fileHandler = logging.FileHandler(logfile)
fileHandler.setFormatter(logFormatter)
log.addHandler(fileHandler)
consoleHandler = logging.StreamHandler()
consoleHandler.setFormatter(logFormatter)
log.addHandler(consoleHandler)
log.info('Default log file path initialized to %s.' % logfile)

delivery.set_logger(log)
delivery.globals_from_config()

if b_gui:
    delivery.display_window(m_2k=b_hires, send_email=b_email, m_matte=b_matte, m_combined=b_combined, m_playlistonly=b_playlistonly, m_deliveryonly=b_deliveryonly, m_hero_playlist=s_hero_playlist)
else:
    delivery.execute_shell(m_interactive=b_interactive, m_2k=b_hires, send_email=b_email, m_matte=b_matte, m_combined=b_combined, m_playlistonly=b_playlistonly, m_deliveryonly=b_deliveryonly, m_hero_playlist=s_hero_playlist)

    