# openshift-rsyncer

# DESPLIEGUE BINARY BUILD:

#se construye la imagen para el pod temporal
git checkout oc-rsyncer-agent

#SEGUIR INSTRUCCIONES README PARA CONSTRUIR EL AGENT, al acabar, git checkout master

#EN EL FICHERO info.json HAY QUE PONER LOS PVCS (en el campo SOURCE_VOLUMES) QUE SE DESEAN EXPORTAR


mount -t nfs vdm-oscont.uoc.es:/PRO_openshift_repo/ /backup
#En el directorio /backup/PVCs ubicaremos los datos de cada pvc, con el siguiente formato: /backup/PVCs/<namespace>/<pvc>

oc project default

oc create -f files/rbac.yml

oc new-build --name rsync --binary --strategy docker -n oc-rsyncer #create build from local dir

oc start-build rsync --from-dir . --follow -n oc-rsyncer

oc create configmap info --from-file=conf/info.json -n default

oc create -f files/pv.yaml

oc create -f files/pvc.yaml -n default 

oc create -f files/cron.yaml



-------------------------------------------------


POSIBLES MEJORAS:
        - Añadir filtro defaults al template pod.yaml. por si hubieran variables no definidas
        - Controlar si el pod temporal ya existia en el proyecto.
        - Hacer el template de jinja2 pod.yaml mas extensible para que desde el ficher info.json se puedan añadir diferentes campos al pod rsync-agent.

