# -*- coding: utf-8 -*-
# from __future__ import absolute_import
import logging
import socket
import os
import subprocess
import datetime
import csv

log = logging.getLogger(__name__)

HAS_LIBS = False
try:
    import smtplib
    # import email.mime.text
    from email.mime.multipart import MIMEMultipart
    from email.mime.text import MIMEText
    from email.mime.image import MIMEImage
    from email.utils import make_msgid
    from email.mime.base import MIMEBase
    from email import encoders
    import yaml
#    import salt.utils
    HAS_LIBS = True
except ImportError:
    raise


__virtualname__ = 'adobe_email'

def __virtual__():
    '''
    Only load this module if smtplib is available on this minion.
    '''
    if HAS_LIBS:
        return __virtualname__
    return (False, 'This module is only loaded if smtplib is available')

def get_user_data(file_path):
    """
        Procedure to load yaml data
    """
    with open(file_path) as file_yaml:
        data = yaml.load(file_yaml)
    return data

def get_files(path, file_format):
    """
        Procedure to list a files in a directory
    """
    p_obj = subprocess.Popen(['ls', path], stdout=subprocess.PIPE)
    files = p_obj.communicate()
    print("Found files")
    print(files)
    files = [file_name for file_name in files[0].decode("utf-8").split("\n") if file_format in file_name]
    yaml_files = []
    for file_yaml in files:
        yaml_files.append(os.path.join(path,file_yaml.strip()).strip())
    return yaml_files

def attach_file(path, file_name, msgroot):
    """
        Procedure to attach file in email
    """
    filename = path+file_name
    attachment = open(filename, "rb")

    part = MIMEBase('application', 'octet-stream')
    part.set_payload((attachment).read())
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', "attachment; filename= %s" % file_name)
    msgroot.attach(part)
    return msgroot

def get_html_message(image_files, users, user, user_data, recepient, path=None):
    """
        Procedure to embedded text/image message in email body
    """
    msgroot = MIMEMultipart('related')
    msgroot['Subject'] = user_data['subject']
    msgroot['From'] = user_data['from']
    msgroot['To'] = recepient
    msgroot['Message-ID'] = make_msgid()
    msgroot.preamble = 'This is a multi-part message in MIME format.'

    msgalternative = MIMEMultipart('alternative')
    msgroot.attach(msgalternative)

    if path is not None:
        # Attachment not required here
        # msgroot = attach_file(path, user_data['patch_info_file'], msgroot)
        pass
    html_message = '<br><html></br>'

    if users is not None:
        patch_groups = users[user].keys()
#        patch_groups.sort()
        sorted(patch_groups)

    for line in user_data['Message'].splitlines():
        if '<patch_group>' in line:
            html_message += 'Patchgroup: '
            for patch_group in patch_groups:
                html_message += patch_group+' '
        elif '<patch_group_schedule>' in line:
            for patch_group in patch_groups:
                html_message += '<p><b>'+'Patchgroup '+patch_group+'</b>'+':'\
                             +user_data['schedule'][patch_group]+'</p>'
        elif '<adobe_server_list>' in line:
            html_message += '<div><b>'+''+'</b></div>'
            html_message += '<div><table style="border: 1px solid black"></div>'
            count, message = create_html_table(['Sl.NO', 'PatchGroup', 'Minion'], users, user)
            html_message += message
            html_message += '<div></table></div>'
        else:
            html_message += line

    html_message += '<div></html></div>'
    html = str(html_message)
    msgtext = MIMEText(html, 'html')
    msgalternative.attach(msgtext)
    msgroot = append_image(image_files, msgroot)
    return msgroot

def append_image(image_files, msgroot):
    """
        Procedure to append image en email body
    """
    for image_file in image_files:
        if image_file is not None:
            fp_img = open(image_file, 'rb')
            msgimage = MIMEImage(fp_img.read())
            fp_img.close()
            msg_id = image_file.split('/')
            msg_id = msg_id[-1].split('.')[0]
            msgimage.add_header('Content-ID', '<{}>'.format(msg_id))
            msgroot.attach(msgimage)
        else:
            log.debug('No image file exist')
            return False
    return msgroot

def send_report(data, users, status, message, use_ssl):
    """
        Procedure to send final report
    """
    report = '<html>'
    report += '<div><table style="border: 1px solid black"></div>'
    count = 1
    table = ''
    for user in users:
        count, table = create_html_table(['Sl.No', 'Minion', 'Patchgroup',\
                        'Owners', 'Status'], users, user, count, status, '')
        report += table
    report += '<div></table></div>'
    report += '</html>'
    if message:
        data['Message'] = "%s file doesn't exist " %data['patch_info_file']
    else:
        data['Message'] = report
    data['subject'] = 'Report'
    for reporter in data['report_email_list']:
        msgroot = get_html_message([], None, None, data, reporter)
        if send_email(data['email_server'], None, None, data['from'], use_ssl, [reporter], msgroot):
            print ("Successfully sent mail to reporter")
            result = True
        else:
            result = False
    return result

def move_files(path, template, user_data):
    """
        Procedure To move template files to backup directory
    """
    obj = datetime.datetime.now()
    current_date = str(obj.year)+'-'+str(obj.month)+'-'+str(obj.day)
    flag = 1
    for patchgroup in user_data['reminder']:
        remider_data = str(user_data['reminder'][patchgroup][-1].year)+'-'\
                     +str(user_data['reminder'][patchgroup][-1].month)+'-'\
                     +str(user_data['reminder'][patchgroup][-1].day)
        if remider_data != current_date:
            flag = 0
            break
    if flag:
        p_obj = subprocess.Popen(['mv', template, '/root/templates/backup/'], stdout=subprocess.PIPE)
        files = p_obj.communicate()

def create_html_table(header, users, user, count=1, status=None, table=None):
    """
        Procedure to create html table dynamicaly
    """
    if count == 1:
        table = '<div><tr>'
        for head in header:
            table += '<th style="border: 1px solid black">'+head+'</th>'
        table += '</tr></div>'
    patch_groups = users[user].keys()
  #  patch_groups.sort()
    sorted(patch_groups)
    for patch_group in patch_groups:
        for minion in users[user][patch_group]:
            if status is None:
                table += '<tr><td style="border: 1px solid black;">'+str(count)\
                      +'</td><td style="border: 1px solid black;">'\
                      +patch_group+'</td><td style="border: 1px solid black;">'+minion+'</td></tr>'
            else:
                table += '<tr><td style="border: 1px solid black;">'+str(count)\
                +'</td><td style="border: 1px solid black;">'+minion+\
                '</td><td style="border: 1px solid black;">'+patch_group+\
                '</td><td style="border: 1px solid black;">'+user+\
                '</td><td style="border: 1px solid black;">'+status[user]+'</td></tr>'
            count += 1
    return count, table

def send_email(server, username, password, sender, use_ssl, recipients, msgroot):
    """
        Procedure send email
    """
    try:
        if use_ssl in ['True', 'true']:
            smtpconn = smtplib.SMTP_SSL(server)
        else:
            smtpconn = smtplib.SMTP(server)

    except socket.gaierror as _error:
        log.debug("Exception: {0}" . format(_error))
        return False

    if use_ssl not in ('True', 'true'):
        smtpconn.ehlo()
        if smtpconn.has_extn('STARTTLS'):
            try:
                smtpconn.starttls()
            except smtplib.SMTPHeloError:
                log.debug("The server didn’t reply properly \
                    to the HELO greeting.")
                return False
            except smtplib.SMTPException:
                log.debug("The server does not support the STARTTLS extension.")
                return False
            except RuntimeError:
                log.debug("SSL/TLS support is not available \
                        to your Python interpreter.")
                return False
            smtpconn.ehlo()

    if username and password:
        try:
            smtpconn.login(username, password)
        except smtplib.SMTPAuthenticationError as _error:
            log.debug("SMTP Authentication Failure")
            return False

    try:
        smtpconn.sendmail(sender, recipients, msgroot.as_string())
    except smtplib.SMTPRecipientsRefused:
        log.debug("All recipients were refused.")
        return False
    except smtplib.SMTPHeloError:
        log.debug("The server didn’t reply properly to the HELO greeting.")
        return False
    except smtplib.SMTPSenderRefused:
        log.debug("The server didn’t accept the {0}.".format(sender))
        return False
    except smtplib.SMTPDataError:
        log.debug("The server replied with an unexpected error code.")
        return False
    smtpconn.quit()
    return True

def is_scheduled(user_data, flag):
    """
        To check given time is matching with current time
    """
    obj = datetime.datetime.now()
    current_date = str(obj.year)+'-'+str(obj.month)+'-'+str(obj.day)
    lst_date = {}
    patch_schedule = []
    for patchgroup in user_data['reminder']:
        lst_date[patchgroup] = []
        for date in user_data['reminder'][patchgroup]:
            lst_date[patchgroup].append(str(date.year)+'-'+str(date.month)+'-'+str(date.day))
    for patchgroup in lst_date:
        if current_date not in lst_date[patchgroup] and not flag:
            continue
        patch_schedule.append(patchgroup)
    return patch_schedule

def get_minion_details(csv_file, schedule_patch_group, flag):
    """
        Procedure to get minion details and create data structure
    """
    with open(csv_file, 'r') as file_stream:
        csv_data = csv.DictReader(file_stream)
        users = {}
        list_of_contacts = ['Primary Contact', 'Secondary Contact']
        for data in csv_data:
            if data['PatchGroup'] not in schedule_patch_group and not flag:
                continue
            try:
                for contact in list_of_contacts:
                    users[data[contact]][data['PatchGroup']].add(data['Name'])
            except:
                for contact in list_of_contacts:
#                    if not users.has_key(data[contact]):
                    if not data[contact] in users:
                        users[data[contact]] = {}
                    users[data[contact]][data['PatchGroup']] = set([data['Name']])
            print (users)
        return users

def send_msg(path=''):
    """
        Main procedure
    """
    flag = 1
    if not path:
        path = '/root/templates/'
        flag = 0
    if not os.path.isfile(path) and flag:
        return "File %s deosn't exist" %path
    username, password = None, None
    pass_recipients = set()
    fail_recipients = set()
    users, status, ret = {}, {}, {}
    table, message = '', ''
    use_ssl = False
    if flag:
        split_path = path.split('/')
        path = path.strip(split_path[-1])

    files = get_files(path, '.yaml')
    image_file = get_files(path, '.jpg')
    for template in files:
        data = get_user_data(template)
        patch_group = is_scheduled(data, flag)
        if not flag and patch_group is None:
            continue
        if not os.path.isfile(path+data['patch_info_file']):
            message = 'File doesnt exist in /root/templates %s' %path
        else:
            users = get_minion_details(path+data['patch_info_file'], patch_group, flag)
        if not users and not message:
            continue
        print (patch_group)
        sender = data['from']
        server = data['email_server']
        for user in users:
            recipients = [user]
            msgroot = get_html_message(image_file, users, user, data, user, path)
            if send_email(server, username, password, sender, use_ssl, recipients, msgroot):
                pass_recipients.add(user)
                status[user] = 'Yes'
            else:
                fail_recipients.add(user)
                status[user] = 'No'
        print (status)
        if send_report(data, users, status, message, use_ssl):
            ret['comment'] = 'Report Email sent succesfully'
        else:
            ret['comment'] = 'Report Failed to send Email'
        ret['changes'] = {}
        ret['changes']['PASS'] = list(pass_recipients)
        ret['changes']['FAIL'] = list(fail_recipients)
        if not flag:
            move_files(path, template, data)
    return ret


if __name__ == "__main__":
    send_msg()
