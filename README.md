# openshift-rsyncer

# BINARY BUILD:

oc new-project prueba

oc create -f conf/rbac.yml

oc new-build --name rsync --binary --strategy docker #create build from local dir

oc start-build rsync --from-dir . --follow

oc new-app rsync

oc patch dc/rsync --patch '{"spec":{"template":{"spec":{"serviceAccountName": "backup-sacc"}}}}'
 
oc create configmap info --from-file=info.json 

oc set volumes dc rsync --add --name=info --type=configmap --configmap-name=info --mount-path=/opt/app-root/info.json --sub-path=info.json

-------------------------------------------------


https://github.com/kubernetes-client/python/blob/02ef5be4ecead787961037b236ae498944040b43/examples/pod_exec.py

https://github.com/openshift/openshift-restclient-python

https://stackoverflow.com/questions/287871/how-to-print-colored-text-in-terminal-in-python


https://stackoverflow.com/questions/42363105/permission-denied-mkdir-in-container-on-openshift


https://stackoverflow.com/questions/3503879/assign-output-of-os-system-to-a-variable-and-prevent-it-from-being-displayed-on

https://stackoverflow.com/questions/44035287/check-key-exist-in-python-dict/44035382


https://kubernetes.io/docs/tasks/configure-pod-container/configure-persistent-volume-storage/  #definicion yaml de pod con pvc

CREAR SECRETO PULL IMAGE:
https://kubernetes.io/docs/concepts/containers/images/#specifying-imagepullsecrets-on-a-pod

https://docs.openshift.com/container-platform/3.11/dev_guide/secrets.html

https://kubernetes.io/docs/tasks/configure-pod-container/pull-image-private-registry/
oc adm pod-network join-projects --to=prueba primary default #prueba, proyecto donde desplegue el pod rsyncer, primary y default proyectos con volumenes
#incluir en el condigo

https://docs.openshift.com/container-platform/3.11/dev_guide/managing_images.html#importing-images-across-projects   -> promocion de imagenes entre proyectos


oc adm pod-network isolate-projects prueba primary default
#isolate project, default is not possible to isolate


#rsync -a -v --rsh='oc rsh -n default' docker-registry-1-fp2f7:/registry  primary/primary-primary-pgdata/   -> v2.go:147] write /dev/stdout: resource temporarily unavailable

#oc adm pod-network make-projects-global <project1> <project2> -> opcion interesante

 oc set volumes dc nagiosdocker --add --name=htpasswd --type=configmap --configmap-name=htpasswd.users --mount-path=/usr/local/nagios/etc/htpasswd.users --sub-path=htpasswd.users


 oc set volumes dc/drupal-openshift --add --name=mysql --type=pvc --mount-path=/var/lib/mysql/data --claim-size=10Gi


 oc set volumes dc/docker-registry --add --name=registrynfs --type=pvc --mount-path=/registry --claim-name=registrynfs-claim 


#git log --graph --decorate --oneline

https://github.com/learnk8s/templating-kubernetes/tree/master/python

https://github.com/kubernetes-client/python/tree/master/examples
