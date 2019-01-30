#!/usr/local/bin/python

import argparse
import delivery
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--gui', help='Launches the GUI version of the application', action='store_true')
parser.add_argument('--hires', help='Creates a hi-resolution delivery instead of a Quicktime-only delivery', action='store_true')
parser.add_argument('--interactive', help='Will prompt the user for version removal in the Terminal', action='store_true')
parser.add_argument('--noemail', help='Will not sync or send email', action='store_true')
parser.add_argument('--matte', help='Creates a matte delivery', action='store_true')
parser.add_argument('--combined', help='Delivers both high resolution and movie files', action='store_true')
parser.add_argument('--playlistonly', help='Only creates a playlist in the database, does not actually perform the submission or copy data', action='store_true')
parser.add_argument('--deliveryonly', help='Assumes that you have already reviewed shots, and want to copy media and send email. Allows user to pick from a list of playlists.', action='store_true')
args = parser.parse_args()

b_gui = False
b_hires = False
b_interactive = False
b_email = True
b_matte = False
b_combined = False
b_playlistonly = False
b_deliveryonly = False

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
    
delivery.globals_from_config()

if b_gui:
    delivery.display_window(m_2k=b_hires, send_email=b_email, m_matte=b_matte, m_combined=b_combined, m_playlistonly=b_playlistonly, m_deliveryonly=b_deliveryonly)
else:
    delivery.execute_shell(m_interactive=b_interactive, m_2k=b_hires, send_email=b_email, m_matte=b_matte, m_combined=b_combined, m_playlistonly=b_playlistonly, m_deliveryonly=b_deliveryonly)

    