FROM registry.redhat.io/openshift3/ose-cli:v3.11
MAINTAINER openshift@essiprojects.com
ENV PYTHONWARNINGS="ignore:Unverified HTTPS request"
ENV HOME /opt/app-root
ENV SCRIPTS_HOME /opt/app-root
ENV BACKUP_PATH /opt/app-root/backup
LABEL io.k8s.description="Openshift OC rsync tool" \
      io.k8s.display-name="rsyncer-0.0.1" \
      io.openshift.tags="rsyncer,0.0.1"
RUN yum update -y && yum clean all && rm -rf /var/cache/yum/*
RUN yum install python3 python3-pip git rsync tar glusterfs-fuse nfs-utils iputils bind-utils -y && yum clean all && rm -rf /var/cache/yum/*
RUN \
  mkdir $SCRIPTS_HOME && mkdir $BACKUP_PATH && \
  groupadd -g 10001 backup && \
  useradd -r -u 10001 -g backup -G wheel  --home-dir $SCRIPTS_HOME backup && \
  chown -R backup:root $SCRIPTS_HOME && \
  chmod -R 775 $SCRIPTS_HOME
COPY  oc-rsync.py pod.yaml $SCRIPTS_HOME/
RUN \
  pip3 install --upgrade pip && \
  pip3 install --no-cache-dir openshift kubernetes 

USER 10001
WORKDIR $SCRIPTS_HOME
ENTRYPOINT ["python3","-u",  "oc-rsync.py"]

