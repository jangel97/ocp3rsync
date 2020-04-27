'''
MANTAINER: openshift@essiprojects.com

El proposito de este script es realizar backup de todos aquellos PersistentVolumeClaims especificados en el fichero info.json.
Este script se puede ejcutar tanto dentro de un pod como desde un bastion de Openshift. En el caso de ejecutarse desde un bastion, es importante que el contexto de Openshift (Kubernetes) del usuario que ejecuta el script, tenga asigando el cluster-role cluster-admin. Si se ejecuta en un pod, se debe asignar serviceaccount con role cluster-admin al pod. Previamente a desplegar este proyecto, se tiene que construir la imagen que hay en el directorio `oc-rsyncer-agent`, y indicar alguna informacion sobre esta en el fichero info.json, para pasarle la informacion al pod, una opcion podria ser configmap y volumen montado con opcion sub-path. Es importante tener en cuenta que el storage de los pods es ephemeral y que por tanto a este pod donde se deplegaria el proyecto habria que montarle un PersistentVolumeClaim para asi garantizar la persistencia de los datos. 
- Si cuando se ejecuta el script, uno no esta loggeado contra el api de OpenShift, no se enviara correo ni se procedera con ninguna ejecucion
- No se debe borrar el pod rsyncer temporal mientras este en Running y el script no haya finalizado
Para mas información consultar en el fichero README.md
'''
import os,sys,json,time, yaml, logging, argparse as ap
from datetime import datetime
from kubernetes import client, config
from openshift.dynamic import DynamicClient, exceptions as OpenShiftExceptions
from pathlib import Path
from jinja2 import Template 
from logging.handlers import RotatingFileHandler
from emailSender import send_email

email_header='Ejecución Smart PV Containarized Replicator -' + '{:%Y-%m-%d}'.format(datetime.now()) 

logger = logging.getLogger('OCPRSYNCER')

logger.setLevel(logging.DEBUG)

#configurar log level con opciones
filehandler = logging.FileHandler('{:%Y-%m-%d-%H:%M}.ocprsynser.log'.format(datetime.now()))
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
filehandler.setFormatter(formatter)
logger.addHandler(filehandler)
log_filename= filehandler.baseFilename
consoleHandler = logging.StreamHandler(sys.stdout)
consoleHandler.setFormatter(formatter)
logger.addHandler(consoleHandler)
logger.debug('Smart PersistentVolume Containered Replicator is just started...')

try:
    import textwrap
    textwrap.indent
except AttributeError:  
    def indent(text, amount, ch=' '):
        padding = amount * ch
        return ''.join(padding+line for line in text.splitlines(True))
else:
    def indent(text, amount, ch=' '):
        return textwrap.indent(text, amount * ch)

PARAMS_JSON='conf/info.json'

#variables globales para api 
v1_pvc=None
v1_pod=None
v1_projects=None
v1_is=None
v1_pv=None

projects_list=None
json_key_error='''
Ejemplo de como usar el fichero JSON de parametro de entrada:
                 {
                   "AGENT_IMAGE_STREAM": "rsyncer-agent",
                   "AGENT_IMAGE_TAG": "latest",
                   "AGENT_PROJECT": "rsync-agent",
                   "SOURCE_VOLUMES": [
                      {
                                "NAMESPACE": "example",
                                "PVCS": ["pvc-example"]
                      },
                    ]
                  }
		'''
 
#ruta backup, si el script se ejecuta en un host, la raiz de los backups sera /backup, si se ejecuta en un pod, sera /opt/app-root/backup
ROOT_BACKUP_FOLDER="/backup/PVCs"

#opciones generales rsync
RSYNC_OPTIONS=" --delete=true --progress=true"
RSYNC_RESTORE_OPTIONS=" --progress=true"

class JsonError(Exception):
   def __init__(self, message,info=""):
      super().__init__(message)
      self.message = message
      self.info=info
   def __str__(self):
      return str('Mensaje de error: '+self.message+'\n'+indent(self.info,0))   
     

#print diccionario, proposito debug
def print_map(map):
   print(json.dumps(map,indent=2))

'''
El objetivo de esta funcion es inicializar el contexto de openshift (kubernetes).
Dependiendo de si el script se ejecuta en un pod o en un host, la configuracion se obtiene por una via u otra y se inicalizan las variables v1_pod y v1_pvc para las llamadas a la api.
'''
def initialize():
   logger.info('Procediendo a inicializar los objetos API')
   if "OPENSHIFT_BUILD_NAME" in os.environ:	#si el script se esta ejecutando en un pod... cargar el contexto desde dento del pod
      config.load_incluster_config()
      global ROOT_BACKUP_FOLDER
      ROOT_BACKUP_FOLDER="/opt/app-root/backup"
   else:
      config.load_kube_config()			#sino... cargar el contexto desde ~/.kube/config
   logger.info('Configuracion contexto (.kube/config) cargada')
   k8s_config = client.Configuration()		
   k8s_client = client.api_client.ApiClient(configuration=k8s_config)
   dyn_client = DynamicClient(k8s_client)	#crear objeto cliente API openshift desde configuracion kubernetes
   global v1_pvc
   global v1_is
   global v1_pod
   global v1_projects
   global projects_list
   global v1_pv
   try:
      v1_pvc = dyn_client.resources.get(api_version='v1',kind='PersistentVolumeClaim')
      v1_pv  = dyn_client.resources.get(api_version='v1',kind='PersistentVolume')
      v1_is = dyn_client.resources.get(api_version='v1',kind='ImageStream')
      v1_pod = dyn_client.resources.get(api_version='v1',kind='Pod')
      v1_projects = dyn_client.resources.get(api_version='project.openshift.io/v1', kind='Project')
      projects_list = list(map(lambda project: project['metadata']['name'],v1_projects.get()['items']))
      logger.info('Objetos api Openshift instanciados')
   except (OpenShiftExceptions.UnauthorizedError, OpenShiftExceptions.ForbiddenError) as e: 
      logger.critical('Unathorized, es requerido oc login, o el server no esta corriendo...')
      sys.exit(-1)    

'''
Esta funcion valida el json de entrada, cuyo PATH esta especificado en la constante PARAMS_JSON
'''
def validate_and_read__params_json():
   logger.info('Procediendo a validar y leer los parametros json')
   try:
      info=json.loads(open(PARAMS_JSON).read())
      logger.debug('Comprobando si existe clave SOURCE_VOLUMES...')
      if 'SOURCE_VOLUMES' not in info: raise JsonError('Clave SOURCE_VOLUMES no encontrada',json_key_error)
      logger.debug('Comprobando si existe clave SMTP_SERVER...')
      if 'SMTP_SERVER' not in info: raise JsonError('Clave SMTP_SERVER no encontrada',json_key_error)
      logger.debug('Comprobando si existe clave AGENT_IMAGE_TAG...')
      if 'AGENT_IMAGE_TAG' not in info: raise JsonError('Clave AGENT_IMAGE_TAG no encontrada',json_key_error)
      logger.debug('Comprobando si existe clave AGENT_IMAGE_STREAM...')
      if 'AGENT_IMAGE_STREAM' not in info: raise JsonError('Clave AGENT_IMAGE_STREAM no encontrada',json_key_error)
      logger.debug('Comprobando si existe clave AGENT_PROJECT...')
      if 'AGENT_PROJECT' not in info: raise JsonError('Clave AGENT_PROJECT no encontrada',json_key_error)
      logger.debug('Comprobando existencia del proyecto:  ' + info['AGENT_PROJECT'] )
      if info['AGENT_PROJECT'] not in projects_list: raise JsonError("Proyecto '"+info['AGENT_PROJECT']+"' no encontrado", "Es importante seguir los pasos del README.md, para asi empezar construyendo la imagen del pod temporal")
      logger.debug('Comprobando existencia del ImageStream:  ' + info['AGENT_IMAGE_STREAM'] )
      v1_is.get(name=info['AGENT_IMAGE_STREAM'],namespace=info['AGENT_PROJECT']) 
      logger.debug('Verificando correcto formatado del campo "SOURCE_VOLUMES"')
      for params in info['SOURCE_VOLUMES']: 
         if params=={}: raise JsonError('Hay un diccionario vacio dentro del json',json_key_error)
         if 'NAMESPACE' not in params: raise JsonError('Clave NAMESPACE falta en la seccion: ' + str(params),json_key_error)
         if 'PVCS' not in params: raise JsonError('Clave PVCS falta en la seccion: ' + str(params),json_key_error)
      return info
   except JsonError as e:
      logger.warn(str(e))
   except json.decoder.JSONDecodeError as e:
      logger.warn('Json no ha sido bien formatado. '+ str(e))
   except OpenShiftExceptions.NotFoundError as e:
      logger.error("Image stream '" +info['AGENT_IMAGE_STREAM']+"' no encontrado en proyecto '"+info['AGENT_PROJECT']+"'" )
   else:
      logger.info('El json ha sido correctamente formatado') 
   return 
    
   

'''
Esta rutina crea un PV con los datos de la aplicacion, para agilizar no tener que crearlo manualmente a posteriori
'''
def create_pv(namespace,pvc):
   pv_yaml=open('templates/pv.yaml.j2','r').read()
   template=Template(pv_yaml)
   try:
      v1_pv.get(name=str(pvc['spec']['volumeName']+'-backup'))
   except OpenShiftExceptions.NotFoundError: 
      logger.info('Procediendo a crear PV: '+ pvc['spec']['volumeName']+'backup')
      params_pv={
                  'pv_name': pvc['spec']['volumeName']+'-backup',
	          'accessModes': pvc['spec']['accessModes'],
                  'namespace': pvc['metadata']['namespace'],
		  'storageClass': 'nexica-nfs',
                  'serverNFS': 'vdm-oscont.uoc.es',
		  'size': pvc['spec']['resources']['requests']['storage']}
      pv_definition=template.render(params=params_pv)
      pv_template=yaml.load(pv_definition, Loader=yaml.FullLoader)
      resp = v1_pv.create(body=pv_template,namespace=namespace)
      logger.info(resp.to_dict())
      logger.info('PV CREADO')
   else:
      logger.info('PV: '+ pvc['spec']['volumeName']+ '-backup ya existente')




'''
El objetivo de esta funcion es iterar sobre la lista de pares PROYECTO:PVCs, especificada en el fichero info.json, asi pues, para cada proyecto se pedira al api pods solo en estado Running y pvcs, del proyecto que se este tratando. A continuacion, se iterara sobre los PVCs y se delegara en la funcion rsync, para que esta, con toda esta informacion (PODs, pvc, proyecto actual, nombre image-stream y proyecto donde se encuentra el image-stream a partir del cual se creara un pod temporal si es que ningun pod monta el pvc concreto).

Si un proyecto o pvc no existe, dara error y se procedera con el siguiente de la lista.
Si el pvc no existe, no se procedera a tratarloi
Es obligatorio que en el json existan las siguientes claves:
"AGENT_IMAGE_TAG": "latest",
"AGENT_IMAGE_STREAM": "rsyncer-agent",
"AGENT_PROJECT": "rsync-agent",
"SOURCE_VOLUMES": [
                      {
                                "NAMESPACE": "example",
                                "PVCS": ["pvc-example"]
                      },
                ]
}
'''
def treat_pvcs(info,args):
   html_params={}
   logger.info('Procediendo a procesar los diferentes PersistentVolumeClaims especificados en el JSON')
   for params in info['SOURCE_VOLUMES']:
      namespace=params['NAMESPACE']
      logger.debug("NAMESPACE ACTUAL: " + namespace)
      if namespace in projects_list:
         pods=list(v1_pod.get(namespace=namespace).to_dict()['items'])
         for pvc in params['PVCS']:
            try:
               pvcget=v1_pvc.get(namespace=namespace,name=pvc).to_dict() 
               if pvcget.get('status',{}).get('phase',"") == "Bound": 
                  logger.info('Procediendo a procesar el objeto PersistentVolumeClaim: ' + pvc + ' proyecto: ' + namespace)
                  message=rsync(pods,pvcget,namespace,info['AGENT_IMAGE_TAG'],info['AGENT_IMAGE_STREAM'],info['AGENT_PROJECT'],args)
                  if message is not None:
                     html_params['PersistentVolumeClaim: '+pvc]=message
                  else:
                     if not(args.restore): 
                        create_pv(namespace,pvcget)
               else: 
                  error="ERROR: PVC no esta en estado Bound, PVC: "+ str(params['PVCS'])
                  logger.error(error)
                  html_params['PersistentVolumeClaim: '+pvc]=error
                  logger.error(error)
            except OpenShiftExceptions.NotFoundError: 
               error="PersistentVolumeClaim '" + pvc + "' no existe"
               html_params['PersistentVolumeClaim: '+pvc]=error
               logger.error(error)
      else: 
         error="Proyecto '" + namespace + "' not existe"
         logger.error(error)
         html_params['Proyecto '+namespace]=error 
   return html_params

 
'''
El objetivo de esta funcion es iterar sobre los pods y encontrar cual es el que monta el pvc a tratar. Si se encuentra el pod, se procede a realizar el rsync contra este, una vez acabado, se sale de la funcion, pues no hay nada mas que hacer. Si resulta que ningun pod monta el volumen, se procedera a crear un pod temporal en el proyecto donde esta el pvc, el cual montara el volumen y se hara el oc rsync contra este. 

Este pod temporal se construira mediante los parametros especificados en el info.json (nombre image-stream, proyecto donde se encuentra image-stream). El pod, por defecto, esperara unos 5 minutos para desplegarse, si en 5 minutos no se ha desplegado correctamnte (estado=='Running'), se procedera a tratar al siguiente PersistentVolumeClaim y no se eliminara el pod temporal, con proposito de debug. Si el pod temporal se desplega correctamente, se procedera a hacer rsync contra este, una vez finalizado el rsync, se destruira. 
'''
def rsync(pods,pvc,namespace,agent_image_tag,agent_image_stream,agent_project,args):
   for pod in pods: 
      volume_pod_pvc=list(filter(lambda volume: volume.get('persistentVolumeClaim',{}).get('claimName','')==pvc['metadata']['name'],pod['spec']['volumes'])) #se comprueba que el pod tenga el pvc montado
      if volume_pod_pvc: #si tiene volumen asociado al pvc y el status es 'Running', se recorreran los containers para coger el que atache el volumen
         logger.debug("Existe un pod que monta el PVC... pod: '"+pod['metadata']['name'] +"' , pvc: " + pvc['metadata']['name'] )
         if pod['status']['phase']=="Running":
            logger.debug('El pod tiene estado Running, se procedera a realizar oc rsync contra este...')
            for container in pod['spec']['containers']:	
               volume_mount=list(filter(lambda volume_mount: volume_mount['name']==volume_pod_pvc[0]['name'],container['volumeMounts']))
               if volume_mount: break #se encontro el volume_mount 
            pod_path=volume_mount[0]['mountPath']  #siempre deberia encontrarse el volume_mount, muy extrano tiene que ser para que no
            pod_name=pod['metadata']['name']
            if not(args.restore):
               Path(ROOT_BACKUP_FOLDER + "/"+namespace+"/"+pvc['metadata']['name']).mkdir(parents=True, exist_ok=True)
               command="oc -n " + namespace + " rsync " + pod_name  +":" + pod_path + " "+ ROOT_BACKUP_FOLDER + "/" +namespace + "/"+pvc['metadata']['name'] + RSYNC_OPTIONS
            else:
               command="oc -n " + namespace + " rsync " + ROOT_BACKUP_FOLDER + "/" +namespace + "/"+pvc['metadata']['name'] + " "+ pod_name+":"+pod_path +" "+ RSYNC_RESTORE_OPTIONS
            logger.info(command)
            logger.info(os.popen(command).read()) 
            logger.debug('oc rsync realizado con exito!')
            return   #la funcion se acaba porque ya se encontro un pod donde el pvc estaba montado, si el codigo continua su ejecucion es porque el pvc esta 'Bound' pero ningun pod lo tiene montado
         else: #si hay contenedor que monta el volumen, pero no esta Running, entonces si el pvc es ReadWriteOnce se informara y no se continuara
            if 'ReadWriteOnce' in pvc['spec']['accessModes']:
               logger.error('No se pudo procesar el PVC:' + pvc['spec']['metadata']+' pues es de tipo ReadWriteOnce y ya esta montado por un pod ('+pod['metadata']['name']+') que no esta en estado Running...')
               return "Pod '" + pod['metadata']['name'] + "' not Running"

   #en este caso, pueden darse las siguientes dos situaciones:
      #que ningun pod monta el PVC y por tanto levantaremos el pod temporal
      #puede que algun pod no 'Running' monte el PVC y que el PVC no sea ReadWriteOnce, pues es montable por el pod temporal   
   message=None
   logger.debug('Se procede a crear un pod temporal en el proyecto: '+namespace)
   logger.info(os.popen('oc tag '+agent_project +'/'+agent_image_stream+':' + agent_image_tag + ' '+namespace+'/rsyncer-agent:latest -n ' + agent_project).read())
   pod_image=os.popen('oc get is rsyncer-agent -o yaml -n '+namespace+' | grep dockerImageRepository | tail -n1').read().split(": ")[1].rstrip()
   pod_yaml=open('templates/pod.yaml.j2','r').read()
   template=Template(pod_yaml)
   params_pod_temporary={
                  'backup_path': '/backup',
                  'name': 'rsyncer-pod-agent',
                  'image': pod_image,
                  'pvc': pvc['metadata']['name'],
                  'volume_name': str(pvc['metadata']['namespace']) + '-pvc-volume' }
   tt=0
   running=1
   pod_definition=template.render(params=params_pod_temporary)
   pod_template=yaml.load(pod_definition, Loader=yaml.FullLoader)
   resp = v1_pod.create(body=pod_template,namespace=namespace)   #controlar excepcion, si no se crea bien
   for wait in range(1,60):
      pod=v1_pod.get(namespace=namespace,name="rsyncer-pod-agent")
      status=pod['status']['phase']
      logger.info("El estado del pod temporal es... '" + status+"', proyecto: " + namespace)
      if status=="Running": break
      time.sleep(3)
      tt=tt+3
      if tt>=(300/3):
         message="Pod temporal no levanto en proyecto: "+namespace
         logger.error('Pod temporal, no consiguio levantar en proyecto: ' + namespace)      
         running=0
         break

   if (running):	#si el pod llego a levantar (status=="Running"), habra que hacer rsync
      logger.debug("Realizando rsync contra pod temporal en proyecto: "+namespace)
      if not(args.restore):
         command="oc -n " + namespace + " rsync "+ params_pod_temporary['name']  +":" + params_pod_temporary['backup_path'] + " "+ ROOT_BACKUP_FOLDER +"/" +namespace + "/"+pvc['metadata']['name'] + RSYNC_OPTIONS
         Path(ROOT_BACKUP_FOLDER + "/"+namespace+"/"+pvc['metadata']['name']).mkdir(parents=True, exist_ok=True)
      else:
         command="oc -n " + namespace + " rsync "+  ROOT_BACKUP_FOLDER +"/" +namespace + "/"+pvc['metadata']['name']  +" " + params_pod_temporary['name']  +":" + params_pod_temporary['backup_path'] + " " + RSYNC_RESTORE_OPTIONS
      logger.info(command)
      logger.info(os.popen(command).read())
   logger.info('Se procede a borrar el pod temporal')
   v1_pod.delete(name=params_pod_temporary['name'] , namespace=namespace)
   try:
      for wait in range(1,60):	#esperaremos a que se borre el pod, como maximo 3 minutos
         v1_pod.get(namespace=namespace,name="rsyncer-pod-agent")
         logger.info("Pod agente no se ha borrado aun, namespace: " + namespace)
         time.sleep(5)
   except:
         pass
   else:
         if message is not None: 
            message=message+'; Pod temporal no se pudo borrar en proyecto: '+ namespace
         else:
            message='Pod temporal no se pudo borrar en proyecto: '+ namespace
         logger.error('Pod temporal no se pudo borrar, procediento a forzar borrado del pod')
         logger.info(os.popen('oc delete po rsyncer-pod-agent --grace-period=0 --force -n '+namespace).read())
   logger.info("Pod temporal en en proyecto " + namespace + " fue borrado")
   return message


'''
Metodo principal, de momento no hay parametros de entrada.
'''
if __name__ == "__main__":
   parser = ap.ArgumentParser(description="Este proyecto realiza una copia entre PVCS")
   parser.add_argument("--restore",action='store_true', help="Restore mode")
   parser.add_argument("--backup",action='store_true',help="Backup mode")
   args, leftovers = parser.parse_known_args()
   if len(sys.argv)>2:
      logger.error("Solo se acepta una unica opcion, ejecuta `python3 oc-rsync.py --help` para mas informacion")
      quit()
   initialize()  #se inicializa el cliente del api de openshift con contexto correspondiente
   info=validate_and_read__params_json()  #se verifica y comprueba el json (parametros de entrada)
   if info is not None:	#si no han habido errores
      results_execution=treat_pvcs(info,args)   #si el json es correcto
      table_html_params={'info':results_execution,'logfile':log_filename}
      send_email(info['SMTP_SERVER'],info['SMTP_PORT'],email_header,info['MAIL_SENDER'],info['MAIL_DEST'],[log_filename],table_html_params,logger) 
      logger.debug('Proceso de sincronizacion de PV completado....')
