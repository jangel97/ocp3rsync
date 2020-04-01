'''
MANTAINER: openshift@essiprojects.com

El proposito de este script es realizar backup de todos aquellos PersistentVolumeClaims especificados en el fichero info.json.
Este script se puede ejcutar tanto dentro de un pod como desde un bastion de Openshift. En el caso de ejecutarse desde un bastion, es importante que el contexto de Openshift (Kubernetes) del usuario que ejecuta el script, tenga asigando el cluster-role cluster-admin. Si se ejecuta en un pod, se debe asignar serviceaccount con role cluster-admin al pod. Previamente a desplegar este proyecto, se tiene que construir la imagen que hay en el directorio `oc-rsyncer-agent`, y indicar alguna informacion sobre esta en el fichero info.json, para pasarle la informacion al pod, una opcion podria ser configmap y volumen montado con opcion sub-path. Es importante tener en cuenta que el storage de los pods es ephemeral y que por tanto a este pod donde se deplegaria el proyecto habria que montarle un PersistentVolumeClaim para asi garantizar la persistencia de los datos. 

Para mas información consultar en el fichero README.md
'''
import os,sys,json,time, yaml 
from kubernetes import client, config
from openshift.dynamic import DynamicClient
from pathlib import Path
from pprint import pprint
from jinja2 import Template 

#variables globales para api 
v1_pvc=None
v1_pod=None

#ruta backup, si el script se ejecuta en un host, la raiz de los backups sera /backup, si se ejecuta en un pod, sera /opt/app-root/backup
ROOT_BACKUP_FOLDER="/backup"

#opciones generales rsync
RSYNC_OPTIONS=" --delete=true --progress=true"

#print diccionario
def print_map(map):
   print(json.dumps(map,indent=2))

'''
El objetivo de esta funcion es inicializar el contexto de openshift (kubernetes).
Dependiendo de si el script se ejecuta en un pod o en un host, la configuracion se obtiene por una via u otra y se inicalizan las variables v1_pod y v1_pvc para las llamadas a la api.
'''
def initialize():
   if "OPENSHIFT_BUILD_NAME" in os.environ:	#si el script se esta ejecutando en un pod... cargar el contexto desde dento del pod
      config.load_incluster_config()
      file_namespace = open(
          "/run/secrets/kubernetes.io/serviceaccount/namespace", "r"
      )
      if file_namespace.mode == "r":
         namespace = file_namespace.read()
         print("namespace: %s\n" %(namespace))
         global ROOT_BACKUP_FOLDER
         ROOT_BACKUP_FOLDER="/opt/app-root/backup"
   else:
      config.load_kube_config()			#sino... cargar el contexto desde ~/.kube/config
   k8s_config = client.Configuration()		
   k8s_client = client.api_client.ApiClient(configuration=k8s_config)
   dyn_client = DynamicClient(k8s_client)	#crear objeto cliente API openshift desde configuracion kubernetes
   global v1_pvc
   global v1_pod
   v1_pvc = dyn_client.resources.get(api_version='v1',kind='PersistentVolumeClaim')
   v1_pod = dyn_client.resources.get(api_version='v1',kind='Pod')

'''
El objetivo de esta funcion es iterar sobre la lista de pares PROYECTO:PVCs, especificada en el fichero info.json, asi pues, para cada proyecto se pedira al api pods y pvcs delproyecto que se este tratando
'''
def treat_pvcs():
   info=json.loads(open('info.json').read())
   for params in info['SOURCE_VOLUMES']:
      namespace=params['NAMESPACE']
      pods=list(filter(lambda pod: pod['status']['phase']=='Running',v1_pod.get(namespace=namespace).to_dict()['items']))
      for pvc in params['PVCS']:
         pvc=v1_pvc.get(namespace=namespace,name=pvc).to_dict()  #CHEQUEAR, QUE PASA SI EL PVC NO SE ENCUENTRA EN EL PROYECTO, O DIRECTAMENTE NI EXISTE
         if pvc['status']['phase'] == "Bound":
            rsync(pods,pvc,namespace,info['AGENT_IMAGE_TAG'],info['AGENT_PROJECT'])
         else: 
            print("ERROR: PVC: "+ str(pvc['metadata']['name']) + ", proyecto: " + str(namespace) + " has status pending..." )

def rsync(pods,pvc,namespace,agent_image,agent_project):
   print("\n\n----------------------------------\nNAMESPACE: " + namespace)
   print("PVC: " + pvc['metadata']['name'])
   for pod in pods: 
      volume_pod_pvc=list(filter(lambda volume: volume.get('persistentVolumeClaim',{}).get('claimName','')==pvc['metadata']['name'],pod['spec']['volumes'])) #se comprueba que el pod tenga el pvc montado
      if volume_pod_pvc: #si tiene volumen asociado al pvc y el status es 'Running', se recorreran los containers para coger el que atache el volumen
         for container in pod['spec']['containers']:	
            volume_mount=list(filter(lambda volume_mount: volume_mount['name']==volume_pod_pvc[0]['name'],container['volumeMounts']))
            if volume_mount: break #se encontro el volume_mount 
         pod_path=volume_mount[0]['mountPath']  #siempre deberia encontrarse el volume_mount, muy extrano tiene que ser para que no
         pod_name=pod['metadata']['name']
         Path(ROOT_BACKUP_FOLDER + "/"+namespace+"/"+pvc['metadata']['name']).mkdir(parents=True, exist_ok=True)
         command="oc -n " + namespace + " rsync " + pod_name  +":" + pod_path + " "+ ROOT_BACKUP_FOLDER + "/" +namespace + "/"+pvc['metadata']['name'] + RSYNC_OPTIONS
         print(command)
         print(os.popen(command).read()) 
         return   #la funcion se acaba porque ya se encontro un pod donde el pvc estaba montado, si el codigo continua su ejecucion es porque el pvc esta 'Bound' pero ningun pod lo tiene montado
   print(os.popen('oc tag '+agent_project +'/'+agent_image+ ' '+namespace+'/rsyncer-agent:latest -n ' + agent_project).read())
   pod_image=os.popen('oc get is -o yaml -n '+namespace+' | grep dockerImageRepository | tail -n1').read().split(": ")[1].rstrip()
   pod_yaml=open('pod.yaml','r').read()
   template=Template(pod_yaml)
   params_pod_temporary={
                  'backup_path': '/backup',
                  'name': 'rsyncer-pod-agent',
                  'image': pod_image,
                  'pvc': pvc['metadata']['name'],
                  'volume_name': str(pvc['metadata']['namespace']) + '-pvc-volume' }

   pod_definition=template.render(params=params_pod_temporary)
   pod_template=yaml.load(pod_definition, Loader=yaml.FullLoader)
   resp = v1_pod.create(body=pod_template,namespace=namespace)   #controlar excepcion, si no se crea bien
   tt=0
   for event in v1_pod.watch(namespace=namespace):
      status=event['raw_object']['status']['phase']
      print("\nPod agent status is... " + status+", namespace: " + namespace)
      if status=="Running": break
      time.sleep(3)
      tt=tt+3
      if tt>=(300/3): 
         print('ERROR: Pod temporal, no consiguio levantar en proyecto: ' + namespace)
         return
 
   print("Attempting rsync against temporary pod in project: "+namespace) 
   command="oc -n " + namespace + " rsync "+ params_pod_temporary['name']  +":" + params_pod_temporary['backup_path'] + " "+ ROOT_BACKUP_FOLDER +"/" +namespace + "/"+pvc['metadata']['name'] + RSYNC_OPTIONS
  
   Path(ROOT_BACKUP_FOLDER + "/"+namespace+"/"+pvc['metadata']['name']).mkdir(parents=True, exist_ok=True)
   print(command)
   print(os.popen(command).read()) 
   v1_pod.delete(name=params_pod_temporary['name'] , namespace=namespace)
   print("Temporary pod in namespace " + namespace + " was deleted")
 
if __name__ == "__main__":
   initialize()
   treat_pvcs()
