#!/usr/bin/python

import os
import sys
import cdl_convert

def usage():
    print "Error: Please provide a path to a .cdl file as the first and only argument."
    print "Usage: cdl_to_cc.py /path/to/cdl/file.cdl"

if len(sys.argv) != 2:
    usage()
    exit()

cdl_file = sys.argv[1]
if not os.path.exists(cdl_file):
    usage()
    exit()

cdl_file_base = os.path.basename(os.path.splitext(cdl_file)[0])

cdl_convert.reset_all()
ccc = cdl_convert.parse_cdl(cdl_file)
cc = ccc.color_decisions[0].cc
cc.id=cdl_file_base
cc.determine_dest('cc',os.path.dirname(cdl_file))
cdl_convert.write_cc(cc)

print "Wrote out %s/%s.cc"%(os.path.dirname(cdl_file), cdl_file_base)
