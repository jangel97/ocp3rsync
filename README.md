# openshift-rsyncer

# DESPLIEGUE BINARY BUILD:

#se construye la imagen para el pod temporal

oc import-image openshift/ose-cli --from=registry.redhat.io/openshift3/ose-cli -n openshift --confirm

oc new-project rsync-agent

oc new-build --name rsyncer-agent --binary --strategy docker 

oc start-build rsyncer-agent --follow --from-dir .

oc get is # para ver que se ha generado correctamente el imagestream 
-------------------------------------------------

#DESPLIEGUE SOURCE BUILD:
