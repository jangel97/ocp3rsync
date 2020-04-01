import os,sys,json,time, yaml 
from kubernetes import client, config
from openshift.dynamic import DynamicClient
from pathlib import Path
from pprint import pprint
from jinja2 import Template 

v1_pvc=None
v1_pod=None

ROOT_BACKUP_FOLDER="/backup"

RSYNC_OPTIONS=" --delete=true --progress=true"

def print_map(map):
   print(json.dumps(map,indent=2))	#embellecer salida diccionario, proposito debug

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

def treat_pvcs():
   info=json.loads(open('info.json').read())
   for params in info['SOURCE_VOLUMES']:
      namespace=params['NAMESPACE']
      pods=v1_pod.get(namespace=namespace).to_dict()['items']
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
      if volume_pod_pvc and pod['status']['phase']=='Running': #si tiene volumen asociado al pvc y el status es 'Running', se recorreran los containers para coger el que atache el volumen
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
   print('TEMPORARY POOOOOOOOOOOOOD')
   print('oc tag '+agent_project +'/'+agent_image+ ' '+namespace+'/rsyncer-agent -n ' + agent_project)
   print(os.popen('oc tag '+agent_project +'/'+agent_image+ ' '+namespace+'/rsyncer-agent:latest -n ' + agent_project).read())
   pod_image=(os.popen('oc get is -o yaml -n '+namespace+' | grep dockerImageRepository | tail -n1').read())
   pod_image= pod_image.split(": ")[1].rstrip()
   print("POD IMAGE IS :" + str(pod_image))
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
   command="oc -n " + namespace + " rsync "+ params_pod_temporary['name']  +":" + params_pod_temporary['backup_path'] + " "+ ROOT_BACKUP_FOLDER +"/" +namespace + "/"+pvc['metadata']['name']
  
   Path(ROOT_BACKUP_FOLDER + "/"+namespace+"/"+pvc['metadata']['name']).mkdir(parents=True, exist_ok=True)
   print(command)
   print(os.popen(command).read()) 
   v1_pod.delete(name=params_pod_temporary['name'] , namespace=namespace)
   print("Temporary pod in namespace " + namespace + " was deleted")
 
if __name__ == "__main__":
   initialize()
   treat_pvcs()
