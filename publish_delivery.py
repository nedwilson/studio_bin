#!/usr/local/bin/python

import argparse
import delivery
import sys

parser = argparse.ArgumentParser()
parser.add_argument('--gui', help='Launches the GUI version of the application', action='store_true')
parser.add_argument('--hires', help='Creates a hi-resolution delivery instead of a Quicktime-only delivery', action='store_true')
parser.add_argument('--interactive', help='Will prompt the user for version removal in the Terminal', action='store_true')
args = parser.parse_args()

b_gui = False
b_hires = False
b_interactive = False

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
    
delivery.globals_from_config()
# delivery.load_versions_for_status(delivery.g_version_status)

if b_gui:
    delivery.display_window(m_2k=b_hires)
else:
    delivery.execute_shell(m_interactive=b_interactive, m_2k=b_hires)

    