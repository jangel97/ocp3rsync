import sys
import codecs
import os
import smtplib
from conf import credentials
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from jinja2 import Template

#https://realpython.com/python-send-email/

COMMASPACE = ', '

'''
subject: titulo del correo
recipients: array de destinatarios
attachments: array de ficheros de attach
'''
def send_email(smtp_server,smtp_port,subject,sender,recipients,attachments,params_email,logger):
    html_text= open('templates/email.html.j2').read()
    html_template=Template(html_text)
    html=html_template.render(params=params_email)     
    
    gmail_password=credentials.login['password']
    #recipients = ['jamorena@essiprojects.com','jos3mor3na@gmail.com']
    
    # Create the enclosing (outer) message
    outer = MIMEMultipart()
    #outer['Subject'] = 'Ejecución Smart PV Containarized Replicator -' + '{:%Y-%m-%d}'.format(datetime.now()) 
    outer['Subject'] = subject 
    outer['To'] = COMMASPACE.join(recipients)
    outer['From'] = sender

    # List of attachments
    #attachments = ['./ocprsyncer.log']

    # Add the attachments to the message
    for file in attachments:
        try:
            with open(file, 'rb') as fp:
                msg = MIMEBase('application', "octet-stream")
                msg.set_payload(fp.read())
            encoders.encode_base64(msg)
            msg.add_header('Content-Disposition', 'attachment', filename=os.path.basename(file))
            outer.attach(msg)  
            web=MIMEText(html,"html")
            outer.attach(web)
        except:
            logger.error("No se pudo . Error: ", sys.exc_info()[0])

    composed = outer.as_string()
    # Send the email
    try:
        with smtplib.SMTP(smtp_server, smtp_port) as s:
            s.ehlo()
            #s.starttls()
            s.ehlo()
            #s.login(sender, gmail_password)
            s.sendmail(sender, recipients, composed)
            s.close()
            logger.debug("Correo enviado!")
    except:
        logger.error("No se pudo enviar el email. Error: ", sys.exc_info()[0])
        raise

#if __name__ == '__main__':
#    main()
