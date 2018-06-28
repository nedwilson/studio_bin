#!/bin/bash

/Applications/Nuke11.1v1/Nuke11.1v1.app/Contents/MacOS/python /Applications/Nuke11.1v1/Nuke11.1v1.app/Contents/MacOS/pythonextensions/site-packages/foundry/frameserver/nuke/runframeserver.py --useInteractiveLicense --numworkers=12 --nukeworkerthreads=4 --nukeworkermemory=4096 --workerconnecturl=tcp://ichiro:5560 --nukepath=/Applications/Nuke11.1v1/Nuke11.1v1.app/Contents/MacOS/Nuke11.1v1

