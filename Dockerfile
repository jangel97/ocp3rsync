FROM registry.redhat.io/openshift3/ose-cli
MAINTAINER openshift@essiprojects.com
ENV HOME="/opt/app-root" \
  SCRIPTS_HOME="/opt/app-root" \
  SYNC_PLAN_PATH="/opt/app-root/conf" \
  LOG_PATH="/opt/app-root/logs" \
  PATH=$PATH:$SCRIPTS_HOME
LABEL io.k8s.description="Openshift PV rsync tool" \
      io.k8s.display-name="rsyncer-0.0.1" \
      io.openshift.tags="rsyncer,0.0.1"
# Update the image with the latest packages (recommended)
RUN yum update -y && \
  yum clean all && \
  rm -rf /var/cache/yum/*
# Install rsync, gluster & nfs clients
RUN yum install -y rsync tar glusterfs-fuse nfs-utils iputils bind-utils && \
  yum clean all && \
  rm -rf /var/cache/yum/*

