#!/usr/local/bin/python

# ssl certificate verify hack

import ssl
ssl._create_default_https_context = ssl._create_unverified_context

import sys
import os
import difflib
import re
import ConfigParser
import csv
import logging
import traceback
import operator
import shutil
import glob
import subprocess
import sgtk
import OpenEXR
import thumbnails

import db_access as DB
from ccdata import CCData
from timecode import TimeCode

# PyQt5

from PyQt5.QtWidgets import *
from PyQt5.QtCore import *
from PyQt5.QtGui import *

g_path = None

homedir = os.path.expanduser('~')
logfile = ""
if sys.platform == 'win32':
    logfile = os.path.join(homedir, 'AppData', 'Local', 'IHPipeline', 'scan_ingest_gui.log')
elif sys.platform == 'darwin':
    logfile = os.path.join(homedir, 'Library', 'Logs', 'IHPipeline', 'scan_ingest_gui.log')
elif sys.platform == 'linux2':
    logfile = os.path.join(homedir, 'Logs', 'IHPipeline', 'scan_ingest_gui.log')
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

# uses mediainfo binary (need homebrew/mediainfo for this to work) to return info about a Quicktime
def quicktime_mediainfo(mov_path):
    d_mediainfo = {}
    if not os.path.exists(mov_path):
        raise IOError("Path provided as first argument %s does not exist!")
    proc = subprocess.Popen(['mediainfo',mov_path],stdout=subprocess.PIPE)
    while proc.poll() is None:
        continue
    lines = proc.stdout.read()
    for line in lines.split('\n'):
        if ':' in line:
            mi_line = line.split(':')
            mi_key = mi_line[0].strip()
            mi_value = mi_line[1].strip()
            d_mediainfo[mi_key] = mi_value
            log.debug('quicktime_mediainfo: setting %s = %s'%(mi_key, mi_value))
    return d_mediainfo

# uses Python's csv module to parse a string with comma-separated values. 
# returns a list
def read_csv_string(parse_string):
    if not parse_string or len(parse_string) == 0:
        raise ValueError("read_csv_string(): parse_string must be a valid text string.")
    lines = parse_string.splitlines()
    rdr = csv.reader(lines, quotechar='"', delimiter=',', quoting=csv.QUOTE_ALL, skipinitialspace=True)
    ret_list = None
    for row in rdr:
        ret_list = row
    return ret_list

# basic command line usage
def usage():
    print ""
    print "scan_ingest_gui.py PATH_TO_FOLDER"
    print ""
    print "Where PATH_TO_FOLDER is a path to a directory that contains images, color correction files, PDF files, etc."

# this function only used if preserve case is specified
def do_nothing(str_value):
    return str_value

class IngestObject():

    def __init__(self):
    
        self.full_name = ""
        self.source_dir = ""
        self.element_name = ""
        self.type = ""
        self.frames = []
        self.is_seq = False
        self.regexp_pattern = ""
        self.scope = "show"
        self.parent_name = ""
        self.parent_wd = ""
        self.dest_dir = ""
        self.extension = ""
        self.dest_name = ""
        self.start_frame = -1
        self.end_frame = -1
        self.start_delim = '.'
        self.end_delim = '.'
        self.parent_dbobject = None
        self.dbobject = None
        self.thumbnail_path = ""
        self.is_mainplate = False

    def get_full_name(self):
        t_full_name = ""
        sframes = sorted(self.frames)
        if len(self.frames) == 0:
            t_full_name = self.full_name
        else:
            log.debug("Regular Expression Pattern - %s"%self.regexp_pattern)
            log.debug("Full Name - %s"%self.full_name)
            match = re.search(self.regexp_pattern.replace('(\d+)', '(.*)'), self.full_name)
            if match:
                log.debug("Regexp match successful.")
                if len(sframes) == 1:
                    t_full_name = os.path.join(self.source_dir, "%s%s%s%s%s"%(match.group(1), match.group(2), match.group(3)%int(sframes[0]), match.group(4), match.group(5)))
                else:
                    t_full_name = os.path.join(self.source_dir, "%s%s%s-%s#%s%s"%(match.group(1), match.group(2), match.group(3)%int(sframes[0]), match.group(3)%int(sframes[-1]), match.group(4), match.group(5)))
            else:
                t_full_name = self.full_name
        return t_full_name

    def get_base_name(self):
        global log
        t_base_name = ""
        sframes = sorted(self.frames)
        if len(self.frames) == 0:
            t_base_name = os.path.basename(self.full_name)
        else:
            log.debug("Regular Expression Pattern - %s"%self.regexp_pattern)
            log.debug("Full Name - %s"%self.full_name)
            match = re.search(self.regexp_pattern.replace('(\d+)', '(.*)'), self.full_name)
            if match:
                log.debug("Regexp match successful.")
                if len(sframes) == 1:
                    t_base_name = "%s%s%s%s%s"%(match.group(1), match.group(2), match.group(3)%int(sframes[0]), match.group(4), match.group(5))
                else:
                    t_base_name = "%s%s%s-%s#%s%s"%(match.group(1), match.group(2), match.group(3)%int(sframes[0]), match.group(3)%int(sframes[-1]), match.group(4), match.group(5))
            else:
                t_base_name = os.path.basename(self.full_name)
        return t_base_name
        
    def __repr__(self):
    
        if self.is_seq:
            return "%s - Image Sequence - %d Frames"%(self.get_base_name(), len(self.frames))
        else:
            return "%s"%self.get_base_name()
            
    def obj_debug_info(self):
        tmp_is_seq = 'False'
        if self.is_seq:
            tmp_is_seq = 'True'
        ret_str = """{
    full_name : %s,
    source_dir : %s,
    element_name : %s,
    type : %s,
    frames : %s,
    is_seq : %s,
    regexp_pattern : %s,
    scope : %s,
    parent_name : %s,
    parent_wd : %s,
    dest_dir : %s,
    extension : %s,
    dest_name : %s,
    start_frame : %s,
    end_frame : %s,
    start_delim : %s,
    end_delim : %s
}"""%(
        self.full_name,
        self.source_dir,
        self.element_name,
        self.type,
        self.frames,
        tmp_is_seq,
        self.regexp_pattern,
        self.scope,
        self.parent_name,
        self.parent_wd,
        self.dest_dir,
        self.extension,
        self.dest_name,
        self.start_frame,
        self.end_frame,
        self.start_delim,
        self.end_delim)
        
        return ret_str

class CheckBoxDelegate(QItemDelegate):
    """
    A delegate that places a fully functioning QCheckBox cell of the column to which it's applied.
    """
    def __init__(self, parent):
        QItemDelegate.__init__(self, parent)

    def createEditor(self, parent, option, index):
        """
        Important, otherwise an editor is created if the user clicks in this cell.
        """
        return None

    def paint(self, painter, option, index):
        """
        Paint a checkbox without the label.
        """
        self.drawCheck(painter, option, option.rect, Qt.Unchecked if int(index.data()) == 0 else Qt.Checked)

    def editorEvent(self, event, model, option, index):
        '''
        Change the data in the model and the state of the checkbox
        if the user presses the left mousebutton and this cell is editable. Otherwise do nothing.
        '''
        #         if not int(index.flags() & Qt.ItemIsEditable) > 0:
        #             print 'Item not editable'
        #             return False

        if event.type() == QEvent.MouseButtonRelease and event.button() == Qt.LeftButton:
            # Change the checkbox-state
            self.setModelData(None, model, index)
            return True

        return False


    def setModelData (self, editor, model, index):
        '''
        The user wanted to change the old state in the opposite.
        '''
        model.setData(index, True if int(index.data()) == 0 else False, Qt.EditRole)

class ComboBoxDelegate(QItemDelegate):
    """
    A delegate that places a fully functioning QComboBox in every
    cell of the column to which it's applied
    """
    def __init__(self, parent):

        QItemDelegate.__init__(self, parent)
        self.items = []
        
    def setItems(self, list):
        self.items = list
        
    def createEditor(self, parent, option, index):
        combo = QComboBox(parent)
        combo.addItems(self.items)
        combo.currentIndexChanged.connect(self.currentIndexChanged)
        return combo

    def setEditorData(self, editor, index):
        array_index = 0
        try:
            array_index = self.items.index(index.model().data(index, Qt.DisplayRole))
        except:
            pass
        editor.blockSignals(True)
        editor.setCurrentIndex(array_index)
        # editor.setCurrentItem(editor.item(array_index))
        editor.blockSignals(False)
            

    def setModelData(self, editor, model, index):
        # print "Calling setModelData()", editor, index.data()
        model.setData(index, self.items[editor.currentIndex()], Qt.EditRole)
        
#     def paint(self, painter, option, index):
#         # text = self.items[index.row()]
#         option.text = index.data()
#         QApplication.style().drawControl(QStyle.CE_ItemViewItem, option, painter)

    @pyqtSlot()
    def currentIndexChanged(self):
        self.commitData.emit(self.sender())

    def updateEditorGeometry(self, editor, option, index):
        r = option.rect
        r.setSize(editor.sizeHint())
        editor.setGeometry(r)

class LineEditDelegate(QItemDelegate):
    def __init__(self, parent):

        QItemDelegate.__init__(self, parent)

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        # editor.setEnabled(True)
        # editor.editingFinished.connect(self.editingFinishedCustomEditor)
        # editor.returnPressed.connect(self.returnPressedCustomEditor)
        return editor

    def setEditorData(self, editor, index):
        if editor:
            editor.setText(index.model().data(index, Qt.DisplayRole))
            # editor.selectAll()

    def setModelData(self, editor, model, index):
        if editor:
            model.setData(index, editor.text(), Qt.EditRole)
                
class ScanIngestWindow(QMainWindow):
    def __init__(self):
        super(ScanIngestWindow, self).__init__()
        global g_object_scope_list, g_dest_type_dict
        self.setWindowTitle('Scan Ingestion')
        self.setMinimumSize(1920,1080)
    
        # central widget
        self.widget = QWidget()
        self.setCentralWidget(self.widget)
        self.layout = QVBoxLayout()
        self.widget.setLayout(self.layout)
        
        self.layout_mid = QHBoxLayout()

        # QTableView for ingest object list
        self.table_model = IngestTableModel(self, self.table_data(), self.table_header())
        self.table_model.validation_error.connect(self.validation_error_slot)
        self.table_model.output_change.connect(self.output_change_slot)
        self.table_view = QTableView()
        self.table_view.setModel(self.table_model)
        self.table_view.setSortingEnabled(True)
        delegate = CheckBoxDelegate(self)
        mp_delegate = CheckBoxDelegate(self)
        scb_delegate = ComboBoxDelegate(self)
        scb_delegate.setItems(g_object_scope_list)
        parent_delegate = LineEditDelegate(self)
        typecb_delegate = ComboBoxDelegate(self)
        typecb_delegate.setItems(g_dest_type_dict.keys())
        destpath_delegate = LineEditDelegate(self)
        self.table_view.setItemDelegateForColumn(0, delegate)
        self.table_view.setItemDelegateForColumn(3, scb_delegate)
        self.table_view.setItemDelegateForColumn(4, parent_delegate)
        self.table_view.setItemDelegateForColumn(5, typecb_delegate)
        self.table_view.setItemDelegateForColumn(6, destpath_delegate)
        self.table_view.setItemDelegateForColumn(7, mp_delegate)
        for i in range(self.table_model.rowCount(None)):
            self.table_view.openPersistentEditor(self.table_model.index(i, 3))
            # self.table_view.openPersistentEditor(self.table_model.index(i, 4))
            self.table_view.openPersistentEditor(self.table_model.index(i, 5))
            # self.table_view.openPersistentEditor(self.table_model.index(i, 6))
        self.table_view.resizeColumnsToContents()
        self.layout_mid.addWidget(self.table_view)
        self.layout.addLayout(self.layout_mid)

        # buttons at the bottom        
        self.layout_bottom = QHBoxLayout()
        self.buttons = QDialogButtonBox(self)
        self.buttons.setOrientation(Qt.Horizontal)
        self.buttons.setStandardButtons(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)     
        self.layout_bottom.addWidget(self.buttons)
        self.layout.addLayout(self.layout_bottom)
        width = 0
        for idx in range(0, len(self.table_model.header)):
            log.debug("Column %d width is %d"%(idx, self.table_view.sizeHintForColumn(idx)))
            width = width + self.table_view.sizeHintForColumn(idx)

        screenSize = QApplication.desktop().availableGeometry(self)
        if width >= screenSize.width:
            width = screenSize.width
        self.resize(width, 1080)
        self.results_window = ScanIngestResultsWindow(self)

    def reject(self):
        global g_cancel
        g_cancel = True
        print "INFO: User has cancelled operation."
        QCoreApplication.instance().quit()

    def process_ingest(self):
        global g_ingest_sorted, log, g_ih_show_root, g_ih_show_code, config, ihdb, g_seq_regexp, g_seq_dir_format, g_shot_dir_format, g_shot_thumb_dir, g_version_separator, g_version_format, g_cdl_file_ext
        self.hide()
        self.results_window.show()
        # dictionary object for thumbnails
        d_shot_thumbnail_files = {}
        default_ccobj = CCData()
        default_ccfile_from_cfg = config.get(g_ih_show_code, 'default_cc_%s'%sys.platform)
        if g_cdl_file_ext != 'cube':
            default_ccobj = CCData(default_ccfile_from_cfg)
        ccdir = config.get(g_ih_show_code, 'cdl_dir_format').format(pathsep = os.path.sep)
        ccext = config.get(g_ih_show_code, 'cdl_file_ext')
        mainplate_regexp = config.get(g_ih_show_code, 'mainplate_regexp')
        # step 0: populate start_frame and end_frame parameters of each scan ingest object, where appropriate
        for tmp_io in g_ingest_sorted:
            if tmp_io.is_seq:
                sorted_frames = sorted(tmp_io.frames)
                tmp_io.start_frame = int(sorted_frames[0])
                tmp_io.end_frame = int(sorted_frames[-1])

        try:
            # step 1: get a unique list of sequences and shots, create the ones that don't exist on the file system
            tmp_sequence_wds = [tmp_io.parent_wd for tmp_io in g_ingest_sorted if tmp_io.scope == 'sequence']
            tmp_sequence_wds_uniq = []
            for tmp_sequence_wd in tmp_sequence_wds:
                if tmp_sequence_wd not in tmp_sequence_wds_uniq:
                    tmp_sequence_wds_uniq.append(tmp_sequence_wd)
                    
            tmp_shot_wds = [tmp_io.parent_wd for tmp_io in g_ingest_sorted if tmp_io.scope == 'shot']
            tmp_shot_wds_uniq = []
            for tmp_shot_wd in tmp_shot_wds:
                if tmp_shot_wd not in tmp_shot_wds_uniq:
                    tmp_shot_wds_uniq.append(tmp_shot_wd)
                    
            for tmp_shot_wd in tmp_shot_wds_uniq:
                if not os.path.exists(tmp_shot_wd):
                    seq_wd = os.path.dirname(tmp_shot_wd)
                    if not os.path.exists(seq_wd):
                        log.info("Creating new sequence %s."%os.path.basename(seq_wd))
                        seq_stub_dir = config.get(g_ih_show_code, 'seq_stub_dir').format(show_root = g_ih_show_root, pathsep = os.path.sep)
                        shutil.copytree(seq_stub_dir, seq_wd)
                        log.info("Successfully created new sequence at %s"%seq_wd)
                        self.results_window.delivery_results.appendPlainText("INFO: Created new sequence on filesystem at %s."%seq_wd)
                        QApplication.processEvents()
                    log.info("Creating new shot %s."%os.path.basename(tmp_shot_wd))
                    shot_stub_dir = config.get(g_ih_show_code, 'shot_stub_dir').format(show_root = g_ih_show_root, pathsep = os.path.sep)
                    shutil.copytree(shot_stub_dir, tmp_shot_wd)
                    log.info("Successfully created new shot at %s"%tmp_shot_wd)
                    self.results_window.delivery_results.appendPlainText("INFO: Created new shot on filesystem at %s."%tmp_shot_wd)
                    log.info("Creating default color correction for shot.")
                    default_cc_file = os.path.join(tmp_shot_wd, ccdir, '%s.%s'%(os.path.basename(tmp_shot_wd), ccext))
                    log.info("Default color correction file: %s"%default_cc_file)
                    if g_cdl_file_ext == 'cube':
                        shutil.copyfile(default_ccfile_from_cfg, default_cc_file)
                        log.info('%s: %s -> %s' % ('copy', default_ccfile_from_cfg, default_cc_file))

                    else:
                        default_ccobj.get_write_function(ccext)(default_cc_file)
                    self.results_window.delivery_results.appendPlainText("INFO: Added default color correction file at %s."%default_cc_file)
                    QApplication.processEvents()
            for tmp_sequence_wd in tmp_sequence_wds_uniq:
                if not os.path.exists(tmp_sequence_wd):
                    log.info("Creating new sequence %s."%os.path.basename(tmp_sequence_wd))
                    seq_stub_dir = config.get(g_ih_show_code, 'seq_stub_dir').format(show_root = g_ih_show_root, pathsep = os.path.sep)
                    shutil.copytree(seq_stub_dir, tmp_sequence_wd)
                    log.info("Successfully created new sequence at %s"%tmp_sequence_wd)
                    self.results_window.delivery_results.appendPlainText("INFO: Created new sequence on filesystem at %s."%tmp_sequence_wd)
                    QApplication.processEvents()
            # step 2: copy/hardlink the files
            file_operation = config.get(g_ih_show_code, 'show_file_operation')
            write_frame_format = config.get(g_ih_show_code, 'write_frame_format')
            mainplate_re = re.compile(mainplate_regexp)
            imgseq_regexp = config.get(g_ih_show_code, 'imgseq_regexp')
            log.debug('Inside copy/hardlink loop')
            for tmp_io in g_ingest_sorted:
                log.info('Examining element %s.'%tmp_io.element_name)
                log.debug(tmp_io.obj_debug_info())
                if tmp_io.is_seq:
                    log.info('%s is an image sequence.'%tmp_io.element_name)
                    glob_path = os.path.join(tmp_io.source_dir, '%s%s*%s%s'%(tmp_io.element_name, tmp_io.start_delim, tmp_io.end_delim, tmp_io.extension))
                    destination_display_path = os.path.join(tmp_io.dest_dir, tmp_io.dest_name)
                    ddp_match = re.search(imgseq_regexp, destination_display_path)
                    if not ddp_match:
                        log.warning('Destination path %s does not match regular expression %s. Skipping.'%(destination_display_path, imgseq_regexp))
                        self.results_window.delivery_results.appendPlainText('WARNING: Destination path %s does not match regular expression %s. Skipping.'%(destination_display_path, imgseq_regexp))
                        QApplication.processEvents()
                        continue
                    ddp_glob = '%s.*.%s'%(ddp_match.group('base'), ddp_match.group('ext'))
                    log.info('%s: %s -> %s'%(file_operation, glob_path, ddp_glob))
                    self.results_window.delivery_results.appendPlainText("INFO: %s: from: %s"%(file_operation, glob_path))
                    self.results_window.delivery_results.appendPlainText("  TO: %s"%(ddp_glob))
                    QApplication.processEvents()
                    element_regexp = re.compile(tmp_io.regexp_pattern)
                    if not os.path.exists(tmp_io.dest_dir):
                        os.makedirs(tmp_io.dest_dir)
                    for source_file in glob.glob(glob_path):
                        element_regexp_match = element_regexp.search(source_file)
                        if not element_regexp_match:
                            log.warning('Source frame %s does not match regular expression %s. Skipping.'%(source_file, tmp_io.regexp_pattern))
                            self.results_window.delivery_results.appendPlainText('WARNING: Source frame %s does not match regular expression %s. Skipping.'%(source_file, tmp_io.regexp_pattern))
                            QApplication.processEvents()
                        else:
                            frame = int(element_regexp_match.group(3))
                            dest_full_path = destination_display_path%frame
                            if not os.path.exists(dest_full_path):
                                log.info('%s: %s -> %s'%(file_operation, source_file, dest_full_path))
                                if file_operation == "hardlink":
                                    os.link(source_file, dest_full_path)
                                elif file_operation == "copy":
                                    shutil.copyfile(source_file, dest_full_path)
                    log.info('Done.')
                    self.results_window.delivery_results.appendPlainText("INFO: Done.")
                    QApplication.processEvents()
                else:
                    ddp = os.path.join(tmp_io.dest_dir, tmp_io.dest_name)
                    log.info('%s: %s -> %s'%(file_operation, tmp_io.full_name, ddp))
                    self.results_window.delivery_results.appendPlainText("INFO: %s: from: %s"%(file_operation, tmp_io.full_name))
                    self.results_window.delivery_results.appendPlainText("  TO: %s"%(ddp))
                    QApplication.processEvents()
                    if not os.path.exists(tmp_io.dest_dir):
                        os.makedirs(tmp_io.dest_dir)
                    if not os.path.exists(ddp):
                        if file_operation == "hardlink":
                            os.link(tmp_io.full_name, ddp)
                        elif file_operation == "copy":
                            shutil.copyfile(tmp_io.full_name, ddp)
                            log.info('%s: %s -> %s' % ('copy', tmp_io.full_name, ddp))
                    log.info('Done.')
                    self.results_window.delivery_results.appendPlainText("INFO: Done.")
                    QApplication.processEvents()
                    # special case to handle color corrections
                    log.debug(tmp_io.full_name)
                    log.debug(tmp_io.type)
                    log.debug(tmp_io.scope)
                    log.debug(tmp_io.dest_name)
                    log.debug(mainplate_regexp)
                    if tmp_io.type == 'color correction' and tmp_io.scope == 'shot':
                        if tmp_io.is_mainplate:
                            default_cc_file = os.path.join(tmp_io.dest_dir, '%s.%s' % (tmp_io.parent_name, ccext))
                            if tmp_io.extension == 'cube':
                                log.info('This cube file has been flagged as a Main Plate. Will make the shot default cube file from it.')
                                log.info('%s: %s -> %s'%(file_operation, tmp_io.full_name, default_cc_file))
                                if file_operation == "hardlink":
                                    os.link(tmp_io.full_name, default_cc_file)
                                elif file_operation == "copy":
                                    shutil.copyfile(tmp_io.full_name, default_cc_file)
                                self.results_window.delivery_results.appendPlainText("INFO: Wrote out default CUBE file for shot at %s."%default_cc_file)
                                QApplication.processEvents()
                            else:
                                log.info('This cc file has been flagged as a Main Plate. Will make the shot default CC file from it.')
                                tmp_ccdata = CCData(ddp)
                                log.info('Default CC file: %s'%default_cc_file)
                                tmp_ccdata.get_write_function(ccext)(default_cc_file)
                                self.results_window.delivery_results.appendPlainText("INFO: Wrote out default CC file for shot at %s."%default_cc_file)
                                QApplication.processEvents()

            # step 3: query the database for unique shots
            uniq_shots = {}
            for tmp_io in g_ingest_sorted:
                if tmp_io.scope == 'shot':
                    if tmp_io.parent_name not in uniq_shots.keys():
                        seq_regexp = '(%s)'%g_seq_regexp
                        seq_match = re.search(seq_regexp, tmp_io.parent_name)
                        if not seq_match:
                            raise ValueError("Unable to get sequence name from shot name %s using regexp %s"%(tmp_io.parent_name, seq_regexp))
                        sequence = seq_match.group(1)
                        shot = tmp_io.parent_name
                        sequence_dir = g_seq_dir_format.format(show_root = g_ih_show_root, pathsep = os.path.sep, sequence = sequence)
                        shot_dir = g_shot_dir_format.format(show_root = g_ih_show_root, pathsep = os.path.sep, sequence = sequence, shot = shot)
                        dbseq = ihdb.fetch_sequence(sequence)
                        if not dbseq:
                            log.info("Creating new sequence %s at path %s."%(sequence, sequence_dir))
                            dbseq = DB.Sequence(sequence, sequence_dir, -1)
                            ihdb.create_sequence(dbseq)
                        
                        log.info("Got sequence %s object from database with ID of %s."%(dbseq.g_seq_code, dbseq.g_dbid))

                        dbshot = ihdb.fetch_shot(shot)
                        if not dbshot:
                            print "INFO: Creating new shot %s at path %s."%(shot, shot_dir)
                            io_obj_primary = None
                            for tmp_io_two in g_ingest_sorted:
                                if tmp_io_two.scope == 'shot' and tmp_io_two.parent_name == shot and tmp_io_two.extension in config.get('scan_ingest', 'movie_exts').split(','):
                                    if tmp_io_two.is_mainplate:
                                        log.info('Found a movie element %s that is a main plate.'%tmp_io_two.dest_name)
                                        io_obj_primary = tmp_io_two
                            for tmp_io_two in g_ingest_sorted:
                                if tmp_io_two.scope == 'shot' and tmp_io_two.parent_name == shot and tmp_io_two.extension in config.get('scan_ingest', 'lutted_image_exts').split(',') and tmp_io_two.is_seq:
                                    if tmp_io_two.is_mainplate:
                                        log.info('Found a high resolution element %s that matches is a main plate.'%tmp_io_two.dest_name)
                                        io_obj_primary = tmp_io_two
                            
                            
                            head_in = 1001
                            cut_in = 1009
                            cut_out = 1092
                            tail_out = 1100
                            cut_duration = 84
                            if io_obj_primary:
                                log.info('Setting boolean is_mainplate = True for element %s.'%io_obj_primary.dest_name)
                                log.debug(io_obj_primary.obj_debug_info())
                                io_obj_primary.is_mainplate = True
                                elem_start = io_obj_primary.start_frame
                                if io_obj_primary.extension in config.get('scan_ingest', 'movie_exts').split(','):
                                    elem_start = io_obj_primary.start_frame + int(config.get('scan_ingest', 'movie_frame_offset'))
                                elem_end = io_obj_primary.end_frame
                                if io_obj_primary.extension in config.get('scan_ingest', 'movie_exts').split(','):
                                    elem_end = io_obj_primary.end_frame + int(config.get('scan_ingest', 'movie_frame_offset'))
                                head_in = elem_start + int(config.get('scan_ingest', 'head_in_offset'))
                                cut_in = elem_start + int(config.get('scan_ingest', 'cut_in_offset'))
                                cut_out = elem_end + int(config.get('scan_ingest', 'cut_out_offset'))
                                tail_out = elem_end + int(config.get('scan_ingest', 'tail_out_offset'))
                                cut_duration = cut_out - cut_in + 1
                            self.results_window.delivery_results.appendPlainText('INFO: Creating new shot %s with editorial information head_in = %d, cut_in = %d, cut_out = %d, tail_out = %d, cut_duration = %d'%(shot, head_in, cut_in, cut_out, tail_out, cut_duration))
                            QApplication.processEvents()
                            log.info('Creating new shot %s with editorial information head_in = %d, cut_in = %d, cut_out = %d, tail_out = %d, cut_duration = %d'%(shot, head_in, cut_in, cut_out, tail_out, cut_duration))                                
                            dbshot = DB.Shot(shot, shot_dir, -1, dbseq, None, head_in, cut_in, cut_out, tail_out, cut_duration)
                            ihdb.create_shot(dbshot)
                            uniq_shots[tmp_io.parent_name] = { 'new_shot' : True, 'dbshot' : dbshot }
                        else:
                            uniq_shots[tmp_io.parent_name] = { 'new_shot' : False, 'dbshot' : dbshot }
                            
            for u_shot in uniq_shots.keys():
                for tmp_io in g_ingest_sorted:
                    if tmp_io.parent_name == u_shot and tmp_io.scope == 'shot':
                        tmp_io.parent_dbobject = uniq_shots[u_shot]['dbshot']
                        
            log.info('Successfully retrieved all shots from the database.')
            self.results_window.delivery_results.appendPlainText('INFO: Successfully retrieved all shots from the database.')
            QApplication.processEvents()
            
            # step 4: publish every shot-related element
            
            basic_thumbnail_path = None

            # EXR metadata keys
            cfg_exr_metadata_key_scene = config.get('scan_ingest', 'exr_metadata_key_scene')
            cfg_exr_metadata_key_slate = config.get('scan_ingest', 'exr_metadata_key_slate')
            cfg_exr_metadata_key_take = config.get('scan_ingest', 'exr_metadata_key_take')
            cfg_exr_metadata_key_reel_name = config.get('scan_ingest', 'exr_metadata_key_reel_name')
            cfg_exr_metadata_key_camera = config.get('scan_ingest', 'exr_metadata_key_camera')
            b_extract_scene_from_slate = False
            cfg_extract_scene_from_slate = config.get('scan_ingest', 'extract_scene_from_slate')
            if cfg_extract_scene_from_slate in ['Y', 'y', 'Yes', 'yes', 'YES', 'True', 'true', 'TRUE']:
                b_extract_scene_from_slate = True

            cfg_scene_regex = re.compile(config.get('scan_ingest', 'scene_regex'))
            cfg_scene_number_format = config.get('scan_ingest', 'scene_number_format')
            cfg_scene_format = config.get('scan_ingest', 'scene_format')
            cfg_take_format = config.get('scan_ingest', 'take_format')
            cfg_lowercase_camera_name = config.get('scan_ingest', 'lowercase_camera_name')
            if cfg_lowercase_camera_name in ['Y', 'y', 'Yes', 'yes', 'YES', 'True', 'true', 'TRUE']:
                b_lowercase_camera_name = True
            b_extract_take_from_metadata = False
            cfg_extract_take_from_metadata = config.get('scan_ingest', 'extract_take_from_metadata')
            if cfg_extract_take_from_metadata in ['Y', 'y', 'Yes', 'yes', 'YES', 'True', 'true', 'TRUE']:
                b_extract_take_from_metadata = True

            for tmp_io in g_ingest_sorted:
            
                if tmp_io.scope == 'shot' and tmp_io.extension in config.get('scan_ingest', 'lutted_image_exts').split(',') and tmp_io.is_seq:

                    # grab a toolkit object from the shot entity
                    dbshot = tmp_io.parent_dbobject
                    # retrive object from database for plate
                    dest_full_path = os.path.join(tmp_io.dest_dir, tmp_io.dest_name)
                    imgseq_match = re.search(imgseq_regexp, tmp_io.dest_name)
                    dest_base = ""
                    dest_ext = ""
                    if imgseq_match:
                        dest_base = imgseq_match.group('base')
                        dest_ext = imgseq_match.group('ext')
                    else:
                        raise ValueError('Ingest object %s does not match image sequence regexp!'%tmp_io.dest_name)
                    
                    log.debug(dbshot)
                    log.debug(dest_base)
                    log.debug(dbshot.g_dbid)    
                    dbplate = ihdb.fetch_plate(dest_base, dbshot)
                    shot_thumb_dir = os.path.join(tmp_io.parent_wd, g_shot_thumb_dir.format(pathsep=os.path.sep))

                    b_new_shot_thumb = False
                    if uniq_shots[tmp_io.parent_name]['new_shot']:
                        b_new_shot_thumb = True

                    if not dbplate:
                        log.info("Creating new plate %s for shot %s."%(dest_base, tmp_io.parent_name))
                        plate_name = dest_base
                        start_frame = tmp_io.start_frame
                        end_frame = tmp_io.end_frame
                        duration = (end_frame - start_frame + 1)
                        thumb_frame = start_frame + (duration/2)
                        plate_path = dest_full_path
                        start_file_path = dest_full_path%start_frame
                        end_file_path = dest_full_path%end_frame
                        thumb_frame_path = dest_full_path%thumb_frame
                        clip_name = plate_name
                        scene = ""
                        take = ""
                        take_number = ""
                        slate = ""
                        camera = ""
                        start_file = None
                        start_timecode = 0
                        b_metadata = False
                        try:
                            start_file = OpenEXR.InputFile(start_file_path)
                            start_timecode = int(start_frame)*1000
                            start_tc_obj = start_file.header()['timeCode']
                            if start_file.header()['Framerate']:
                                header_fps = float(start_file.header()['Framerate'])
                            else:
                                header_fps = float(start_file.header()['framesPerSecond'].n)/float(start_file.header()['framesPerSecond'].d)
                            start_timecode = int((TimeCode("%02d:%02d:%02d:%02d"%(start_tc_obj.hours, start_tc_obj.minutes, start_tc_obj.seconds, start_tc_obj.frame), inputfps=header_fps).frame_number() * 1000) / header_fps)
                            clip_name = start_file.header()[cfg_exr_metadata_key_reel_name]
                            scene = start_file.header()[cfg_exr_metadata_key_scene]
                            take = start_file.header()[cfg_exr_metadata_key_take]
                            take_number = start_file.header()[cfg_exr_metadata_key_take]
                            slate = start_file.header()[cfg_exr_metadata_key_slate]
                            if b_lowercase_camera_name:
                                camera = start_file.header()[cfg_exr_metadata_key_camera].lower()
                            else:
                                camera = start_file.header()[cfg_exr_metadata_key_camera]
                            # if we have gotten this far without throwing an exception, we can probably assume that there is valid metadata and this is an EXR file
                            b_metadata = True
                        except KeyError:
                            e = sys.exc_info()
                            log.warning("KeyError: metadata key %s not available in EXR file."%e[1])
                        except ValueError as ve:
                            log.error("%s"%ve.message)
                        except IOError as ioe:
                            log.warning("Image is not in EXR format.")
                        except AttributeError as atte:
                            log.warning("Caught AttributeError when trying to extract header information from EXR file.")
                            log.warning(atte.strerror)

                        # figure out the scene name, take name, etc.
                        if b_metadata:
                            log.info('This image sequence contains EXR files that have valid metadata.')
                            # should we try and extract the scene from the slate?
                            if b_extract_scene_from_slate:
                                log.info('Trying to extract the scene name from the slate metadata key.')
                                tmp_scene = ''
                                scene_re_match = cfg_scene_regex.search(slate)
                                if scene_re_match:
                                    log.info('Slate %s is a match for scene regular expression.'%slate)
                                    scene_match_dict = scene_re_match.groupdict()
                                    tmp_scene_number = cfg_scene_number_format%int(scene_match_dict['number'])
                                    tmp_scene = cfg_scene_format.format(prefix = scene_match_dict['prefix'], special = scene_match_dict['special'], number = tmp_scene_number)
                                    log.info('Determined scene to be %s.'%tmp_scene)
                                    scene = tmp_scene
                                else:
                                    log.info('Slate %s does not match regular expression %s.'%(slate, cfg_scene_regex.pattern))
                            if b_extract_take_from_metadata:
                                log.info('Trying to extract the take name from the metadata.')
                                tmp_take = cfg_take_format.format(slate = slate, take = take_number, camera = camera)
                                log.info('Determined take to be %s.'%tmp_take)
                                take = tmp_take

                        end_file = None
                        end_timecode = 0

                        try:
                            end_file = OpenEXR.InputFile(end_file_path)
                            end_tc_obj = end_file.header()['timeCode']
                            end_timecode = int((TimeCode("%02d:%02d:%02d:%02d"%(end_tc_obj.hours, end_tc_obj.minutes, end_tc_obj.seconds, end_tc_obj.frame)).frame_number() * 1000) / 24)
                        except KeyError:
                            e = sys.exc_info()
                            log.warning("KeyError: metadata key %s not available in EXR file."%e[1])
                        except IOError as ioe:
                            log.warning("Image is not in EXR format.")

                        dbplate = DB.Plate(plate_name, start_frame, end_frame, duration, plate_path, start_timecode, clip_name, scene, take, end_timecode, dbshot, -1)
                        dbplate.set_slate(slate)
                        ihdb.create_plate(dbplate)
    
                        # upload a thumbnail for the plate_name
                        # first, create a .PNG from the source...
                        generated_thumb_path = thumbnails.create_thumbnail(thumb_frame_path)
                        ihdb.upload_thumbnail('Plate', dbplate, generated_thumb_path)
                        log.info("Uploaded thumbnail %s to DB plate object %s."%(generated_thumb_path, dbplate.g_plate_name))

                        # publish the plate using the toolkit API
                        log.info('Publishing this plate to the database...')
                        dbpublishplate = None
                        try:
                            dbpublishplate = ihdb.publish_for_ingest(dbshot, plate_path, plate_name, 'Publish of plate by Scan Ingestion script', 'Plate')
                        except:
                            log.error("Caught exception when trying to publish a plate!")
                            log.error(sys.exc_info()[0])
                            log.error(sys.exc_info()[1])
                        # upload a thumbnail
                        if dbpublishplate:
                            log.info("Uploading thumbnail for publish.")
                            ihdb.upload_thumbnail('PublishedFile', dbplate, generated_thumb_path, altid = dbpublishplate['id'])
                        basic_thumbnail_path = generated_thumb_path
                        try:
                            tmp_thumb = d_shot_thumbnail_files[dbshot.g_shot_code]
                            if tmp_io.is_mainplate:
                                d_shot_thumbnail_files[dbshot.g_shot_code] = { 'path' : generated_thumb_path, 'hires_src' : True, 'mainplate' : True }
                        except KeyError:
                            d_shot_thumbnail_files[dbshot.g_shot_code] = { 'path' : generated_thumb_path, 'hires_src' : True, 'mainplate' : tmp_io.is_mainplate }

                        # upload a thumbnail for the plate to the shot, in the event that this is a new shot
                        if b_new_shot_thumb and tmp_io.is_mainplate:
                            shutil.copyfile(generated_thumb_path, thumbnails.get_thumbnail_for_shot(dbshot.g_shot_code))
                            log.info('%s: %s -> %s' % ('copy', generated_thumb_path, thumbnails.get_thumbnail_for_shot(dbshot.g_shot_code)))
                            ihdb.upload_thumbnail('Shot', dbshot, generated_thumb_path)
                            log.info("Uploaded thumbnail %s to DB shot object %s."%(generated_thumb_path, dbshot.g_shot_code))
                            uniq_shots[tmp_io.parent_name]['new_shot'] = False

                    log.info("Got plate %s object from database with ID of %s."%(dbplate.g_plate_name, dbplate.g_dbid))
                    self.results_window.delivery_results.appendPlainText('INFO: Published plate %s for shot %s.'%(dbplate.g_plate_name, dbshot.g_shot_code))

                    # make a version in the database for this shot
                    plate_thumb_glob = os.path.join(shot_thumb_dir, '%s_thumb.*.png'%(dest_base))
                    plate_thumb_path = None
                    for tmp_thumb_path in glob.glob(plate_thumb_glob):
                        plate_thumb_path = tmp_thumb_path

                    dbversion = ihdb.fetch_version(dest_base, dbshot)
                    if not dbversion:
                        dbversion = DB.Version(dest_base, -1, 'Element Version from Scan Ingest', dbplate.g_start_frame, dbplate.g_end_frame, dbplate.g_duration, dbplate.g_filesystem_path, None, dbshot, None, None)
                        dbversion.set_status('vwd')
                        dbversion.set_version_type('Scan')
                        ihdb.create_version(dbversion)
                    else:
                        dbversion.g_description = 'Element Version from Scan Ingest'
                        dbversion.g_path_to_frames = dbplate.g_filesystem_path
                        dbversion.set_status('vwd')
                        dbversion.set_version_type('Scan')
                        ihdb.update_version(dbversion)
                    log.info(
                        "Got version %s object from database with ID of %s." % (dbversion.g_version_code, dbversion.g_dbid))
                    self.results_window.delivery_results.appendPlainText(
                        'INFO: Got version %s for shot %s.' % (dbversion.g_version_code, dbshot.g_shot_code))
                    QApplication.processEvents()
                    if plate_thumb_path:
                        ihdb.upload_thumbnail('Version', dbversion, plate_thumb_path)
                        log.info(
                            "Uploaded thumbnail for version %s." % (dbversion.g_version_code))
                        self.results_window.delivery_results.appendPlainText(
                            'INFO: Uploaded thumbnail for version %s.' % (dbversion.g_version_code))
                        QApplication.processEvents()


            for tmp_io in g_ingest_sorted:
            
                if tmp_io.scope == 'shot' and tmp_io.extension in config.get('scan_ingest', 'movie_exts').split(','):
                           
                    dbshot = tmp_io.parent_dbobject
                    shot_thumb_dir = os.path.join(tmp_io.parent_wd, g_shot_thumb_dir.format(pathsep=os.path.sep))

                    # retrive object from database for plate
                    dest_full_path = os.path.join(tmp_io.dest_dir, tmp_io.dest_name)
                    dest_base = os.path.splitext(os.path.basename(tmp_io.dest_name))[0]
                    b_new_shot_thumb = False

                    if uniq_shots[tmp_io.parent_name]['new_shot']:
                        b_new_shot_thumb = True
                    
                    # first, create a .PNG from the source...
                    log.debug(dest_full_path)
                    log.debug(tmp_io.start_frame)
                    log.debug(tmp_io.end_frame)
                    log.info("About to call create_thumbnail_from_movie()...")
                    generated_thumb_path = thumbnails.create_thumbnail_from_movie(dest_full_path, ((tmp_io.end_frame - tmp_io.start_frame)/2) + tmp_io.start_frame)
                    log.info("Created thumbnail %s."%(generated_thumb_path))

                    # publish the movie
                    log.info('Publishing this movie to the database...')
                    dbpublishmovie = None
                    try:
                        dbpublishmovie = ihdb.publish_for_ingest(dbshot, dest_full_path, dest_base, 'Publish of movie by Scan Ingestion script', 'Movie')
                    except:
                        log.error("Caught exception when trying to publish a movie!")
                        log.error(sys.exc_info()[0])
                        log.error(sys.exc_info()[1])
                        log.error(traceback.format_exc(sys.exc_info()[2]))
                    log.info('Done.')
                    # upload a thumbnail
                    log.info("Uploading thumbnail for publish.")
                    if dbpublishmovie:
                        ihdb.upload_thumbnail('PublishedFile', dbshot, generated_thumb_path, altid = dbpublishmovie['id'])
                    if not basic_thumbnail_path:
                        basic_thumbnail_path = generated_thumb_path

                    try:
                        tmp_thumb = d_shot_thumbnail_files[dbshot.g_shot_code]
                        if not tmp_thumb['hires_src']:
                            if tmp_io.is_mainplate:
                                d_shot_thumbnail_files[dbshot.g_shot_code] = { 'path' : generated_thumb_path, 'hires_src' : False, 'mainplate' : True }
                    except KeyError:
                        d_shot_thumbnail_files[dbshot.g_shot_code] = { 'path' : generated_thumb_path, 'hires_src' : False, 'mainplate' : tmp_io.is_mainplate }

                    # upload a thumbnail for the plate to the shot, in the event that this is a new shot
                    if b_new_shot_thumb and tmp_io.is_mainplate:
                        shutil.copyfile(generated_thumb_path, thumbnails.get_thumbnail_for_shot(dbshot.g_shot_code))
                        log.info('%s: %s -> %s' % ('copy', generated_thumb_path, thumbnails.get_thumbnail_for_shot(dbshot.g_shot_code)))
                        ihdb.upload_thumbnail('Shot', dbshot, generated_thumb_path)
                        log.info("Uploaded thumbnail %s to DB shot object %s."%(generated_thumb_path, dbshot.g_shot_code))
                        uniq_shots[tmp_io.parent_name]['new_shot'] = False

                    self.results_window.delivery_results.appendPlainText('INFO: Published movie %s for shot %s.'%(dest_base, dbshot.g_shot_code))
                    QApplication.processEvents()

                    # make a version in the database for this shot
                    plate_thumb_glob = os.path.join(shot_thumb_dir, '%s_movie_thumb.*.png'%(dest_base))
                    plate_thumb_path = None
                    b_thumb_ul = False
                    for tmp_thumb_path in glob.glob(plate_thumb_glob):
                        plate_thumb_path = tmp_thumb_path
                        log.info('Located thumbnail for Version %s: %s'%(dest_base, plate_thumb_path))
                    if not plate_thumb_path:
                        plate_thumb_glob = os.path.join(shot_thumb_dir, '%s_thumb.*.png' % (dest_base))
                        for tmp_thumb_path in glob.glob(plate_thumb_glob):
                            plate_thumb_path = tmp_thumb_path
                            log.info('Located thumbnail for Version %s: %s' % (dest_base, plate_thumb_path))

                    dbversion = ihdb.fetch_version(dest_base, dbshot)
                    if not dbversion:
                        dbversion = DB.Version(dest_base, -1, 'Quicktime Version from Scan Ingest', tmp_io.start_frame, tmp_io.end_frame, tmp_io.start_frame, None, dest_full_path, dbshot, None, None)
                        dbversion.set_status('vwd')
                        dbversion.set_version_type('Reference')
                        ihdb.create_version(dbversion)
                        log.info('Successfully created new Version %s in the database with ID %d.'%(dbversion.g_version_code, dbversion.g_dbid))
                        b_thumb_ul = True
                    else:
                        dbversion.g_description = 'Quicktime Version from Scan Ingest'
                        dbversion.g_path_to_movie = dest_full_path
                        dbversion.set_status('vwd')
                        ihdb.update_version(dbversion)
                        log.info('Successfully updated existing Version %s in the database with ID %d.' % (
                        dbversion.g_version_code, dbversion.g_dbid))
                    log.info(
                        "Got version %s object from database with ID of %s." % (dbversion.g_version_code, dbversion.g_dbid))
                    self.results_window.delivery_results.appendPlainText(
                        'INFO: Got version %s for shot %s.' % (dbversion.g_version_code, dbshot.g_shot_code))
                    QApplication.processEvents()
                    if plate_thumb_path and b_thumb_ul:
                        log.info('Will upload thumbnail %s for version %s'%(plate_thumb_path, dbversion.g_version_code))
                        ihdb.upload_thumbnail('Version', dbversion, plate_thumb_path)
                        log.info(
                            "Uploaded thumbnail for version %s." % (dbversion.g_version_code))
                        self.results_window.delivery_results.appendPlainText(
                            'INFO: Uploaded thumbnail for version %s.' % (dbversion.g_version_code))
                        QApplication.processEvents()

                    
            # step 5: create a stub Nuke script, if none exists
            for u_shot in uniq_shots.keys():
            
                # build a list of every file to add to a Nuke script
                tmp_shotitems = []
                tmp_hiresitems = []
                tmp_refitems = []
                
                shot_wd = None
                dbshot = None
                movie_exts = config.get('scan_ingest', 'movie_exts').split(',')
                hires_exts = config.get('scan_ingest', 'lutted_image_exts').split(',')

                log.info("Looping through available items for shot %s."%u_shot)
                
                for tmp_io in g_ingest_sorted:
                    log.debug(tmp_io.obj_debug_info())
                    if tmp_io.scope == 'shot' and tmp_io.parent_name == u_shot:
                        if tmp_io.extension in movie_exts:
                            if tmp_io.is_mainplate:
                                tmp_hiresitems.insert(0, os.path.join(tmp_io.dest_dir, tmp_io.dest_name))
                            else:
                                tmp_hiresitems.append(os.path.join(tmp_io.dest_dir, tmp_io.dest_name))
                            shot_wd = tmp_io.parent_wd
                            dbshot = tmp_io.parent_dbobject
                        elif tmp_io.extension in hires_exts:
                            if tmp_io.is_seq:
                                if tmp_io.is_mainplate:
                                    tmp_refitems.insert(0, os.path.join(tmp_io.dest_dir, tmp_io.dest_name))
                                else:
                                    tmp_refitems.append(os.path.join(tmp_io.dest_dir, tmp_io.dest_name))
                                shot_wd = tmp_io.parent_wd
                                dbshot = tmp_io.parent_dbobject
                                
                tmp_shotitems.extend(tmp_hiresitems)
                tmp_shotitems.extend(tmp_refitems)

                if len(tmp_shotitems) == 0:
                    log.info("No plates or reference material available in this ingest for shot %s. No Nuke script will be created."%u_shot)
                    continue
                
                # check to see if we are building a temp script or not
                b_temp_shot = True
                for tmp_item in tmp_shotitems:
                    tmp_ext = os.path.splitext(tmp_item)[-1].lstrip('.')
                    if tmp_ext in config.get('scan_ingest', 'lutted_image_exts').split(','):
                        b_temp_shot = False
                
                # has a Nuke script already been created?
                log.debug("Has a nuke script already been created?")
                log.debug("Shot working directory: %s"%shot_wd)
                log.debug("Nuke scripts directory: %s"%config.get(g_ih_show_code, 'shot_scripts_dir'))
                nuke_scripts_dir = os.path.join(shot_wd, config.get(g_ih_show_code, 'shot_scripts_dir'))
                nuke_script_path = None
                
                temp_script_name = config.get(g_ih_show_code, 'temp_script_start').format(shot = u_shot)
                temp_script_path = os.path.join(nuke_scripts_dir, '%s.nk'%temp_script_name)
                
                if b_temp_shot:
                    nuke_script_name = config.get(g_ih_show_code, 'temp_script_start').format(shot = u_shot)
                    nuke_script_path = os.path.join(nuke_scripts_dir, '%s.nk'%nuke_script_name)
                else:
                    nuke_script_name = None
                    
                    if os.path.exists(temp_script_path):
                        log.info('This shot already contains temp Nuke scripts.')
                        glob_base_list = temp_script_name.split(g_version_separator)
                        glob_temp_match = os.path.join(nuke_scripts_dir, '%s%s*.nk'%(glob_base_list[0], g_version_separator))
                        latest_temp = sorted(glob.glob(glob_temp_match))[-1]
                        log.info('Latest temp version: %s'%latest_temp)
                        latest_temp_base = os.path.splitext(os.path.basename(latest_temp))[0]
                        latest_temp_version = int(latest_temp_base.split(g_version_separator)[-1])
                        start_nuke_version_string = g_version_format%(latest_temp_version + 1)
                        nuke_script_name = config.get(g_ih_show_code, 'shot_script_start').format(shot = u_shot).split(g_version_separator)[0] + g_version_separator + start_nuke_version_string
                    else:
                        nuke_script_name = config.get(g_ih_show_code, 'shot_script_start').format(shot = u_shot)
                    nuke_script_path = os.path.join(nuke_scripts_dir, '%s.nk'%nuke_script_name)


                log.info('Likely Nuke script for this shot is %s.'%nuke_script_path)
                if not os.path.exists(nuke_script_path):
                    log.info('Script will need to be created.')
                    tmp_shotitems.insert(0, nuke_script_path)              
                    tmp_shotitems.insert(0, config.get('scan_ingest', 'nuke_script_creator_%s'%sys.platform))
                    log.info('Nuke script creator command line:')
                    log.info(' '.join(tmp_shotitems))
                    proc = subprocess.Popen(tmp_shotitems)
                    proc.wait()
                    log.info('Nuke script creation complete!')
                    self.results_window.delivery_results.appendPlainText('INFO: Created stub Nuke script at %s.'%nuke_script_path)
                    QApplication.processEvents()
                    
                    dbtask = None
                    dbtasks = ihdb.fetch_tasks_for_shot(dbshot)
                    # create a temp task in the database, if it doesn't already exist
                    if b_temp_shot:
                        str_temp_comp_task_name = config.get('scan_ingest', 'temp_comp_task_name')
                        for tmptask in dbtasks:
                            if tmptask.g_task_name == str_temp_comp_task_name:
                                dbtask = tmptask
                        if not dbtask:
                            dbtask = DB.Task(str_temp_comp_task_name, None, None, uniq_shots[u_shot]['dbshot'], -1)
                            dbtask.set_pipeline_step_id(int(config.get('database', 'shotgun_temp_pipeline_step_id')))
                            log.info('Creating a %s task in the database for shot %s.'%(str_temp_comp_task_name, u_shot))
                            ihdb.create_task(dbtask)
                    else:
                        str_final_comp_task_name = config.get('scan_ingest', 'final_comp_task_name')
                        for tmptask in dbtasks:
                            if tmptask.g_task_name == str_final_comp_task_name:
                                dbtask = tmptask
                        if not dbtask:
                            dbtask = DB.Task(str_final_comp_task_name, None, None, uniq_shots[u_shot]['dbshot'], -1)
                            dbtask.set_pipeline_step_id(int(config.get('database', 'shotgun_comp_pipeline_step_id')))
                            log.info('Creating a %s task in the database for shot %s.'%(str_final_comp_task_name, u_shot))
                            ihdb.create_task(dbtask)
                    if dbtask:
                        log.info('Publishing the Nuke script to the database...')
                        nuke_script_base = os.path.splitext(os.path.basename(nuke_script_path))[0]
                        try:
                            dbpublishnk = ihdb.publish_for_shot(uniq_shots[u_shot]['dbshot'], nuke_script_path, 'Initial publish of stub Nuke script by Scan Ingestion script')
                            ihdb.upload_thumbnail('PublishedFile', dbtask, d_shot_thumbnail_files[u_shot]['path'], altid = dbpublishnk['id'])
                        except:
                            log.error("Caught exception when trying to publish a Nuke script!")
                            log.error(sys.exc_info()[0])
                            log.error(sys.exc_info()[1])
                        log.info('Done.')
                else:
                    log.info('Nuke script already exists at this location.')
                    
                log.info('Done creating Nuke scripts for shot %s.'%u_shot)
                
            self.results_window.delivery_results.appendPlainText('INFO: Done with scan ingestion!!!')
            QApplication.processEvents()
        except:
            e = sys.exc_info()
            etype = e[0].__name__
            emsg = e[1]
            self.results_window.delivery_results.appendPlainText("ERROR: Caught exception of type %s!"%etype)
            self.results_window.delivery_results.appendPlainText("  MSG: %s"%emsg)
            self.results_window.delivery_results.appendPlainText(traceback.format_exc(e[2]))
            QApplication.processEvents()
        self.results_window.close_button.setEnabled(True)
    
    def accept(self):
        global log, g_seq_regexp, g_shot_regexp, g_ingest_sorted, g_show_element_dir, g_ih_show_root, g_seq_dir_format, g_seq_regexp, g_shot_dir_format, g_seq_element_dir_format
        log.info('User clicked OK button. Proceeding with form validation.')
        for row_id in xrange(self.table_model.rowCount(Qt.DisplayRole)):
            parent_idx = self.table_model.createIndex(row_id, 4)
            parent = parent_idx.data()
            scope_idx = parent_idx.sibling(row_id, 3)
            scope = scope_idx.data()
            if scope == 'sequence':
                seq_regexp = '^%s$'%g_seq_regexp
                log.debug('Attempting to match parent value %s with regular expression %s'%(parent, seq_regexp))
                if not re.match(seq_regexp, parent):
                    log.info('Parent value of %s does not match regular expression for sequence %s.'%(parent, seq_regexp))
                    parent_del = self.table_view.itemDelegate(parent_idx)
                    QMessageBox.warning(self, 'Validation Error', 'Value entered does not match validation pattern for a %s'%scope, QMessageBox.Ok)
                    self.table_view.selectionModel().select(parent_idx, QItemSelectionModel.ClearAndSelect)
                    parent_editor = parent_del.createEditor(None, None, parent_idx)
                    parent_editor.setFocus()
                    parent_editor.selectAll()
                    parent_editor.home(True)
                    return False
            elif scope == 'shot':
                shot_regexp = '^%s$'%g_shot_regexp
                log.debug('Attempting to match parent value %s with regular expression %s'%(parent, shot_regexp))
                if not re.match(shot_regexp, parent):
                    log.info('Parent value of %s does not match regular expression for shot %s.'%(parent, shot_regexp))
                    parent_del = self.table_view.itemDelegate(parent_idx)
                    QMessageBox.warning(self, 'Validation Error', 'Value entered does not match validation pattern for a %s'%scope, QMessageBox.Ok)
                    self.table_view.selectionModel().select(parent_idx, QItemSelectionModel.ClearAndSelect)
                    parent_editor = parent_del.createEditor(None, None, parent_idx)
                    parent_editor.setFocus()
                    parent_editor.selectAll()
                    parent_editor.home(True)
                    return False
        tmp_ingest_sorted = []
        # print "INFO: Proceeding with delivery publish."
        for index, row in enumerate(self.table_model.mylist):
            if not row[0]:
                log.info("User requested removal of %s from delivery."%row[2])
            else:
                tmp_io = g_ingest_sorted[index]
                log.info('Adding element %s to ingest list.'%row[2])
                tmp_io.scope = row[3]
                tmp_io.parent_name = row[4]
                tmp_parent_wd = ""
                if row[3] == 'show':
                    tmp_parent_wd = g_show_element_dir.format(show_root = g_ih_show_root, pathsep = os.path.sep)
                elif row[3] == 'sequence':
                    sequence = row[4]
                    tmp_parent_wd = g_seq_element_dir_format.format(show_root = g_ih_show_root, pathsep = os.path.sep, sequence = row[4])
                elif row[3] == 'shot':
                    shot = row[4]
                    match_obj = re.search(g_seq_regexp, row[4])
                    if match_obj:
                        sequence = match_obj.group(0)
                    else:
                        sequence = 'xx'
                    tmp_parent_wd = g_shot_dir_format.format(show_root = g_ih_show_root, pathsep = os.path.sep, sequence = sequence, shot = row[4])
                tmp_io.parent_wd = tmp_parent_wd
                tmp_io.type = row[5]
                tmp_io.dest_dir = os.path.dirname(row[6])
                tmp_io.dest_name = os.path.basename(row[6])
                tmp_io.is_mainplate = row[7]
                log.info(tmp_io)
                tmp_ingest_sorted.append(tmp_io)
                        
        g_ingest_sorted = tmp_ingest_sorted
        self.process_ingest()

    def table_data(self):
        element_table_ret = []
        global g_ingest_sorted
        for element in reversed(g_ingest_sorted):
            element_table_ret.append([True, element.element_name, element.get_full_name(), element.scope, element.parent_name, element.type, os.path.join(element.dest_dir, element.dest_name), element.is_mainplate])
        return element_table_ret

    @pyqtSlot(QModelIndex)
    def validation_error_slot(self, index):
        idx_widget = self.table_view.indexWidget(index)
        scope_value = index.sibling(index.row(), 3).data()
        QMessageBox.warning(self, 'Validation Error', 'Value entered does not match validation pattern for a %s'%scope_value, QMessageBox.Ok)
        idx_widget.selectAll()
        # print idx_widget

    @pyqtSlot(QModelIndex)
    def output_change_slot(self, index):
        global g_ih_show_code, g_ih_show_root, g_show_element_dir, g_dest_type_dict, g_ingest_sorted, g_seq_dir_format, g_seq_regexp, g_shot_dir_format, g_seq_element_dir_format
        idx_widget = self.table_view.indexWidget(index)
        scope_idx = None
        parent_idx = None
        type_idx = None
        ename_idx = index.sibling(index.row(), 1)
        ename = ename_idx.data()
        epath_idx = index.sibling(index.row(), 2)
        epath = epath_idx.data()
        fpath_idx = index.sibling(index.row(), 6)
        if index.column() == 3:
            scope_idx = index
            parent_idx = index.sibling(index.row(), 4)
            type_idx = index.sibling(index.row(), 5)
            if index.data() == 'show':
                self.table_model.blockSignals(True)
                self.table_model.setData(parent_idx, g_ih_show_code)
                self.table_model.blockSignals(False)
        elif index.column() == 4:
            scope_idx = index.sibling(index.row(), 3)
            parent_idx = index
            type_idx = index.sibling(index.row(), 5)
        elif index.column() == 5:
            scope_idx = index.sibling(index.row(), 3)
            parent_idx = index.sibling(index.row(), 4)
            type_idx = index
        
        scope = scope_idx.data()
        type = type_idx.data()
        parent = parent_idx.data()
        
        sequence = None
        shot = None
        
        is_seq = False
        elem_obj = None
        for tmp_elem in g_ingest_sorted:
            if tmp_elem.get_full_name() == epath:
                elem_obj = tmp_elem
                log.info('Found element match: %s = %s'%(tmp_elem.get_full_name(), epath))
                if tmp_elem.is_seq:
                    is_seq = True
        tmp_parent_wd = ""
        if scope == 'show':
            tmp_parent_wd = g_show_element_dir.format(show_root = g_ih_show_root, pathsep = os.path.sep)
        elif scope == 'sequence':
            sequence = parent
            tmp_parent_wd = g_seq_element_dir_format.format(show_root = g_ih_show_root, pathsep = os.path.sep, sequence = parent)
        elif scope == 'shot':
            shot = parent
            match_obj = re.search(g_seq_regexp, parent)
            if match_obj:
                sequence = match_obj.group(0)
            else:
                sequence = 'xx'
            tmp_parent_wd = g_shot_dir_format.format(show_root = g_ih_show_root, pathsep = os.path.sep, sequence = sequence, shot = parent)
        tmp_elem_wd = None
        if is_seq:
            tmp_elem_wd = os.path.join(tmp_parent_wd, g_dest_type_dict[type].format(pathsep = os.path.sep, element_name = elem_obj.dest_name.split('.')[0]))
        else:
            tmp_elem_wd = os.path.join(tmp_parent_wd, g_dest_type_dict[type].format(pathsep = os.path.sep, element_name = elem_obj.dest_name.split('.')[0]))
        final_path = os.path.join(tmp_elem_wd, elem_obj.dest_name)
        self.table_model.blockSignals(True)
        self.table_model.setData(fpath_idx, final_path)
        self.table_model.blockSignals(False)
                   
    def table_header(self):
        element_header_ret = ['Include?', 'Element Name', 'Source Path', 'Scope', 'Parent Name', 'Element Type', 'Destination Path', 'Main Plate']
        return element_header_ret

class IngestTableModel(QAbstractTableModel):

    validation_error = pyqtSignal(QModelIndex)
    output_change = pyqtSignal(QModelIndex)
    
    def __init__(self, parent, mylist, header, *args):
        super(IngestTableModel, self).__init__()
        self.mylist = mylist
        self.header = header
    def flags(self, index):
        if index.column() in [0, 3, 4, 5, 6, 7]:
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable
        else: 
            return Qt.ItemIsEnabled | Qt.ItemIsSelectable
    def updateModel(self, mylist):
        self.mylist = mylist
    def rowCount(self, parent):
        return len(self.mylist)
    def columnCount(self, parent):
        return len(self.header)
    def data(self, index, role):
        if not index.isValid():
            return None
        elif role != Qt.DisplayRole:
            return None
        return self.mylist[index.row()][index.column()]
    def setData(self, index, value, role=Qt.DisplayRole):
        global log
        log.debug('IngestTableModel.setData() called, index.row = %d, index.column = %d, value = %s'%(index.row(), index.column(), value))
        global g_ih_show_code, g_seq_regexp, g_shot_regexp
        if index.column() == 0:
            self.mylist[index.row()][0] = value
        elif index.column() == 4:
            scope_index = index.sibling(index.row(), 3)
            scope_value = scope_index.data(Qt.DisplayRole)
            if scope_value == 'show':
                value = g_ih_show_code
                self.mylist[index.row()][4] = value
                self.output_change.emit(index)
            elif scope_value == 'sequence':
                seq_regexp = '^%s$'%g_seq_regexp
                if not re.match(seq_regexp, value):
                    self.validation_error.emit(index)
                    return False
                else:
                    self.mylist[index.row()][4] = value
                    self.output_change.emit(index)
            elif scope_value == 'shot':
                shot_regexp = '^%s$'%g_shot_regexp
                if not re.match(shot_regexp, value):
                    self.validation_error.emit(index)
                    return False
                else:
                    self.mylist[index.row()][4] = value
                    self.output_change.emit(index)
        elif index.column() == 3:
            self.mylist[index.row()][3] = value
            self.output_change.emit(index)
        elif index.column() == 5:
            self.mylist[index.row()][5] = value
            self.output_change.emit(index)
        elif index.column() == 6:
            self.mylist[index.row()][6] = value
        elif index.column() == 7:
            self.mylist[index.row()][7] = value
        return True

    def headerData(self, col, orientation, role):
        if orientation == Qt.Horizontal and role == Qt.DisplayRole:
            return self.header[col]
        return None
    def sort(self, col, order):
        """sort table by given column number col"""
        self.layoutAboutToBeChanged.emit()
        self.mylist = sorted(self.mylist,
            key=operator.itemgetter(col))
        if order == Qt.DescendingOrder:
            self.mylist.reverse()
        self.layoutChanged.emit()
        
class ScanIngestResultsWindow(QMainWindow):
    def __init__(self, parent):
        super(ScanIngestResultsWindow, self).__init__(parent)
        self.setWindowTitle('Scan Ingest Results')
        self.setMinimumSize(1920,1080)
    
        # central widget
        self.widget = QWidget()
        self.setCentralWidget(self.widget)
        self.layout = QVBoxLayout()
        self.widget.setLayout(self.layout)
    
        self.layout_top = QHBoxLayout()
        self.delivery_results = QPlainTextEdit()
    
        self.layout_top.addWidget(self.delivery_results)
        self.layout.addLayout(self.layout_top)
        # buttons at the bottom        
        self.layout_bottom = QHBoxLayout()
        self.close_button = QPushButton("Close", self)
        # self.close_button.setOrientation(Qt.Horizontal)
        # self.close_button.setStandardButtons(QDialogButtonBox.Ok|QDialogButtonBox.Cancel)
        self.close_button.clicked.connect(self.window_close)
        self.close_button.setEnabled(False)
        self.layout_bottom.addWidget(self.close_button)
        self.layout.addLayout(self.layout_bottom)


    def window_close(self):
        QCoreApplication.instance().quit()

class ScanIngestRule:
    
    valid_scope_list = ['show', 'sequence', 'shot']

    def __init__(self, name, rule_param_list):
        if not isinstance(rule_param_list, list):
            raise ValueError("Please provide a list to the ScanIngestRule class constructor.")
        if len(rule_param_list) != 8:
            raise ValueError("Please provide a list to the ScanIngestRule class constructor that is 8 elements long.")
            
        self.rule_param_list = rule_param_list
        self.name = name
        
        tmp_scope_list = rule_param_list[0].split('|')
        for tmp_scope in tmp_scope_list:
            if tmp_scope not in ScanIngestRule.valid_scope_list:
                raise ValueError("Scope provided as parameter 1 must be one of: %s"%valid_scope_list)
        
        self.scope_list = tmp_scope_list
        self.ext_list = rule_param_list[1].split('|')
        self.name_match_re = re.compile(rule_param_list[2])
        self.is_seq = False
        if rule_param_list[3] in ['True', 'TRUE', 'true', 'Yes', 'YES', 'yes', 'y', 'Y']:
            self.is_seq = True
        self.dest_element_type = rule_param_list[4]
        self.case_func = do_nothing
        if rule_param_list[5] in ['UPPER', 'Upper', 'upper']:
            self.case_func = str.upper
        if rule_param_list[5] in ['LOWER', 'Lower', 'lower']:
            self.case_func = str.lower
        self.re_dest_match = rule_param_list[6]
        self.re_dest_sub = rule_param_list[7]
        
    def match_io(self, ingest_object):
        global log, g_dest_type_dict, g_frame_format
        b_rule_match = False
        if not isinstance(ingest_object, IngestObject):
            raise ValueError("match_io(ingest_object) must be provided an object of type IngestObject")
        # does this ingest object match the scope of the rule?
        if ingest_object.scope in self.scope_list:
            log.debug("%s scope of %s matches rule scope list %s"%(ingest_object.element_name, ingest_object.scope, self.scope_list))
            # does this ingest object have the correct file extension?
            log.debug("File extension of IngestObject: %s"%ingest_object.extension)
            if ingest_object.extension in self.ext_list:
                log.debug("%s extension of %s matches rule extension list %s"%(ingest_object.element_name, ingest_object.extension, self.ext_list))
                # does this ingest object name match the rule name regular expression?
                if self.name_match_re.match(ingest_object.element_name):
                    log.debug("%s element name matches rule regular expression %s"%(ingest_object.element_name, self.name_match_re.pattern))
                    # last, should this be an image sequence?
                    if ingest_object.is_seq == self.is_seq:
                        log.debug("%s image sequence parameter '%s' matches rule image sequence parameter '%s'"%(ingest_object.element_name, ingest_object.is_seq, self.is_seq))
                        log.info("Element %s matches rule %s!"%(ingest_object.element_name, self.name))
                        ingest_object.type = self.dest_element_type
                        log.debug("Setting type of element %s to %s."%(ingest_object.element_name, ingest_object.type))
                        new_base = self.case_func(re.sub(self.re_dest_match, self.re_dest_sub, ingest_object.element_name))
                        if ingest_object.is_seq:
                            ingest_object.dest_name = "%s.%s.%s"%(new_base, g_frame_format, ingest_object.extension.lower())
                        else:
                            ingest_object.dest_name = "%s.%s"%(new_base, ingest_object.extension.lower())
                        log.debug("Setting dest_name of element %s to %s."%(ingest_object.element_name, ingest_object.dest_name))
                        path_fromwd = g_dest_type_dict[ingest_object.type].format(pathsep = os.path.sep, element_name = new_base)
                        ingest_object.dest_dir = os.path.join(ingest_object.parent_wd, path_fromwd)
                        log.debug("Setting dest_dir of element %s to %s."%(ingest_object.element_name, ingest_object.dest_dir))
                        log.debug('')
                        log.debug('')
                        log.debug('Rule Match: %s'%self.name)
                        log.debug('')
                        log.debug('')
                        log.debug(ingest_object.obj_debug_info())
                        b_rule_match = True
        return b_rule_match

        
if len(sys.argv) != 2:
    log.error("Please provide a valid path to a directory as the first and only command line argument.")
    usage()
    exit()
    
if not os.path.exists(sys.argv[1]):
    log.error("Path provided on the command line does not exist.")
    usage()
    exit()
elif not os.path.isdir(sys.argv[1]):
    log.error("Path provided on the command line is not a directory.")
    usage()
    exit()
else:
    g_path = sys.argv[1]
    log.info("Located source folder %s."%g_path)

def case_func(str_input):
    return str_input            

# Globals
g_sequences = {}

g_ingest_sorted = []

g_ih_show_code = None
g_ih_show_root = None
g_ih_show_cfg_path = None
g_shot_regexp = None
g_seq_regexp = None
g_sequence_regexp = None
g_shot_dir = None
g_shot_dir_format = None
g_seq_dir_format = None
g_seq_element_dir_format = None
g_show_file_operation = None
g_skip_list = []
g_imgseq_regexp = None
g_shot_scripts_dir = None
g_shot_script_start = None
g_shot_template = None
g_shot_thumb_dir = None
g_cdl_mainplate_regexp = None
g_mainplate_re = None
g_plate_colorspace = None
g_nuke_exe_path = None
g_image_ext_list = []
g_dest_type_dict = {}
g_frame_format = None
g_show_element_dir = None
g_version_separator = None
g_version_format = None
g_cdl_file_ext = 'cdl'
g_rules = []
config = None
g_object_scope_list = ['show', 'sequence', 'shot']
ihdb = None

# Shotgun Authentication
sa = None
user = None


try:
    g_ih_show_code = os.environ['IH_SHOW_CODE']
    g_ih_show_root = os.environ['IH_SHOW_ROOT']
    g_ih_show_cfg_path = os.environ['IH_SHOW_CFG_PATH']
    config = ConfigParser.ConfigParser()
    config.read(g_ih_show_cfg_path)
    g_shot_regexp = config.get(g_ih_show_code, 'shot_regexp_ci')
    g_seq_regexp = config.get(g_ih_show_code, 'sequence_regexp_ci')
    g_sequence_regexp = config.get(g_ih_show_code, 'sequence_regexp_2')
    g_shot_dir = config.get(g_ih_show_code, 'shot_dir')
    g_shot_dir_format = config.get(g_ih_show_code, 'shot_dir_format')
    g_seq_dir_format = config.get(g_ih_show_code, 'seq_dir_format')
    g_seq_element_dir_format = config.get(g_ih_show_code, 'seq_element_dir_format')
    g_show_file_operation = config.get(g_ih_show_code, 'show_file_operation')
    g_imgseq_regexp = config.get(g_ih_show_code, 'imgseq_regexp')
    g_shot_scripts_dir = config.get(g_ih_show_code, 'shot_scripts_dir')
    g_shot_comp_render_dir = config.get(g_ih_show_code, 'shot_comp_render_dir')
    g_shot_script_start = config.get(g_ih_show_code, 'shot_script_start')
    g_write_extension = config.get(g_ih_show_code, 'write_extension')
    g_write_frame_format = config.get(g_ih_show_code, 'write_frame_format')
    g_write_fps = config.get(g_ih_show_code, 'write_fps')
    g_plate_colorspace = config.get(g_ih_show_code, 'plate_colorspace')
    g_cdl_mainplate_regexp = config.get(g_ih_show_code, 'cdl_mainplate_regexp')
    g_mainplate_re = re.compile(config.get(g_ih_show_code, 'mainplate_regexp'))
    g_show_element_dir = config.get(g_ih_show_code, 'show_element_dir')
    tmp_case_func = config.get(g_ih_show_code, 'case_func')
    if tmp_case_func == 'lower':
        case_func = str.lower
    elif tmp_case_func == 'upper':
        case_func = str.upper
    g_shot_template = config.get('shot_template', sys.platform)
    g_shot_thumb_dir = config.get('thumbnails', 'shot_thumb_dir')
    g_nuke_exe_path = config.get('nuke_exe_path', sys.platform)
    g_version_separator = config.get(g_ih_show_code, 'version_separator')
    g_version_format = config.get(g_ih_show_code, 'version_format')
    g_image_ext_list = config.get('scan_ingest', 'image_exts').split(',')
    g_file_ignore_list = read_csv_string(config.get('scan_ingest', 'file_ignore'))
    tmp_type_list = sorted(read_csv_string(config.get('scan_ingest', 'destination_types')))
    for tmp_type in tmp_type_list:
        if tmp_type.find('|') == -1:
            raise ValueError("Destination type %s in config file doesn't contain the required | character!"%tmp_type)
        type, path_fmt = tmp_type.split('|')
        g_dest_type_dict[type] = path_fmt
    g_frame_format = config.get(g_ih_show_code, 'write_frame_format')
    g_cdl_file_ext = config.get(g_ih_show_code, 'cdl_file_ext')
    log.info("Successfully loaded show-specific config file for %s."%g_ih_show_code)
    ihdb = DB.DBAccessGlobals.get_db_access()

    # Shotgun Authentication
    sa = sgtk.authentication.ShotgunAuthenticator()
    user = sa.create_script_user(api_script=config.get('database', 'shotgun_script_name'), api_key=config.get('database', 'shotgun_api_key'), host=config.get('database', 'shotgun_server_path'))
    sgtk.set_authenticated_user(user)
except:
    e = sys.exc_info()
    log.error(e[1])
    err_tb = traceback.format_exc()
    log.error(err_tb)
    exit()


# traverse the file structure
for dirname, subdirlist, filelist in os.walk(g_path):

    patterns = {}    
    fname_prev = ""
    frame_len_prev = -1
    frame_len_variable = False
    frame_start_delim = '.'
    frame_end_delim = '.'
    
    for fidx, fname in enumerate(sorted(filelist)):
        badfile = False
        for badfile_re in g_file_ignore_list:
            if re.search(badfile_re, fname):
                log.info("Skipping file %s - it is in the exclude list."%fname)
                badfile = True
                break
        if badfile:
            continue        
        fext = os.path.splitext(fname)[-1].lstrip('.')
        if fext not in g_image_ext_list:
            continue
        if fidx == 0:
            fname_prev = fname
            continue
        pattern_rev = ""
        fname_prev_rev = fname_prev[::-1]
        fname_rev = fname[::-1]
        diff_loc = -1
        for didx, info in enumerate(difflib.ndiff(fname_prev_rev, fname_rev)):
            if info[0] != ' ':
                diff_loc = didx
                break
        for digit_match in re.finditer('(\d+)', fname_rev):
            if digit_match.start() == diff_loc:
                pattern_rev = fname_rev[0:digit_match.start()] + '@' + fname_rev[digit_match.end():]
                frame_start_delim = fname_rev[digit_match.end()]
                frame_end_delim = fname_rev[digit_match.start() - 1]
                tframe = digit_match.group(1)[::-1]
                if frame_len_prev == -1:
                    frame_len_prev = len(tframe)
                else:
                    if frame_len_prev != len(tframe):
                        frame_len_variable = True
                frame_len_prev = len(tframe)
                break
        pattern = '(' + pattern_rev[::-1].replace('%s@%s'%(frame_start_delim, frame_end_delim), ')(\%s)(\d+)(\%s)('%(frame_start_delim, frame_end_delim)) + ')'
        if pattern not in patterns.keys():
            patterns[pattern] = pattern_rev[::-1].replace('@', '%%0%dd'%frame_len_prev)
        if frame_len_variable:
            patterns[pattern] = pattern_rev[::-1].replace('@', '%d')
        fname_prev = fname
        
    seqmatch = False
    for fname in sorted(filelist):
        badfile = False
        for badfile_re in g_file_ignore_list:
            if re.search(badfile_re, fname):
                log.info("Skipping file %s - it is in the exclude list."%fname)
                badfile = True
                break
        if badfile:
            continue        
        seqmatch = False
        log.debug('Looking at %s'%fname)
        for re_pattern in patterns.keys():
            match = re.search(re_pattern, fname)
            if match:
                tframe = ''
                try:
                    tframe = match.group(3)
                    # log.debug(match.groups())
                except IndexError:
                    continue
                seqmatch = True
                seq_key = os.path.join(dirname, patterns[re_pattern])
                seq_frames = None
                try:
                    seq_frames = g_sequences[seq_key].frames
                except KeyError:
                    tmp_io = IngestObject()
                    tmp_io.is_seq = True
                    tmp_io.full_name = seq_key
                    tmp_io.element_name = match.group(1)
                    if g_mainplate_re.search(tmp_io.element_name):
                        tmp_io.is_mainplate = True
                    tmp_io.source_dir = dirname
                    tmp_io.regexp_pattern = re_pattern
                    tmp_io.extension = os.path.splitext(fname)[-1].lstrip('.')
                    g_sequences[seq_key] = tmp_io
                    seq_frames = g_sequences[seq_key].frames
                seq_frames.append(tframe)
        if not seqmatch:
            noseq_key = os.path.join(dirname, fname)
            tmp_io = IngestObject()
            tmp_io.full_name = noseq_key
            tmp_io.element_name = os.path.splitext(fname)[0]
            tmp_io.source_dir = dirname
            tmp_io.extension = os.path.splitext(fname)[-1].lstrip('.')
            if tmp_io.extension == 'mov':
                mediainfo = quicktime_mediainfo(tmp_io.full_name)
                miliseconds = 1000.0
                frame_rate_re = '^([0-9.]+) '
                frame_rate = 23.976
                frame_rate_match = re.search(frame_rate_re, mediainfo['Frame rate'])
                if frame_rate_match:
                    frame_rate = float(frame_rate_match.group(1))
                duration_minutes = 0.0
                duration_seconds = 0.0
                duration_ms = 0.0
                duration_min_re = '([0-9]+) min'
                duration_sec_re = '([0-9]+) s'
                duration_ms_re = '([0-9]+) ms'
                duration_min_match = re.search(duration_min_re, mediainfo['Duration'])
                duration_sec_match = re.search(duration_sec_re, mediainfo['Duration'])
                duration_ms_match = re.search(duration_ms_re, mediainfo['Duration'])

                if duration_sec_match:
                    duration_seconds = float(duration_sec_match.group(1))
                if duration_min_match:
                    duration_minutes = float(duration_min_match.group(1))
                    duration_seconds = duration_seconds + (60.0 * duration_minutes)
                if duration_ms_match:
                    duration_ms = float(duration_ms_match.group(1))

                total_duration = (duration_seconds * frame_rate) + ((duration_ms/miliseconds)*frame_rate)
                frames = int(round(total_duration))
                log.info('Quicktime movie %s information: frame rate : %.3f fps, start frame : %d, end frame: %d'%(tmp_io.full_name, frame_rate, 1, frames))     
                tmp_io.start_frame = 1
                tmp_io.end_frame = frames               
                if g_mainplate_re.search(tmp_io.element_name):
                    tmp_io.is_mainplate = True
            if tmp_io.extension in ['cdl','ccc','cc', 'cube']:
                log.debug('File is a LUT.')
                if g_mainplate_re.search(tmp_io.element_name):
                    tmp_io.is_mainplate = True
                    log.debug('File matches the main plate regular expression')
            tmp_io.is_seq = False
            g_sequences[noseq_key] = tmp_io
            
        log.debug('Image sequence: %s'%(tmp_io.is_seq))


g_ingest_sorted = sorted(g_sequences.values(), key=lambda element: (-element.is_seq, element.element_name))

# put rules into global list

for tmp_rule in config.items('scan_ingest_rules'):
    g_rules.append(ScanIngestRule(tmp_rule[0], read_csv_string(tmp_rule[1])))

for ing_elem in g_ingest_sorted:
    log.info("Located element in folder to examine: %s"%ing_elem)
    shot_match = re.search(g_shot_regexp, ing_elem.element_name)
    if shot_match:
        tmp_shot = case_func(shot_match.group('shot'))
        tmp_sequence = case_func(shot_match.group('sequence'))
        log.debug("Setting parent name of element %s to shot %s."%(ing_elem.element_name, tmp_shot))
        ing_elem.parent_name = tmp_shot
        ing_elem.scope = 'shot'
        ing_elem.parent_wd = g_shot_dir_format.format(show_root = g_ih_show_root, pathsep = os.path.sep, sequence = tmp_sequence, shot = tmp_shot)
        log.debug("Setting parent working directory of element %s to %s."%(ing_elem.element_name, ing_elem.parent_wd))
    else:
        seq_match = re.search(g_sequence_regexp, ing_elem.element_name)
        if seq_match:
            tmp_sequence = case_func(seq_match.group(1))
            log.debug("Setting parent name of element %s to sequence %s."%(ing_elem.element_name, tmp_sequence))
            ing_elem.parent_name = tmp_sequence
            ing_elem.scope = 'sequence'
            ing_elem.parent_wd = g_seq_element_dir_format.format(show_root = g_ih_show_root, pathsep = os.path.sep, sequence = tmp_sequence)
            log.debug("Setting parent working directory of element %s to %s."%(ing_elem.element_name, ing_elem.parent_wd))
        else:
            log.debug("Setting parent name of element %s to show %s."%(ing_elem.element_name, g_ih_show_code))
            ing_elem.parent_name = g_ih_show_code
            ing_elem.scope = 'show'
            ing_elem.parent_wd = g_show_element_dir.format(show_root = g_ih_show_root, pathsep = os.path.sep)
            log.debug("Setting parent working directory of element %s to %s."%(ing_elem.element_name, ing_elem.parent_wd))
    for rule in g_rules:
        rule.match_io(ing_elem)

# Create a Qt application
app = QApplication(sys.argv)

# Our main window will be a QListView
window = ScanIngestWindow()
window.show()
app.exec_()
