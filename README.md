# openshift-rsyncer

# DESPLIEGUE BINARY BUILD:

#se construye la imagen para el pod temporal
oc new-project rsync-agent

cd oc-rsyncer-agent

oc new-build --name rsyncer-agent --binary --strategy docker 

oc start-build rsyncer-agent --follow --from-dir .

cd ..

#nos situamos en el proyecto default para desplegar el oc-rsyncer. (Importante, rellenar el fichero info.json)
oc project default

oc create -f conf/rbac.yml

oc new-build --name rsync --binary --strategy docker #create build from local dir

oc start-build rsync --from-dir . --follow

oc new-app rsync

oc patch dc/rsync --patch '{"spec":{"template":{"spec":{"serviceAccountName": "backup-sacc"}}}}'
 
oc create configmap info --from-file=info.json 

oc set volumes dc rsync --add --name=info --type=configmap --configmap-name=info --mount-path=/opt/app-root/info.json --sub-path=info.json

-------------------------------------------------

#DESPLIEGUE SOURCE BUILD:
