#!/usr/local/bin/python

# sync_and_send_email.python
# sends a delivery package, either with rsync or aspera, and then sends email after procedure is complete.
# takes a temp config file as an argument

import ConfigParser
import sys
import os
import subprocess
import logging
import glob

# gmail/oauth

import httplib2
import oauth2client
import base64
import mimetypes

from oauth2client import client, tools
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from apiclient import errors, discovery
from email.mime.image import MIMEImage
from email.mime.audio import MIMEAudio
from email.mime.base import MIMEBase

# custom

g_ih_show_cfg_path = None
g_ih_show_root = None
g_ih_show_code = None
g_config = None
g_distro_list_to = None
g_distro_list_cc = None
g_mail_from = None
g_mail_from_address = None
g_write_ale = False
g_show_code = ""
g_shared_root = ""
g_credentials_dir = ""
g_client_secret = ""
g_gmail_creds = ""
g_gmail_scopes = ""
g_application_name = ""
g_shot_count = 0
g_email_text = ""
g_rsync_enabled = False
g_rsync_filetypes = []
g_rsync_dest = ""
g_subform_file_format = 'xlsx'

log = None

tmp_config = None

def globals_from_config():
    # initialize logger
    global log
    homedir = os.path.expanduser('~')
    logfile = ""
    if sys.platform == 'win32':
        logfile = os.path.join(homedir, 'AppData', 'Local', 'IHPipeline', 'sync_and_send_email.log')
    elif sys.platform == 'darwin':
        logfile = os.path.join(homedir, 'Library', 'Logs', 'IHPipeline', 'sync_and_send_email.log')
    elif sys.platform == 'linux2':
        logfile = os.path.join(homedir, 'Logs', 'IHPipeline', 'sync_and_send_email.log')
    if not os.path.exists(os.path.dirname(logfile)):
        os.makedirs(os.path.dirname(logfile))
    logFormatter = logging.Formatter("%(asctime)s:[%(threadName)s]:[%(levelname)s]:%(message)s")
    log = logging.getLogger()
    log.setLevel(logging.DEBUG)
    fileHandler = logging.FileHandler(logfile)
    fileHandler.setFormatter(logFormatter)
    log.addHandler(fileHandler)
    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    log.addHandler(consoleHandler)    
    
    global g_ih_show_cfg_path, g_ih_show_root, g_ih_show_code, g_config, g_subform_file_format
    global g_distro_list_to, g_distro_list_cc, g_mail_from, g_write_ale, g_shared_root, g_credentials_dir, g_client_secret, g_gmail_creds, g_application_name, g_email_text, g_rsync_enabled, g_rsync_filetypes, g_rsync_dest
    try:
        g_ih_show_code = os.environ['IH_SHOW_CODE']
        g_ih_show_root = os.environ['IH_SHOW_ROOT']
        g_ih_show_cfg_path = os.environ['IH_SHOW_CFG_PATH']
        g_config = ConfigParser.ConfigParser()
        g_config.read(g_ih_show_cfg_path)
        g_distro_list_to = g_config.get('email', 'distro_list_to')
        g_distro_list_cc = g_config.get('email', 'distro_list_cc')
        g_mail_from = g_config.get('email', 'mail_from')
        g_shared_root = g_config.get('shared_root', sys.platform)
        credentials_dir_dict = { 'pathsep' : os.path.sep, 'shared_root' : g_shared_root }
        g_credentials_dir = g_config.get('email', 'credentials_dir').format(**credentials_dir_dict)
        g_client_secret = g_config.get('email', 'client_secret')
        g_gmail_creds = g_config.get('email', 'gmail_creds')
        g_gmail_scopes = g_config.get('email', 'gmail_scopes')
        g_application_name = g_config.get('email', 'application_name')
        g_email_text = g_config.get('email', 'email_text')
        g_rsync_enabled = True if g_config.get(g_ih_show_code, 'delivery_rsync_enabled') == 'yes' else False
        g_rsync_filetypes = g_config.get(g_ih_show_code, 'delivery_rsync_filetypes').split(',')
        g_rsync_dest = g_config.get(g_ih_show_code, 'delivery_rsync_dest')
        g_subform_file_format = g_config.get('delivery', 'subform_file_format')
        log.info("Globals initiliazed from config %s."%g_ih_show_cfg_path)
    except KeyError:
        e = sys.exc_info()
        log.error(e[1])
        log.error("This is most likely because this system has not been set up to run inside the In-House environment.")
    except ConfigParser.NoSectionError:
        e = sys.exc_info()
        log.error(e[1])
    except ConfigParser.NoOptionError:
        e = sys.exc_info()
        log.error(e[1])
    except:        
        e = sys.exc_info()
        log.error(e[1])

def handle_rsync(m_source_folder):
    global log
    global g_rsync_filetypes, g_rsync_dest
    rsync_cmd = ['rsync',
                 '-auv',
                 '--prune-empty-dirs',
                 '--include="*/"']
    for valid_ext in g_rsync_filetypes:
        rsync_cmd.append('--include="*.%s"'%valid_ext)
    rsync_cmd.append('--exclude="*"')    
    rsync_cmd.append(m_source_folder.rstrip('/'))
    rsync_cmd.append(g_rsync_dest)
    log.info("Executing command: %s"%" ".join(rsync_cmd))
    proc = subprocess.Popen(" ".join(rsync_cmd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, shell=True)
    while proc.poll() is None:
        try:
            s_out = proc.stdout.readline().strip()
            log.info(s_out)
        except IOError:
            log.error("IOError Caught!")
            var = traceback.format_exc()
            log.error(var)
    if proc.returncode != 0:
        log.error("Errors have occurred during the rsync process - please see ~/Library/Logs/IHPipeline/sync_and_send_email.log for details.")
    else:
        log.info("Successfully completed delivery render.")
            
def get_credentials():
    global log
    global g_credentials_dir, g_gmail_creds, g_application_name, g_client_secret, g_gmail_scopes
    if not os.path.exists(g_credentials_dir):
        log.warning("Credentials directory in config file %s does not exist. Creating."%g_credentials_dir)
        os.makedirs(g_credentials_dir)
    credential_path = os.path.join(g_credentials_dir, g_gmail_creds)
    log.info("Searching for credential: %s"%credential_path)
    store = oauth2client.file.Storage(credential_path)
    credentials = store.get()
    if not credentials or credentials.invalid:
        flow = client.flow_from_clientsecrets(g_client_secret, g_gmail_scopes)
        flow.user_agent = g_application_name
        credentials = tools.run_flow(flow, store)
        log.info('Storing credentials to ' + credential_path)
    return credentials

def SendMessage(sender, to, cc, subject, msgHtml, msgPlain, attachmentFile=None):
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('gmail', 'v1', http=http, cache_discovery=False)
    if attachmentFile:
        message1 = createMessageWithAttachment(sender, to, cc, subject, msgHtml, msgPlain, attachmentFile)
    else: 
        message1 = CreateMessageHtml(sender, to, cc, subject, msgHtml, msgPlain)
    result = SendMessageInternal(service, "me", message1)
    return result

def SendMessageInternal(service, user_id, message):
    try:
        message = (service.users().messages().send(userId=user_id, body=message).execute())
        log.info('Message send complete, message ID: %s' % message['id'])
        return message
    except errors.HttpError as error:
        log.error('Caught HttpError: %s' % error)
        return "Error"
    return "OK"

def CreateMessageHtml(sender, to, cc, subject, msgHtml, msgPlain):
    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = sender
    msg['To'] = to
    msg['Cc'] = cc
    msg.attach(MIMEText(msgPlain, 'plain'))
    msg.attach(MIMEText(msgHtml, 'html'))
    return {'raw': base64.urlsafe_b64encode(msg.as_string())}

def createMessageWithAttachment(sender, to, cc, subject, msgHtml, msgPlain, attachmentFile):
    global log
    """Create a message for an email.

    Args:
      sender: Email address of the sender.
      to: Email address of the receiver.
      subject: The subject of the email message.
      msgHtml: Html message to be sent
      msgPlain: Alternative plain text message for older email clients          
      attachmentFile: The path to the file to be attached.

    Returns:
      An object containing a base64url encoded email object.
    """
    message = MIMEMultipart()
    message['to'] = to
    message['cc'] = cc
    message['from'] = sender
    message['subject'] = subject

    log.info("Email Message: %s"%msgPlain)
    message.attach(MIMEText(msgPlain))

    log.info("create_message_with_attachment: file: %s" % attachmentFile)
    content_type, encoding = mimetypes.guess_type(attachmentFile)

    if content_type is None or encoding is not None:
        content_type = 'application/octet-stream'
    main_type, sub_type = content_type.split('/', 1)
    if main_type == 'text':
        fp = open(attachmentFile, 'rb')
        msg = MIMEText(fp.read(), _subtype=sub_type)
        fp.close()
    elif main_type == 'image':
        fp = open(attachmentFile, 'rb')
        msg = MIMEImage(fp.read(), _subtype=sub_type)
        fp.close()
    elif main_type == 'audio':
        fp = open(attachmentFile, 'rb')
        msg = MIMEAudio(fp.read(), _subtype=sub_type)
        fp.close()
    else:
        fp = open(attachmentFile, 'rb')
        msg = MIMEBase(main_type, sub_type)
        msg.set_payload(fp.read())
        fp.close()
    filename = os.path.basename(attachmentFile)
    msg.add_header('Content-Disposition', 'attachment', filename=filename)
    message.attach(msg)

    return {'raw': base64.urlsafe_b64encode(message.as_string())}

# builds the body of the email message
def send_email(delivery_directory, file_list, shot_count):

    global g_rsync_dest, g_email_text, g_mail_from, g_distro_list_to, g_distro_list_cc, g_config, g_subform_file_format
    formatted_list= "\n".join(file_list)

    final_destination_dir = os.path.join(g_rsync_dest, os.path.split(delivery_directory)[-1])
    	
    d_email_text = {'shot_count' : shot_count, 'delivery_folder' : final_destination_dir, 'shot_list' : formatted_list, 'package' : os.path.split(delivery_directory)[-1]}
    msg = g_email_text.format(**d_email_text).replace('\\r', '\r')
    csvfiles = glob.glob(os.path.join(delivery_directory, '*.%s'%g_subform_file_format))
    d_email_subject = {'package' : os.path.split(delivery_directory)[-1]}
    s_subject = g_config.get('email', 'subject').format(**d_email_subject)
    
    if len(csvfiles) > 0:
        SendMessage(g_mail_from, g_distro_list_to, g_distro_list_cc, s_subject, msg, msg, csvfiles[0])
    else:
        SendMessage(g_mail_from, g_distro_list_to, g_distro_list_cc, s_subject, msg, msg)
        
    return msg
    
if __name__ == "__main__":
    valid = False
    if len(sys.argv) >= 2:
        file_path = sys.argv[1]
        if os.path.exists(file_path) and not os.path.isdir(file_path):
            valid = True
            try:
                globals_from_config()
                log.info("Reading information from temp file: %s"%file_path)
                tmp_config = ConfigParser.ConfigParser()
                tmp_config.read(file_path)
                package_dir = tmp_config.get('delivery', 'source_folder')
                file_list = tmp_config.get('delivery', 'file_list').split(',')
                file_count = len(file_list)
                if g_rsync_enabled:
                    log.info("About to call handle_rsync(%s)"%package_dir)
                    handle_rsync(package_dir)
                log.info("About to call send_email(%s, %s, %s)"%(package_dir, file_list, file_count))
                send_email(package_dir, file_list, file_count)
            except:
                problem = sys.exc_info()
                etype = problem[0].__name__
                emsg = problem[1]
                log.error("Caught exception of type %s!"%etype)
                log.error("%s"%emsg)
    if not valid:
        print "ERROR: Please provide a valid path to a temporary config file as the first and only argument."
        
            
